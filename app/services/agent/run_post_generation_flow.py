import asyncio
import json
import traceback

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.post import PostUpdate
from app.database.schemas.request_filters import RequestFiltersCreate, RequestFiltersUpdate
from app.services.agent.ai_tools import edit_message_for_user, choose_lot_ids_from_lots
from app.services.agent.run import RunAgent
from app.services.agent.types import Filters
from app.services.ai_post_generation.generate_post import GeneratePost
from app.services.rabbit.rabbit_service import RabbitMQPublisher


async def run_post_generation_flow(filters: Filters, editable_message_id: str, user_uuid: str):
    logger.info("run_post_generation_flow:start", extra={"user_uuid": user_uuid, "editable_message_id": editable_message_id, "filters": filters.model_dump()})
    async with get_async_db() as db:
        filter_service = RequestFiltersService(db)
        last_request = await filter_service.get_last_request_for_user_uuid(user_uuid)
        if not last_request or last_request.stage in (RequestStage.FAILED, RequestStage.COMPLETED):
            request = await filter_service.create(RequestFiltersCreate(site=filters.site, make=filters.make, user_uuid=user_uuid, model=filters.model, year_from=filters.year_from, year_to=filters.year_to, odo_from=filters.odo_from, odo_to=filters.odo_to, document=filters.document, transmission=filters.transmission, status=filters.status, auction_date_from=filters.auction_date_from, auction_date_to=filters.auction_date_to, stage=RequestStage.IN_PROGRESS))
            logger.info("request_created", extra={"request_id": request.id, "user_uuid": user_uuid})
        else:
            await edit_message_for_user(editable_message_id, "❌ Please wait until your previous request will be completed", user_uuid)
            logger.warning("previous_request_in_progress", extra={"user_uuid": user_uuid, "last_request_id": last_request.id, "stage": last_request.stage.name})
            return
    try:
        start_prompt = f"Start searching with this filters: {filters.model_dump()}"
        logger.info("agent_run:start", extra={"user_uuid": user_uuid, "request_id": request.id})
        agent = RunAgent(editable_message_id, user_uuid)
        response, lots = await agent.run_agent_async(start_prompt)
        jsoned_response = json.loads(response)
        logger.info("agent_run:finished", extra={"user_uuid": user_uuid, "request_id": request.id, "lots_count": len(lots) if lots else 0, 'chose_lot_ids': jsoned_response.get('lot_ids', '')})

        is_error = jsoned_response.get("is_error")
        error_detail = jsoned_response.get("error_detail")
        if is_error:
            logger.error("agent_response_error", extra={"user_uuid": user_uuid, "request_id": request.id, "error_detail": error_detail, "raw_response": jsoned_response})
            async with get_async_db() as db:
                filter_service = RequestFiltersService(db)
                await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.FAILED))
            text = f"❌ En error occurred:\n{error_detail}"
            await edit_message_for_user(editable_message_id, text, user_uuid)
            return
        logger.info("choose_lots:start", extra={"user_uuid": user_uuid, "request_id": request.id})
        chosen_lots = choose_lot_ids_from_lots(lots, jsoned_response["lot_ids"])
        logger.info("choose_lots:finished", extra={"user_uuid": user_uuid, "request_id": request.id, "chosen_count": len(chosen_lots) if chosen_lots else 0})
        logger.info("calculators:start", extra={"user_uuid": user_uuid, "request_id": request.id})
        lots_with_calculator = await GeneratePost.get_calculators_for_lots(chosen_lots)
        logger.info("calculators:finished", extra={"user_uuid": user_uuid, "request_id": request.id})
        logger.info("create_posts_batch:start", extra={"user_uuid": user_uuid, "request_id": request.id})
        await GeneratePost.create_posts_batch(request.id, lots_with_calculator)
        async with get_async_db() as db:
            posts_service = PostService(db)
            for item in lots_with_calculator:
                avg = await GeneratePost.get_average_price(item[0])
                if avg:
                    post = await posts_service.get_by_request_id_and_lot_id(request.id, item[0].lot_id)
                    if post:
                        await posts_service.update(post.id, PostUpdate(average_sell_price=avg))
            await edit_message_for_user(editable_message_id, "✉️ Done! Sending Posts to you", user_uuid)
            logger.info("publish_to_rabbit:start", extra={"user_uuid": user_uuid, "request_id": request.id})
            await RabbitMQPublisher().publish(routing_key="posts_service.generated_posts", payload={"posts": GeneratePost.generate_response_for_user(list(await posts_service.get_by_request_id(request.id))), "user_uuid": user_uuid, "request_id": request.id})
            logger.info("publish_to_rabbit:finished", extra={"user_uuid": user_uuid, "request_id": request.id})
        async with get_async_db() as db:
            filter_service = RequestFiltersService(db)
            await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.COMPLETED))
            logger.info("request_completed", extra={"user_uuid": user_uuid, "request_id": request.id})
    except Exception as e:
        tb = traceback.format_exc()
        async with get_async_db() as db:
            filter_service = RequestFiltersService(db)
            await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.FAILED))
        logger.error("run_post_generation_flow:error", extra={"user_uuid": user_uuid, "request_id": request.id if 'request' in locals() else None, "error": str(e), "traceback": tb}, exc_info=True)
        text = "❌ En error occurred, try again"
        await edit_message_for_user(editable_message_id, text, user_uuid)


if __name__ == "__main__":
    async def main():
        await run_post_generation_flow(Filters(site="IAAI", make="BMW"), 1, "123456")
    asyncio.run(main())
