import ast
import json
from enum import Enum

from aio_pika.abc import AbstractIncomingMessage

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db, get_db
from app.database.schemas.post import PostUpdate
from app.database.schemas.request_filters import RequestFiltersCreate
from app.services.ai_post_generation.generate_post import GeneratePost
from app.services.ai_post_generation.types import Filters
from app.services.rabbit.consumer_base import RabbitBaseService
from app.services.rabbit.rabbit_service import RabbitMQPublisher
from app.services.rabbit.types import RabbitChatBotTextMessage, RabbitChatBotImageMessage


class PostsRoutingKeys(str, Enum):
    POSTS_GENERATE_WITH_FILTERS = "posts_bot.generate_post.with_filters"
    CHAT_BOT_GENERATED_TEXT = 'ai_chat_bot.generated.text'
    CHAT_BOT_GENERATED_ON_IMAGE = 'ai_chat_bot.generated.image.text'


class RabbitPostsConsumer(RabbitBaseService):
    async def process_message(self, message: AbstractIncomingMessage):
        message_data = message.body.decode("utf-8")
        payload = json.loads(message_data).get("payload")
        routing_key = message.routing_key

        logger.info(f"Received new message", extra={"payload": payload})

        if routing_key in PostsRoutingKeys:
            route = PostsRoutingKeys(routing_key)
        else:
            return

        if route == PostsRoutingKeys.POSTS_GENERATE_WITH_FILTERS:
            async with get_async_db() as db:
                request_filters_service = RequestFiltersService(db)

                request = await request_filters_service.create(RequestFiltersCreate(
                    user_uuid=payload.get("user_uuid"),
                    **payload.get("filters")
                ))
                generator = GeneratePost(Filters.model_validate(payload.get("filters", {})), request.id)

                await generator.generate_post()

        elif route == PostsRoutingKeys.CHAT_BOT_GENERATED_TEXT:
            async with get_async_db() as db:
                post_service = PostService(db)
                data = RabbitChatBotTextMessage.model_validate(payload)
                jsoned_data = ast.literal_eval(data.response)
                lots = jsoned_data.get('lots')
                lot_ids = [lot.get('lot_id') for lot in lots]
                left_lots = await post_service.left_only_this_lot_ids(data.request_id, lot_ids)
                for lot in left_lots:
                    publisher = RabbitMQPublisher()
                    await publisher.connect()
                    await publisher.publish('post_generator.generate_response.image', {'assistant_name': 'lot_images_processor',
                                 'request_id': data.request_id, 'image_urls': lot.images.split(','), 'lot_id': lot.lot_id})
                    await publisher.close()

        elif route == PostsRoutingKeys.CHAT_BOT_GENERATED_ON_IMAGE:
            async with get_async_db() as db:
                post_service = PostService(db)
                data = RabbitChatBotImageMessage.model_validate(payload)
                posts = await post_service.get_by_request_id_and_lot_id(data.request_id, data.lot_id)
                jsoned_data = ast.literal_eval(data.response)
                description = jsoned_data.get('description')
                score = jsoned_data.get('condition_score')
                for post in posts:
                    await post_service.update(post.id, PostUpdate(image_score=score, image_description=description))

                all_posts = await post_service.get_by_request_id(data.request_id)
                with_image_description = 0
                for post in all_posts:
                    if post.image_description:
                        with_image_description += 1

                if len(all_posts) == with_image_description:
                    publisher = RabbitMQPublisher()
                    await publisher.connect()
                    await publisher.publish('post_generator.generate_response.text',
                                            {'prompt': serialized_lots, 'assistant_name': 'lot_chooser',
                                             'request_id': self.request_id})
                    await publisher.close()
















