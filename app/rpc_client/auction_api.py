import os
import sys

import grpc

from app.config import settings
from app.rpc_client.base_client import BaseRpcClient, T
from app.services.ai_post_generation.types import Filters

# Ensure generated proto packages (auction, carfax, payment) are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gen', 'python'))

from app.rpc_client.gen.python.auction.v1 import lot_pb2_grpc, lot_pb2


class ApiRpcClient(BaseRpcClient[lot_pb2_grpc.LotServiceStub]):
    def __init__(self):
        super().__init__(server_url=settings.RPC_AUCTION_API_URL)

    async def __aenter__(self):
        await self.connect()
        return self

    def _create_stub(self, channel: grpc.aio.Channel) -> T:
        return lot_pb2_grpc.LotServiceStub(channel)

    async def get_lot_by_vin_or_lot_id(self, vin_or_lot_id: str, site: str = None) -> lot_pb2.GetLotByVinOrLotResponse:
        data = lot_pb2.GetLotByVinOrLotRequest(vin_or_lot_id=vin_or_lot_id, site=site)
        return await self._execute_request(self.stub.GetLotByVinOrLot, data)

    async def get_current_lots_with_filters(
            self,
            filters: Filters,
            vehicle_type: str = 'Automobile',
            size: int = 20,
            page: int = 1
        ) -> lot_pb2.GetCurrentLotsByFiltersResponse:

        data = lot_pb2.GetCurrentLotsByFiltersRequest(
            site=filters.site,
            make=filters.make,
            model=filters.model,
            year_from=filters.year_from,
            year_to=filters.year_to,
            vehicle_type=vehicle_type,
            status=filters.status,
            transmission=filters.transmission,
            odometer_min=filters.odo_from,
            odometer_max=filters.odo_to,
            document=filters.document,
            size=size,
            page=page
        )
        return await self._execute_request(self.stub.GetCurrentLotsByFilters, data)

    async def get_current_bid(self, lot_id: int, site: str) -> lot_pb2.GetCurrentBidResponse:
        data = lot_pb2.GetCurrentBidRequest(lot_id=lot_id, site=site)
        return await self._execute_request(self.stub.GetCurrentBid, data)

    async def get_sale_history(self, lot_id: int, site: str) -> lot_pb2.GetSaleHistoryResponse:
        data = lot_pb2.GetSaleHistoryRequest(lot_id=lot_id, site=site)
        return await self._execute_request(self.stub.GetSaleHistory, data)
