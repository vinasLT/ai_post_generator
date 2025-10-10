import json
from enum import Enum

from aio_pika.abc import AbstractIncomingMessage

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.schemas.post import PostUpdate
from app.services.ai_post_generation.new_ai_generation import GeneratePosts
from app.services.ai_post_generation.post_serializer import SerializePost
from app.services.agent.types import Filters
from app.services.generate_post_manually import process_post_manually
from app.services.rabbit.consumer_base import RabbitBaseService
from app.services.rabbit.rabbit_service import RabbitMQPublisher


class PostsRoutingKeys(str, Enum):
    POSTS_GENERATE_WITH_FILTERS = "posts_bot.generate_post.with_filters"
    POSTS_PUBLISH_POST = "posts_bot.publish_post"
    POST_GENERATE_MANUALLY = "posts_bot.generate_post.manually"



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
            generator = GeneratePosts(Filters.model_validate(payload.get("filters", {})), payload.get("user_uuid"))
            await generator.run()

        elif route == PostsRoutingKeys.POST_GENERATE_MANUALLY:
            lot_id = payload.get("lot_id")
            site = payload.get("site")
            user_uuid = payload.get("user_uuid")
            message_id = payload.get("message_id")
            print(payload)
            await process_post_manually(lot_id, site, user_uuid, message_id)

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
                    payload={"text": text, 'images': post.images.split(',')[:3]}
                )




















