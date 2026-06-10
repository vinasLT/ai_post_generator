import asyncio
import grpc
from typing import Any

from dateutil import parser
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent_debug_log import agent_debug_log
from app.core.logger import async_timer
from app.database.models import Post
from app.database.schemas.post import PostUpdate, PostCreate
from app.rpc_client.auction_api import ApiRpcClient
from app.services.lang_chain_agent.serializer import SerializePost
from app.services.lang_chain_agent.types import Filters
from app.services.rabbit.rabbit_service import RabbitMQPublisher
from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.enums import AuctionEnum
from app.rpc_client.calculator import (
    CalculatorRcpClient,
    calculator_response_from_batch_item,
    get_broker_fee_from_calculator,
    is_valid_calculator_response,
)
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
    # #region agent log
    try:
        auc = AuctionEnum(lot.base_site.lower())
    except Exception as ae:
        auc = None
    agent_debug_log(
        "H2",
        "utils.py:get_calculator_for_lot:entry",
        "lot_and_rcp",
        {
            "lot_id": lot.lot_id,
            "base_site": getattr(lot, "base_site", None),
            "auction_resolved": str(auc) if auc is not None else None,
            "vehicle_type": getattr(lot, "vehicle_type", None),
            "location_preview": (lot.location or "")[:160],
            "rcp_calculator_url": settings.RCP_CALCULATOR_URL,
        },
    )
    # #endregion
    try:
        async with CalculatorRcpClient() as client:
            try:
                response = await client.get_calculator_with_data(
                    price=1,
                    auction=AuctionEnum(lot.base_site.lower()),
                    vehicle_type=lot.vehicle_type,
                    location=lot.location
                )
                if not is_valid_calculator_response(response):
                    logger.warning(
                        f'For lot: {lot.lot_id} calculator returned no pricing data',
                        extra={
                            'location': lot.location,
                            'vehicle_type': lot.vehicle_type,
                        },
                    )
                    return None
                return response
            except grpc.aio.AioRpcError as e:
                # #region agent log
                agent_debug_log(
                    "H2",
                    "utils.py:get_calculator_for_lot:rpc",
                    "AioRpcError",
                    {
                        "lot_id": lot.lot_id,
                        "code": str(e.code()),
                        "details": (e.details() or "")[:500],
                    },
                )
                # #endregion
                logger.warning(f'For lot: {lot.lot_id} data for calculator was not found (Rpc Request)',
                               extra={'error_code': str(e.code()), 'error_details': str(e.details())})
                return None
    except Exception as e:
        # #region agent log
        agent_debug_log(
            "H1",
            "utils.py:get_calculator_for_lot:outer",
            "non_rpc_or_connect",
            {"lot_id": lot.lot_id, "exc_type": type(e).__name__, "exc": str(e)[:500]},
        )
        # #endregion
        raise

async def get_calculators_for_lots(lots: list[lot_pb2.Lot]) -> list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]]:
    if not lots:
        return []

    results: dict[int, calculator_pb2.GetCalculatorWithDataResponse] = {}

    try:
        async with CalculatorRcpClient() as client:
            batch_response = await client.get_batch_calculators_with_data(lots)
            if batch_response:
                for item in batch_response.data:
                    response = calculator_response_from_batch_item(item)
                    if response:
                        results[int(item.lot_id)] = response
    except Exception as e:
        logger.error(f"Batch calculator request failed: {e}")

    missing_lots = [lot for lot in lots if lot.lot_id not in results]
    if missing_lots:
        semaphore = asyncio.Semaphore(5)

        async def fetch_single(lot: lot_pb2.Lot) -> None:
            async with semaphore:
                try:
                    calculator = await get_calculator_for_lot(lot)
                    if is_valid_calculator_response(calculator):
                        results[lot.lot_id] = calculator
                except Exception as e:
                    logger.error(f"Error getting calculator for lot {lot.lot_id}: {str(e)}")

        await asyncio.gather(*(asyncio.create_task(fetch_single(lot)) for lot in missing_lots))

    if len(results) < len(lots):
        logger.warning(
            "Calculator pricing missing for some lots",
            extra={
                "requested": len(lots),
                "resolved": len(results),
            },
        )

    return [(lot, results[lot.lot_id]) for lot in lots if lot.lot_id in results]





class GeneratePostUtils:
    def __init__(self, filters: Filters, request_id: int, user_uuid: str):
        self.filters = filters
        self.user_uuid = user_uuid
        self.request_id = request_id
        self.auction_api_client = ApiRpcClient()

    @classmethod
    def generate_response_for_user(cls, posts: list[Post]) -> list[dict[str, Any]]:
        posts_serialized = []
        for post in posts:
            post_serializer = SerializePost(post)
            text = post_serializer.serialize()
            images = post_serializer.get_images()
            link = post_serializer.generate_link()
            posts_serialized.append({'text': text, 'images': images, 'link': link, 'post_id': post.id})

        return posts_serialized

    @classmethod
    async def create_post(cls, lot: lot_pb2.Lot, calculator: calculator_pb2.GetCalculatorWithDataResponse,
                          request_id: int, db: AsyncSession, flush: bool = False,
                          average_sell_price: int = None) -> Post | None:
        post_service = PostService(db)
        minimal_delivery_price = min(
            [delivery_price.price for delivery_price in calculator.data.calculator.transportation_price])
        minimal_shipping_price = min([shipping_price.price for shipping_price in calculator.data.calculator.ocean_ship])
        try:
            post = await post_service.create(PostCreate(
                lot_id=lot.lot_id,
                auction=AuctionEnum(lot.base_site),
                title=lot.title,
                make=lot.make,
                model=lot.model if lot.model else None,
                odometer=lot.odometer,
                vin=lot.vin,
                status=lot.status,
                primary_damage=lot.damage_pr.upper() if lot.damage_pr else None,
                year=lot.year,
                auction_date=parser.parse(lot.auction_date) if lot.auction_date else None,
                delivery_price=minimal_delivery_price,
                shipping_price=minimal_shipping_price,
                broker_fee=get_broker_fee_from_calculator(calculator),
                average_sell_price=average_sell_price,
                request_id=request_id,
                images=','.join(list(lot.link_img_hd)[:10])
            ), flush=flush)
        except Exception as e:
            logger.error(f"Error processing lot {lot.lot_id} to DB: {e}")
            return None
        return post

    @classmethod
    async def send_response_to_user(cls, posts: list[Post], request_id: int, user_uuid: str):
        serialized = cls.generate_response_for_user(posts)
        data = {
            'posts': serialized,
            'request_id': request_id,
            'user_uuid': user_uuid
        }
        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.generated_posts', payload=data)

    @classmethod
    async def edit_message_for_user(cls, message_id: int, text: str, user_uuid: str):
        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.update_message',
                                    payload={'message': text, 'message_id': message_id, 'user_uuid': user_uuid})

    @classmethod
    async def get_average_price(cls, post: Post) -> int | None:
        async with ApiRpcClient() as client:
            year_from = None
            year_to = None
            if post.year:
                year_from = post.year - 1
                year_to = post.year + 1
            response = await client.get_average_price(post.make, post.model,
                                                      year_from=year_from,
                                                      year_to=year_to,
                                                      period=6)

            logger.debug(f'Response avg prices: {list(response.stats)}')
            avg_prices = []
            for item in response.stats:
                avg_prices.append(item.total)
            if not avg_prices:
                return None
            logger.debug(f'Avg prices: {avg_prices}')
            avg = round(sum(avg_prices) / len(avg_prices))
            logger.debug(f'Avg: {avg}')
            return avg

    @classmethod
    async def send_error_to_user(cls, request_id: int, user_uuid: str, error_message: str):
        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.error', payload={
                'error_message': error_message,
                'request_id': request_id,
                'user_uuid': user_uuid
            })
    @classmethod
    async def update_average_price_for_posts(cls, posts: list[Post])->list[Post]:
        updated_posts = []
        async with async_timer('update average sell price'):
            async with get_async_db() as db:
                posts_service = PostService(db)
                for post in posts:
                    try:
                        average_price = await cls.get_average_price(post)
                        updated_posts.append(await posts_service.update(post.id, PostUpdate(average_sell_price=average_price)))
                    except Exception as e:
                        updated_posts.append(post)
                        logger.error(f'Error updating average sell price for post {post.id}: {e}')
        return updated_posts



