import grpc

from app.core.logger import logger, log_async_execution_time
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.models import RequestFilters
from app.database.schemas.request_filters import RequestFiltersCreate, RequestFiltersUpdate
from app.rpc_client.auction_api import ApiRpcClient
from app.rpc_client.calculator import CalculatorRcpClient
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.services.ai_post_generation.types import Filters


class GeneratePosts:
    def __init__(self, filters: Filters, user_uuid: str):
        self.filters = filters
        self.user_uuid = user_uuid
        self.request: RequestFilters | None = None

    async def _search_results_generator(self):
        try:
            async with ApiRpcClient() as client:
                async for lots in client.get_current_lots_by_filters_generator(self.filters):
                    yield lots
        except grpc.aio.AioRpcError as e:
            logger.error(f'Error getting search results from api for request: {self.request.id if self.request else "unknown"}',
                         extra={'error_code': str(e.code()), 'error_details': str(e.details())})

    async def set_request_stage(self, stage: RequestStage):
        async with get_async_db() as db:
            service = RequestFiltersService(db)
            if not self.request:
                self.request = await service.create(
                    RequestFiltersCreate(
                        user_uuid=self.user_uuid,
                        **self.filters.model_dump(),
                        stage=stage
                    )
                )
            else:
                self.request = await service.set_request_stage(
                    self.request.id,
                    stage
                )
    @log_async_execution_time('Get calculator for lots')
    async def _get_calculator_results(self, lots: list[lot_pb2.Lot]):
        try:
            async with CalculatorRcpClient() as client:
                return await client.get_batch_calculators_with_data(lots)
        except grpc.aio.AioRpcError as e:
            logger.error(f'Error getting calculator results for request: {self.request.id if self.request else "unknown"}',
                         extra={'error_code': str(e.code()), 'error_details': str(e.details())})
            return []


    async def process_page(self, lots: list[lot_pb2.Lot]):
        calculator_results = await self._get_calculator_results(lots)


    async def run(self):
        await self.set_request_stage(RequestStage.STARTING)

        async for lots in self._search_results_generator():
            await self.process_page(lots)



