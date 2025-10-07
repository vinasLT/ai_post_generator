import ast
import asyncio
from typing import Any, Generator, AsyncGenerator, Coroutine

from dateutil import parser
import grpc
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger, log_async_execution_time, async_timer
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.enums import AuctionEnum
from app.database.models import Post
from app.database.schemas.post import PostCreate, PostUpdate
from app.rpc_client.auction_api import ApiRpcClient
from app.rpc_client.calculator import CalculatorRcpClient
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2
from app.rpc_client.gen.python.calculator.v1.calculator_pb2 import GetCalculatorWithDataResponse
from app.services.ai_post_generation.ai_service import Transformers
from app.services.ai_post_generation.post_serializer import SerializePost
from app.services.ai_post_generation.types import Filters
from app.services.rabbit.rabbit_service import RabbitMQPublisher


class GeneratePost:
    def __init__(self, filters: Filters, request_id: int, user_uuid: str):
        self.filters = filters
        self.user_uuid = user_uuid
        self.request_id = request_id
        self.auction_api_client = ApiRpcClient()

    async def _get_search_results_from_api(self, page: int = 1)-> lot_pb2.GetCurrentLotsByFiltersResponse | None:
        try:
            async with self.auction_api_client as client:
                return await client.get_current_lots_with_filters(
                    self.filters,
                    page=page
                )
        except grpc.aio.AioRpcError as e:
            logger.error(f'Error getting search results from api for request: {self.request_id}',
                         extra={'error_code': str(e.code()), 'error_details': str(e.details())})
    @classmethod
    async def get_calculator_for_lot(cls, lot: lot_pb2.Lot) -> calculator_pb2.GetCalculatorWithDataResponse | None:
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
    @log_async_execution_time('Get calculator for lots')
    async def get_calculators_for_lots(self, lots: list[lot_pb2.Lot]) -> list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]]:
        lots_with_calculators = []

        async def get_calculator(lot: lot_pb2.Lot) -> None:
            try:
                calculator = await self.get_calculator_for_lot(lot)
                if calculator:
                    lots_with_calculators.append((lot, calculator))
            except Exception as e:
                logger.error(f"Error getting calculator for lot {lot.lot_id}: {str(e)}")

        tasks = [asyncio.create_task(get_calculator(lot)) for lot in lots]
        await asyncio.gather(*tasks)

        return lots_with_calculators

    async def process_repeated_posts(self, lots: list[lot_pb2.Lot]) -> list[lot_pb2.Lot]:
        async with get_async_db() as db:
            post_service = PostService(db)
            lot_ids_with_calculator = [lot.lot_id for lot in lots]
            repeated_posts_lot_ids = await post_service.get_repeated_posts(lot_ids_with_calculator, return_ids=True)
            logger.debug(f'Repeated posts IDs: {repeated_posts_lot_ids}')
            logger.debug(f'Repeated posts IDs types: {[type(x) for x in repeated_posts_lot_ids]}')
            logger.debug(f'First lot ID: {lots[0].lot_id}, type: {type(lots[0].lot_id)}')
            return self.exclude_lots_by_lot_ids(repeated_posts_lot_ids, lots)


    @classmethod
    async def create_post(cls, lot: lot_pb2.Lot, calculator: calculator_pb2.GetCalculatorWithDataResponse,
                          request_id: int, db: AsyncSession, flush: bool = False, average_sell_price: int = None) -> Post | None:
        post_service = PostService(db)
        try:
            post = await post_service.create(PostCreate(
                lot_id=lot.lot_id,
                auction=AuctionEnum(lot.base_site),
                title=lot.title,
                odometer=lot.odometer,
                vin=lot.vin,
                status=lot.status,
                year=lot.year,
                auction_date=parser.parse(lot.auction_date) if lot.auction_date else None,
                delivery_price=calculator.data.calculator.transportation_price[0].price,
                shipping_price=calculator.data.calculator.ocean_ship[0].price,
                average_sell_price=average_sell_price,
                request_id=request_id,
                images=','.join(list(lot.link_img_hd)[:10])
            ), flush=flush)
        except Exception as e:
            logger.error(f"Error processing lot {lot.lot_id} to DB: {e}")
            return None
        return post


    async def create_posts_batch(
            self,
            lots_with_calculators: list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]]
    ) -> list[lot_pb2.Lot]:
        processed_lots = []

        async with get_async_db() as db:
            for lot_calculator_pair in lots_with_calculators:
                lot, calculator = lot_calculator_pair
                try:
                    post = await self.create_post(lot, calculator, self.request_id, db, flush=True)
                    if post:
                        processed_lots.append(post)
                except Exception as e:
                    logger.error(f"Error processing lot {lot.lot_id} to DB: {e}")

            await db.commit()

        return processed_lots

    async def left_only_this_lot_ids_db(self, lot_ids: list[int])-> list[Post]:
        async with get_async_db() as db:
            post_service = PostService(db)
            return await post_service.left_only_this_lot_ids(self.request_id, lot_ids)

    async def process_lots_with_calculator_and_db(self, lots: list[lot_pb2.Lot]):
        unique_lots = await self.process_repeated_posts(lots)
        lots_with_calculator = await self.get_calculators_for_lots(unique_lots)

        processed_lots = await self.create_posts_batch(lots_with_calculator)
        return processed_lots

    @classmethod
    async def serialize_response_from_assistant(cls, response: dict[str, Any]) -> dict[str, Any]:
        if response.get('data') and response.get('data').get('response'):
            serialized_lots_data: dict[str, Any] = ast.literal_eval(response.get('data').get('response'))
        return serialized_lots_data

    @classmethod
    @log_async_execution_time('Request to ai assistant')
    async def request_to_ai_assistant(cls, prompt: str, assistant_name: str, route: str, timeout: int = 30)-> dict[str, Any]:
        async with RabbitMQPublisher() as publisher:
            response = await publisher.publish_and_wait_response(route,
                                                                 {
                                                                     'prompt': prompt,
                                                                     'assistant_name': assistant_name
                                                                 },
                                                                 timeout=timeout
                                                                 )
            return await cls.serialize_response_from_assistant(response)

    @log_async_execution_time('Send batch request to ai assistant')
    async def send_batch_request_to_ai_assistant(self, tasks: list[dict[str, Any]], timeout: int = 30):
        logger.debug(f'Tasks: len {len(tasks)}, sending to ai assistant')
        async with RabbitMQPublisher() as publisher:
            responses = await publisher.send_multiple_rpc_requests(tasks, timeout=timeout)
            return [await self.serialize_response_from_assistant(response) for response in responses]


    def left_lots_by_lot_ids(self, lot_ids: list[int], lots: list[lot_pb2.Lot]) -> list[lot_pb2.Lot]:
        left_lots = []
        for lot in lots:
            if lot.lot_id in lot_ids:
                left_lots.append(lot)
        return left_lots

    def exclude_lots_by_lot_ids(self, lot_ids_to_exclude: list[int], lots: list[lot_pb2.Lot]) -> list[lot_pb2.Lot]:
        excluded_lots = []
        lot_ids_to_exclude_set = set(int(x) for x in lot_ids_to_exclude)

        for lot in lots:
            if int(lot.lot_id) not in lot_ids_to_exclude_set:
                excluded_lots.append(lot)
        return excluded_lots

    @classmethod
    def generate_response_for_user(cls, posts: list[Post])-> list[dict[str, Any]]:
        posts_serialized = []
        for post in posts:
            post_serializer = SerializePost(post)
            text = post_serializer.serialize()
            images = post_serializer.get_images()
            link = post_serializer.generate_link()
            posts_serialized.append({'text': text, 'images': images, 'link': link, 'post_id': post.id})

        return posts_serialized


    async def send_response_to_user(self, posts: list[Post]):
        serialized = self.generate_response_for_user(posts)
        data = {
            'posts': serialized,
            'request_id': self.request_id,
            'user_uuid': self.user_uuid
        }
        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.generated_posts', payload=data)
    @classmethod
    async def get_average_price(cls, lot: lot_pb2.Lot) -> int | None:
        async with ApiRpcClient() as client:
            year_from = None
            year_to = None
            if lot.year:
                year_from = lot.year - 1
                year_to = lot.year + 1
            response = await client.get_average_price(lot.make, lot.model,
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


    async def send_error_to_user(self, error_message: str):
        error_message += f'\nSearch for make: {self.filters.make}'

        async with RabbitMQPublisher() as publisher:
            await publisher.publish(routing_key='posts_service.error', payload={
                'error_message': error_message,
                'request_id': self.request_id,
                'user_uuid': self.user_uuid
            })
        pass

    @log_async_execution_time('Post page processing')
    async def process_lots_page(self, lots: list[lot_pb2.Lot]):
        try:
            lots_after_ai_processing, lots_with_calculator = await self._process_lots_with_ai(lots)
            if not lots_after_ai_processing:
                logger.error(f'AI text chooser didnt find any suitable lots for request: {self.request_id}',)
                return None

            lots_with_descriptions = await self._process_lot_images(lots_after_ai_processing)
            if not lots_with_descriptions:
                logger.error(f'No lots with descriptions for request: {self.request_id}',
                             extra={'request_id': self.request_id})
                return None

            final_lots = await self._get_final_processed_lots(lots_with_descriptions)
            if not final_lots:
                logger.error(f'No final lots after processing for request: {self.request_id}',
                             extra={'request_id': self.request_id})
                return None

            final_lots_with_calculator = [
                (lot, calc) for lot, calc in lots_with_calculator
                if lot.lot_id in final_lots
            ]
            await self.create_posts_batch(final_lots_with_calculator)

            lots_index = {lot.lot_id: lot for lot in lots_after_ai_processing if lot.lot_id in final_lots}
            await self._update_average_prices(final_lots, lots_index)

            return lots_index
        except Exception as e:
            logger.error(f'Error in generate_post for request: {self.request_id}',
                         exc_info=True, extra={'request_id': self.request_id})
            await self.send_error_to_user(f'Error generating post: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return None

    async def api_search_generator(self) -> AsyncGenerator[list[Lot], None]:
        search_results = await self._get_search_results_from_api(page=1)
        pages = search_results.pagination.pages
        logger.debug(f'Pages available: {pages}')
        yield list(search_results.lot)

        pages_to_process = min(pages, 20)
        for page in range(2, pages_to_process + 1):
            result = await self._get_search_results_from_api(page=page)
            lots = list(result.lot)
            yield lots

    @log_async_execution_time('Generate posts')
    async def generate_post(self):
        try:
            semaphore = asyncio.Semaphore(5)
            processing_tasks = []

            async def process_and_send_page(lots, page_num):
                async with semaphore:
                    logger.debug(f'Processing page {page_num} for request: {self.request_id}')

                    lots_index = await self.process_lots_page(lots)

                    if not lots_index:
                        logger.debug(f'No results from page {page_num}')
                        return 0

                    page_lot_ids = list(lots_index.keys())
                    posts = await self.left_only_this_lot_ids_db(page_lot_ids)

                    if posts:
                        logger.info(f'Sending {len(posts)} posts from page {page_num} to user')
                        await self.send_response_to_user(posts)
                        return len(posts)

                    return 0

            page_num = 0
            async for lots in self.api_search_generator():
                page_num += 1
                unique_lots = await self.process_repeated_posts(lots)

                if len(unique_lots) < 10:
                    logger.debug(f'Skipping page {page_num} with only {len(unique_lots)} unique lots')
                    continue

                # Добавляем задачу на обработку страницы
                task = asyncio.create_task(process_and_send_page(unique_lots, page_num))
                processing_tasks.append(task)

            # Ждем завершения всех задач
            results = await asyncio.gather(*processing_tasks, return_exceptions=True)

            # Подсчитываем успешно отправленные посты
            total_posts_sent = sum(r for r in results if isinstance(r, int))
            errors = [r for r in results if isinstance(r, Exception)]

            if errors:
                logger.warning(f'Some pages failed to process: {len(errors)} errors')

            logger.info(f'Completed generation. Total posts sent: {total_posts_sent} for request: {self.request_id}')

        except Exception as e:
            logger.error(f'Error in generate_post_parallel for request: {self.request_id}',
                         extra={'request_id': self.request_id, 'error': str(e)})
            await self.send_error_to_user(f'Error generating posts: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return None


    async def _fetch_unique_lots(self, page: int = 1):
        try:
            async with async_timer('get api results'):
                search_results = await self._get_search_results_from_api(page=page)
                logger.debug(f'Found {len(search_results.lot)} lots for page {page}')

            if len(search_results.lot) == 0:
                logger.error(f'No lots found for request: {self.request_id}', extra={'request_id': self.request_id})
                await self.send_error_to_user(f'No lots found, change filters\n'
                                              f'request id: {self.request_id}')
                return None

            all_lots = list(search_results.lot)
            unique_lots = await self.process_repeated_posts(all_lots)

            current_page = search_results.pagination.page
            while len(unique_lots) < 14 and search_results.pagination.pages > current_page + 1:
                current_page += 1
                try:
                    async with async_timer(f'get api results for page {current_page}'):
                        search_results_next_page = await self._get_search_results_from_api(page=current_page)
                        logger.debug(f'Found {len(search_results_next_page.lot)} lots on page {current_page}')

                        unique_lots = await self.process_repeated_posts(list(search_results_next_page.lot))
                        search_results = search_results_next_page
                except Exception as e:
                    logger.error(f'Error fetching page {current_page} for request: {self.request_id}',
                                 exc_info=True, extra={'request_id': self.request_id})
                    break

            if not unique_lots:
                logger.error(f'No unique lots remain for request: {self.request_id}',
                             extra={'request_id': self.request_id})
                await self.send_error_to_user(f'No unique lots remain, change filters for get new lots\n'
                                              f'request id: {self.request_id}')
                return None

            logger.debug(f'Unique lots: {len(unique_lots)}')
            return unique_lots
        except Exception as e:
            logger.error(f'Error in _fetch_unique_lots for request: {self.request_id}',
                        extra={'request_id': self.request_id, 'error': str(e)})
            await self.send_error_to_user(f'Error fetching lots: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return None

    async def _process_lots_with_ai(self, unique_lots, max_retries=3, retry_delay=2)-> tuple[list[Lot], list[tuple[
        Lot, GetCalculatorWithDataResponse]] | None] | None:
        try:
            serialized_lots = Transformers.transform_lot_for_ai(unique_lots)

            async with async_timer('get calculator and process lots with ai chooser'):
                calculator_task = self.get_calculators_for_lots(unique_lots)

                response_from_ai_chooser = None
                for attempt in range(max_retries):
                    try:
                        ai_chooser_task = self.request_to_ai_assistant(
                            serialized_lots,
                            'lot_chooser',
                            'post_generator.generate_response.text',
                            timeout=120
                        )

                        responses = await asyncio.gather(calculator_task, ai_chooser_task)
                        calculator_task = asyncio.create_task(asyncio.sleep(0))  # Fake task for next iterations

                        response_from_ai_chooser = responses[1]
                        lots_from_ai_chooser = response_from_ai_chooser.get('lots', [])

                        if lots_from_ai_chooser and len(lots_from_ai_chooser) > 0:
                            logger.info(
                                f'AI chooser returned {len(lots_from_ai_chooser)} lots on attempt {attempt + 1}')
                            break
                        else:
                            logger.warning(f'AI chooser returned no lots on attempt {attempt + 1}/{max_retries}')
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                            else:
                                logger.error(f'AI chooser failed to return lots after {max_retries} attempts')
                                response_from_ai_chooser = {'lots': []}

                    except Exception as e:
                        logger.error(f'Error in AI chooser attempt {attempt + 1}/{max_retries}: {str(e)}')
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                        else:
                            raise

                lots_with_calculator = responses[0] if attempt == 0 else await self.get_calculators_for_lots(
                    unique_lots)

            lots_from_calculator = [lot.lot_id for lot, calculator in lots_with_calculator]

            lots_from_ai_chooser = response_from_ai_chooser.get('lots', [])
            lot_ids = [lot.get('lot_id') for lot in lots_from_ai_chooser]

            lots_filtered = self.left_lots_by_lot_ids(lots_from_calculator, unique_lots)
            logger.debug(f'Lots with calculator: {len(lots_filtered)}')

            return (self.left_lots_by_lot_ids(lot_ids, lots_filtered),
                    lots_with_calculator)

        except Exception as e:
            logger.error(f'Error in _process_lots_with_ai for request: {self.request_id}',
                         exc_info=True, extra={'request_id': self.request_id})
            await self.send_error_to_user(f'Error processing lots with AI: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return None

    async def _process_lot_images(self, lots_after_ai_chooser):
        try:
            async with async_timer('get image description'):
                tasks = []
                for lot in lots_after_ai_chooser:
                    tasks.append({
                        'service_queue': 'ai_chat_bot_service',
                        'action': 'post_generator.generate_response.image',
                        'data': {
                            "image_urls": list(lot.link_img_hd)[:7],
                            'assistant_name': 'lot_images_processor',
                            'lot_id': lot.lot_id
                        }
                    })

                image_description_responses = await self.send_batch_request_to_ai_assistant(tasks, timeout=240)

            lots_index = {lot.lot_id: lot for lot in lots_after_ai_chooser}
            lots_with_image_description = []

            for response in image_description_responses:
                lot_id = response.get('lot_id')
                if lot_id and lot_id in lots_index:
                    lot_obj = lots_index[lot_id]
                    lots_with_image_description.append({
                        "lot": lot_obj,
                        "description": response.get('description', ''),
                        "score": response.get('condition_score', 0)
                    })

            return lots_with_image_description
        except Exception as e:
            logger.error(f'Error in _process_lot_images for request: {self.request_id}',
                         exc_info=True, extra={'request_id': self.request_id})
            await self.send_error_to_user(f'Error processing lot images: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return []

    async def _get_final_processed_lots(self, lots_with_image_description):
        try:
            serialized_lots_with_image_description = Transformers.transform_lot_for_ai_images(
                lots_with_image_description)

            async with async_timer('get full lot processor response'):
                full_lot_processor_response = await self.request_to_ai_assistant(
                    serialized_lots_with_image_description,
                    'full_lot_processor',
                    'post_generator.generate_response.text',
                    timeout=90
                )

            return [lot.get('lot_id') for lot in full_lot_processor_response.get('lots', []) if lot]
        except Exception as e:
            logger.error(f'Error in _get_final_processed_lots for request: {self.request_id}',
                         exc_info=True, extra={'request_id': self.request_id})
            await self.send_error_to_user(f'Error getting final processed lots: {str(e)}\n'
                                          f'request id: {self.request_id}')
            return []

    async def _update_average_prices(self, final_lot_ids, lots_index):
        try:
            async with async_timer('update average sell price'):
                for lot_id in final_lot_ids:
                    try:
                        lot = lots_index[lot_id]
                        average_price = await self.get_average_price(lot)

                        async with get_async_db() as db:
                            posts_service = PostService(db)
                            post = await posts_service.get_by_lot_id(lot_id)
                            await posts_service.update(post.id, PostUpdate(average_sell_price=average_price))
                    except Exception as e:
                        logger.error(f'Error updating average price for lot {lot_id}, request: {self.request_id}',
                                     exc_info=True, extra={'request_id': self.request_id, 'lot_id': lot_id})
                        continue
        except Exception as e:
            logger.error(f'Error in _update_average_prices for request: {self.request_id}',
                         exc_info=True, extra={'request_id': self.request_id})
            await self.send_error_to_user(f'Error updating average prices: {str(e)}\n'
                                          f'request id: {self.request_id}')






if __name__ == "__main__":

    post_generator = GeneratePost(filters=Filters())

    print(asyncio.run(post_generator.generate()))

