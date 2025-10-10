import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

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


def _safe_json_loads(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {"raw": x}
    return {"raw": x}


async def _create_or_reject_request(filters: Filters, user_uuid: str) -> Optional[int]:
    async with get_async_db() as db:
        service = RequestFiltersService(db)
        last_req = await service.get_last_request_for_user_uuid(user_uuid)
        if not last_req or last_req.stage in {RequestStage.FAILED, RequestStage.COMPLETED}:
            created = await service.create(
                RequestFiltersCreate(
                    site=filters.site,
                    make=filters.make,
                    user_uuid=user_uuid,
                    model=filters.model,
                    year_from=filters.year_from,
                    year_to=filters.year_to,
                    odo_from=filters.odo_from,
                    odo_to=filters.odo_to,
                    document=filters.document,
                    transmission=filters.transmission,
                    status=filters.status,
                    auction_date_from=filters.auction_date_from,
                    auction_date_to=filters.auction_date_to,
                    stage=RequestStage.IN_PROGRESS,
                )
            )
            return created.id
        return None


async def _set_stage(request_id: int, stage: RequestStage) -> None:
    async with get_async_db() as db:
        service = RequestFiltersService(db)
        await service.update(request_id, RequestFiltersUpdate(stage=stage))


async def _finalize_success(request_id: int, editable_message_id: str, user_uuid: str, lots_with_calc: List[Tuple[Any, Any]]) -> None:
    async with get_async_db() as db:
        posts_service = PostService(db)
        for item in lots_with_calc:
            avg = await GeneratePost.get_average_price(item[0])
            if avg:
                post = await posts_service.get_by_request_id_and_lot_id(request_id, item[0].lot_id)
                if post:
                    await posts_service.update(post.id, PostUpdate(average_sell_price=avg))
        await edit_message_for_user(editable_message_id, "✉️ Done! Sending Posts to you", user_uuid)
        await RabbitMQPublisher().publish(
            routing_key="posts_service.generated_posts",
            payload={
                "posts": GeneratePost.generate_response_for_user(list(await posts_service.get_by_request_id(request_id))),
                "user_uuid": user_uuid,
                "request_id": request_id,
            },
        )
    await _set_stage(request_id, RequestStage.COMPLETED)


async def run_post_generation_flow(filters: Filters, editable_message_id: str, user_uuid: str) -> None:
    request_id = await _create_or_reject_request(filters, user_uuid)
    if not request_id:
        await edit_message_for_user(editable_message_id, "❌ Please wait until your previous request will be completed", user_uuid)
        return

    try:
        start_prompt = f"Start searching with this filters: {filters.model_dump()}"
        agent = RunAgent(editable_message_id, user_uuid)
        response, lots = await agent.run_agent_async(start_prompt)
        payload = _safe_json_loads(response)

        is_error = bool(payload.get("is_error"))
        error_detail = payload.get("error_detail") or payload.get("error") or payload.get("message")
        if is_error:
            logger.error(f"Error while posts generation occurred (response from agent): {error_detail}")
            await _set_stage(request_id, RequestStage.FAILED)
            await edit_message_for_user(editable_message_id, f"❌ En error occurred:\n{error_detail}", user_uuid)
            return

        lot_ids = payload.get("lot_ids") or []
        if not isinstance(lot_ids, list):
            lot_ids = []
        if not lots or not lot_ids:
            await _set_stage(request_id, RequestStage.FAILED)
            await edit_message_for_user(editable_message_id, "❌ En error occurred, try again", user_uuid)
            return

        chosen_lots = choose_lot_ids_from_lots(lots, lot_ids)
        lots_with_calc = await GeneratePost.get_calculators_for_lots(chosen_lots)
        await GeneratePost.create_posts_batch(request_id, lots_with_calc)
        await _finalize_success(request_id, editable_message_id, user_uuid, lots_with_calc)

    except Exception as e:
        try:
            await _set_stage(request_id, RequestStage.FAILED)
        except Exception:
            pass
        logger.exception(f"Error while posts generation occurred: {str(e)}")
        await edit_message_for_user(editable_message_id, "❌ En error occurred, try again", user_uuid)


if __name__ == "__main__":
    async def main():
        await run_post_generation_flow(Filters(site="IAAI", make="BMW"), "1", "123456")
    asyncio.run(main())
