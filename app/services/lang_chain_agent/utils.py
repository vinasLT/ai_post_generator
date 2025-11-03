import asyncio

import grpc

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.enums import AuctionEnum
from app.rpc_client.calculator import CalculatorRcpClient
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2


async def get_repeated_lots(lot_ids: list[int], user_uuid: str, request_id: int | None = None) -> list[int]:
    if not lot_ids:
        return []

    async with get_async_db() as db:
        post_service = PostService(db)
        repeated_set = await post_service.get_repeated_lot_ids_for_user(
            user_uuid=user_uuid,
            lot_ids=lot_ids,
            exclude_request_id=request_id,
        )

    return [lot_id for lot_id in lot_ids if lot_id in repeated_set]



async def get_calculator_for_lot(lot: lot_pb2.Lot) -> calculator_pb2.GetCalculatorWithDataResponse | None:
    async with CalculatorRcpClient() as client:
        try:
            response = await client.get_calculator_with_data(
                price=1,
                auction=AuctionEnum(lot.base_site.lower()),
                vehicle_type=lot.vehicle_type,
                location=lot.location
            )
            return response
        except grpc.aio.AioRpcError as e:
            logger.warning(f'For lot: {lot.lot_id} data for calculator was not found (Rpc Request)',
                           extra={'error_code': str(e.code()), 'error_details': str(e.details())})
            return None

async def get_calculators_for_lots(lots: list[lot_pb2.Lot]) -> list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]]:
    semaphore = asyncio.Semaphore(5)
    lots_with_calculators: list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]] = []

    async def get_calculator(lot: lot_pb2.Lot) -> None:
        async with semaphore:
            try:
                calculator = await get_calculator_for_lot(lot)
                if calculator:
                    lots_with_calculators.append((lot, calculator))
            except Exception as e:
                logger.error(f"Error getting calculator for lot {lot.lot_id}: {str(e)}")

    await asyncio.gather(*(asyncio.create_task(get_calculator(lot)) for lot in lots))
    return lots_with_calculators
