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
from app.services.ai_post_generation.post_serializer import SerializePost
from app.services.ai_post_generation.types import Filters
from app.services.rabbit.consumer_base import RabbitBaseService
from app.services.rabbit.rabbit_service import RabbitMQPublisher
from app.services.rabbit.types import RabbitChatBotTextMessage, RabbitChatBotImageMessage


class PostsRoutingKeys(str, Enum):
    POSTS_GENERATE_WITH_FILTERS = "posts_bot.generate_post.with_filters"
    POSTS_PUBLISH_POST = "posts_bot.publish_post"



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
                generator = GeneratePost(Filters.model_validate(payload.get("filters", {})), request.id, payload.get("user_uuid"))

                await generator.generate_post()
        elif route == PostsRoutingKeys.POSTS_PUBLISH_POST:
            post_id = payload.get("post_id")
            async with get_async_db() as db:
                post_service = PostService(db)
                post = await post_service.get(post_id)
                await post_service.update(post_id, PostUpdate(is_posted=True))
                serializer = SerializePost(post)
                text = serializer.serialize()
                await RabbitMQPublisher().publish(
                    routing_key="posts_service.publish_post",
                    payload={"text": text, 'images': post.images.split(',')}
                )




















