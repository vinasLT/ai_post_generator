import ast
import asyncio
from typing import Any, Coroutine
from dateutil import parser
import grpc
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.enums import AuctionEnum
from app.database.schemas.post import PostCreate
from app.rpc_client.auction_api import ApiRpcClient
from app.rpc_client.calculator import CalculatorRcpClient
from app.rpc_client.chat_bot import ChatBotRpcClient
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2
from app.rpc_client.gen.python.chat_bot.v1 import chat_bot_pb2
from app.services.ai_post_generation.ai_service import Transformers
from app.services.ai_post_generation.types import Filters
from app.services.rabbit.rabbit_service import RabbitMQPublisher


class GeneratePost:
    def __init__(self, filters: Filters, request_id: int):
        self.filters = filters
        self.request_id = request_id
        self.auction_api_client = ApiRpcClient()

    async def _get_search_results_from_api(self)-> lot_pb2.GetCurrentLotsByFiltersResponse | None:
        async with self.auction_api_client as client:

            return await client.get_current_lots_with_filters(
                self.filters
            )


    @classmethod
    async def _check_calculator(cls, lots: RepeatedCompositeFieldContainer[lot_pb2.Lot]) -> list[Any]:
        lots_with_calculator = []
        for lot in lots:
            async with CalculatorRcpClient() as client:
                try:
                    response = await client.get_calculator_with_data(
                        price=100,
                        auction=AuctionEnum(lot.base_site.lower()),
                        vehicle_type=lot.vehicle_type,
                        location=lot.location
                    )
                    if response:
                        lots_with_calculator.append({'lot': lot, 'calculator': response})
                except grpc.aio.AioRpcError as e:
                    logger.warning(f'For lot: {lot.lot_id} data for calculator was not found (Rpc Request)',
                                   extra={'error_code': str(e.code()), 'error_details': str(e.details())})
                    continue
        return lots_with_calculator

    async def get_calculator_for_lot(self, lot: lot_pb2.Lot) -> calculator_pb2.GetCalculatorWithDataResponse | None:
        async with CalculatorRcpClient() as client:
            try:
                response = await client.get_calculator_with_data(
                    price=100,
                    auction=AuctionEnum(lot.base_site.lower()),
                    vehicle_type=lot.vehicle_type,
                    location=lot.location
                )
                return response
            except grpc.aio.AioRpcError as e:
                logger.warning(f'For lot: {lot.lot_id} data for calculator was not found (Rpc Request)',
                               extra={'error_code': str(e.code()), 'error_details': str(e.details())})
                return None

    async def generate_post(self):
        time_start = asyncio.get_running_loop().time()
        search_results = await self._get_search_results_from_api()
        logger.debug(f'Found {len(search_results.lot)} lots')
        if len(search_results.lot) == 0:
            return ""

        lots_with_calculator = []
        async with get_async_db() as db:
            post_service = PostService(db)

            for lot in search_results.lot:
                calculator = await self.get_calculator_for_lot(lot)
                if not calculator:
                    continue
                if not await post_service.get_by_lot_id(lot.lot_id):
                    await post_service.create(PostCreate(
                        lot_id=lot.lot_id,
                        auction=AuctionEnum(lot.base_site),
                        title=lot.title,
                        odometer=lot.odometer,
                        vin=lot.vin,
                        status=lot.status,
                        auction_date=parser.parse(lot.auction_date) if lot.auction_date else None,
                        delivery_price=calculator.data.calculator.transportation_price[0].price,
                        shipping_price=calculator.data.calculator.ocean_ship[0].price,
                        average_sell_price=None,
                        request_id=self.request_id,
                        images=','.join(list(lot.link_img_hd)[:10])
                    ))
                lots_with_calculator.append(lot)

            serialized_lots = Transformers.transform_lot_for_ai(lots_with_calculator)


            async with RabbitMQPublisher() as publisher:
                response = await publisher.publish_and_wait_response('post_generator.generate_response.text',
                                                                     {
                                                                         'prompt': serialized_lots,
                                                                         'assistant_name': 'lot_chooser'
                                                                     },
                                                                     timeout=30
                                                                     )
                response = ast.literal_eval(response.get('data').get('response'))
                lots = response.get('lots')
                lot_ids = [lot.get('lot_id') for lot in lots]
                await post_service.left_only_this_lot_ids(self.request_id, lot_ids)

                tasks = []
                for lot_id in lot_ids:
                    lot = next((lot for lot in search_results.lot if lot.lot_id == lot_id), None)
                    if lot:
                        tasks.append({'service_queue': 'ai_chat_bot_service',
                                      'action': 'post_generator.generate_response.image',
                                      'data': {"image_urls": list(lot.link_img_hd)[:10],
                                               'assistant_name': 'lot_images_processor', 'lot_id': lot.lot_id}
                                      }
                                     )

                responses = await publisher.send_multiple_rpc_requests(tasks, timeout=60)


                lots_with_image_description = []
                for response in responses:
                    if response.get('data') and response.get('data').get('response'):
                        data = ast.literal_eval(response.get('data').get('response'))
                        lot_id = response.get('data').get('lot_id')

                        lot_obj = next((lot for lot in search_results.lot if lot.lot_id == lot_id), None)
                        if lot_obj:
                            lots_with_image_description.append({
                                "lot": lot_obj,
                                "description": data.get('description', ''),
                                "score": data.get('condition_score', 0)
                            })



                serialized_lots_with_image_description = Transformers.transform_lot_for_ai_images(lots_with_image_description)
                print(serialized_lots_with_image_description)

                response = await publisher.publish_and_wait_response('post_generator.generate_response.text',
                                                                     {
                                                                         'prompt': serialized_lots_with_image_description,
                                                                         'assistant_name': 'full_lot_processor'
                                                                     },
                                                                     timeout=30
                                                                     )

                print(response)
                time_end = asyncio.get_running_loop().time()
                print(f'Time: {time_end - time_start}')
                return lots_with_image_description













    async def choose_lots_with_calculator(self):
        search_results = await self._get_search_results_from_api()
        logger.debug(f'Found {len(search_results.lot)} lots')
        if len(search_results.lot) == 0:
            return ""
        lots_with_calculator = []
        async with get_async_db() as db:
            post_service = PostService(db)

            for lot in search_results.lot:
                calculator = await self.get_calculator_for_lot(lot)
                if not calculator:
                    continue
                print(lot.auction_date)
                if not await post_service.get_by_lot_id(lot.lot_id):
                    await post_service.create(PostCreate(
                        lot_id=lot.lot_id,
                        auction=AuctionEnum(lot.base_site),
                        title=lot.title,
                        odometer=lot.odometer,
                        vin=lot.vin,
                        status=lot.status,
                        auction_date=parser.parse(lot.auction_date) if lot.auction_date else None,
                        delivery_price=calculator.data.calculator.transportation_price[0].price,
                        shipping_price=calculator.data.calculator.ocean_ship[0].price,
                        average_sell_price=None,
                        request_id=self.request_id,
                        images= ','.join(list(lot.link_img_hd)[:10])
                    ))
                lots_with_calculator.append(lot)


        serialized_lots = Transformers.transform_lot_for_ai(lots_with_calculator)

        publisher = RabbitMQPublisher()
        await publisher.connect()
        await publisher.publish('post_generator.generate_response.text', {'prompt': serialized_lots, 'assistant_name': 'lot_chooser',
                                 'request_id': self.request_id})
        await publisher.close()


    async def process_lots_images(self, lots: list[lot_pb2.Lot]):
        semaphore = asyncio.Semaphore(5)

        async def process_lot_images(lot):
            async with semaphore:
                logger.debug(f'Processing images for lot: {lot.lot_id}')
                try:
                    description_response = await self._request_to_ai_on_image(list(lot.link_img_hd), "lot_images_processor")
                    logger.debug(f'Images for lot: {lot.lot_id} processed', extra=description_response.response)
                    return {
                        'lot': lot,
                        'description': ast.literal_eval(description_response.response)
                    }
                except grpc.aio.AioRpcError as e:
                    logger.error(f'For lot: {lot.lot_id} error occurred while processing images',
                                   extra={'error_code': str(e.code()), 'error_details': str(e.details())})
                    return None
                except Exception as e:
                    logger.error(f'For lot: {lot.lot_id} error occurred while processing images', extra={'error_details': str(e)})

        tasks = [process_lot_images(lot) for lot in lots]
        return await asyncio.gather(*tasks)






if __name__ == "__main__":

    post_generator = GeneratePost(filters=Filters())

    print(asyncio.run(post_generator.generate()))

