from app.core.logger import logger
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.request_filters import RequestFiltersCreate
from app.rpc_client.auction_api import ApiRpcClient
from app.services.ai_post_generation.generate_post import GeneratePost

from app.services.rabbit.rabbit_service import RabbitMQPublisher


async def process_post_manually(lot_id: int, site: str, user_uuid: str, message_id: int):
    try:
        async with ApiRpcClient() as api_client:
            response = await api_client.get_lot_by_vin_or_lot_id(str(lot_id), site)
            lot = response.lot[0]


        calculator = await GeneratePost.get_calculator_for_lot(lot)
        async with get_async_db() as db:
            filter_request_service = RequestFiltersService(db)
            request = await filter_request_service.create(RequestFiltersCreate(user_uuid=user_uuid, site=lot.base_site,
                                                                               make=lot.make, stage=RequestStage.COMPLETED))
            average_sell_price = await GeneratePost.get_average_price(lot)
            print(average_sell_price)
            post = await GeneratePost.create_post(lot, calculator, request.id, db, average_sell_price=average_sell_price)
        serialized = GeneratePost.generate_response_for_user([post])
        data = {
            'posts': serialized,
            'request_id': request.id,
            'message_id': message_id,
            'user_uuid': user_uuid
        }
        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.manually_generated_post', payload=data)
    except Exception as e:
        logger.exception(f"Error processing manual post: {e}")





