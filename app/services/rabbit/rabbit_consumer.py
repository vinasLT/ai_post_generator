import base64
import json
from enum import Enum

from aio_pika.abc import AbstractIncomingMessage

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.database.schemas.post import PostUpdate
from app.services.lang_chain_agent import run_flow
from app.services.generate_post_manually import process_post_manually
from app.services.image_post_generator.generator import build_post
from app.services.lang_chain_agent.serializer import SerializePost
from app.services.lang_chain_agent.types import Filters
from app.services.lang_chain_agent.utils import GeneratePostUtils
from app.services.rabbit.consumer_base import RabbitBaseService
from app.services.rabbit.rabbit_service import RabbitMQPublisher


class PostsRoutingKeys(str, Enum):
    POSTS_GENERATE_WITH_FILTERS = "posts_bot.generate_post.with_filters"
    POSTS_PUBLISH_POST = "posts_bot.publish_post"
    POST_GENERATE_MANUALLY = "posts_bot.generate_post.manually"
    POST_GENERATE_MANUALLY_ADD_COMMENT = "posts_bot.generate_post.manually.add_comment"
    POST_GENERATE_MANUALLY_IMAGE = "posts_bot.generate_post.manually.generate_image"



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
            filters = payload.get("filters")
            user_uuid = payload.get("user_uuid")
            editable_message_id = payload.get("editable_message_id")
            await run_flow(Filters(**filters), user_uuid, editable_message_id)

        elif route == PostsRoutingKeys.POST_GENERATE_MANUALLY_IMAGE:
            post_id = payload.get("post_id")
            editable_message_id = payload.get("editable_message_id")
            user_uuid = payload.get("user_uuid")
            async with get_async_db() as db:
                post_service = PostService(db)
                post = await post_service.get(post_id)
                images = post.images.split(',')
                text = SerializePost(post).serialize(for_image=True)
                image = build_post(images[:3], text, font_size=30, line_h=40)
                await RabbitMQPublisher().publish(
                    routing_key="posts_service.image_generated",
                    payload={"image": base64.b64encode(image).decode("ascii"), 'message_id': editable_message_id,
                             'post_id': post_id, 'user_uuid': user_uuid, 'request_id': post.request_id,}
                )




        elif route == PostsRoutingKeys.POST_GENERATE_MANUALLY_ADD_COMMENT:
            post_id = payload.get("post_id")
            comment = payload.get('comment')
            user_uuid = payload.get('user_uuid')
            editable_message_id = payload.get('editable_message_id')
            async with get_async_db() as db:
                post_service = PostService(db)
                post = await post_service.get(post_id)
                await post_service.update(post_id, PostUpdate(comment=comment))
                serialized = GeneratePostUtils.generate_response_for_user([post])

                data = {
                    'posts': serialized,
                    'request_id': post.request_id,
                    'message_id': editable_message_id,
                    'user_uuid': user_uuid
                }

                async with RabbitMQPublisher() as publisher:
                    await publisher.publish(routing_key='posts_service.manually_generated_post', payload=data)





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




















