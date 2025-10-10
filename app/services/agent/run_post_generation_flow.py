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


def _format_for_log(value: Any, limit: int = 500) -> str:
    try:
        text_repr = repr(value)
    except Exception:
        try:
            text_repr = str(value)
        except Exception:
            text_repr = "<unprintable>"
    if len(text_repr) > limit:
        return f"{text_repr[:limit]}...(truncated)"
    return text_repr


def _safe_json_loads(x: Any, context: str = "") -> Dict[str, Any]:
    log_context = f" ({context})" if context else ""
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception as exc:
            logger.warning(
                f"Failed to deserialize agent response{log_context}: {exc}",
                extra={"raw_excerpt": _format_for_log(x)},
            )
            return {"raw": x}
    logger.warning(
        f"Agent response had unexpected type{log_context}: {type(x).__name__}",
        extra={"raw_excerpt": _format_for_log(x)},
    )
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
            logger.info(
                f"Created new request {created.id} for user {user_uuid} with filters: {filters.model_dump(exclude_none=True)}"
            )
            return created.id
        logger.info(
            f"Rejecting new request for user {user_uuid} because request {last_req.id} is still {last_req.stage}"
        )
        return None


async def _set_stage(request_id: int, stage: RequestStage) -> None:
    async with get_async_db() as db:
        service = RequestFiltersService(db)
        logger.debug(f"Updating request {request_id} stage to {stage}")
        updated = await service.update(request_id, RequestFiltersUpdate(stage=stage))
        if updated:
            logger.debug(f"Request {request_id} stage persisted as {updated.stage}")
        else:
            logger.warning(f"Request {request_id} not found when attempting to set stage to {stage}")


async def _finalize_success(request_id: int, editable_message_id: str, user_uuid: str, lots_with_calc: List[Tuple[Any, Any]]) -> None:
    async with get_async_db() as db:
        posts_service = PostService(db)
        logger.info(f"Finalizing successful post generation for request {request_id} with {len(lots_with_calc)} lots")
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
    logger.info(f"Request {request_id} marked as completed")


async def run_post_generation_flow(filters: Filters, editable_message_id: str, user_uuid: str) -> None:
    request_id = await _create_or_reject_request(filters, user_uuid)
    if not request_id:
        logger.info(f"User {user_uuid} attempted to start a new post generation flow while a previous one is still active")
        await edit_message_for_user(editable_message_id, "❌ Please wait until your previous request will be completed", user_uuid)
        return

    logger.info(f"Starting post generation flow for request {request_id} (user {user_uuid}) with filters: {filters.model_dump(exclude_none=True)}")
    raw_response_excerpt = None
    payload: Dict[str, Any] = {}

    try:
        start_prompt = f"Start searching with this filters: {filters.model_dump()}"
        logger.debug(f"Prepared agent prompt for request {request_id}: {_format_for_log(start_prompt)}")
        agent = RunAgent(editable_message_id, user_uuid)
        response, lots = await agent.run_agent_async(start_prompt)
        raw_response_excerpt = _format_for_log(response)
        logger.debug(f"Agent raw response for request {request_id}: {raw_response_excerpt}")
        payload = _safe_json_loads(response, context=f"request_id={request_id}")

        payload_summary = {key: payload.get(key) for key in ("is_error", "error_detail", "error", "message", "lot_ids", "raw") if key in payload}
        logger.debug(f"Agent payload for request {request_id}: {_format_for_log(payload_summary)}")
        if "raw" in payload:
            logger.warning(
                f"Agent response for request {request_id} returned raw fallback payload",
                extra={"raw_excerpt": _format_for_log(payload.get("raw"))},
            )

        is_error = bool(payload.get("is_error"))
        error_detail = payload.get("error_detail") or payload.get("error") or payload.get("message")
        if is_error:
            logger.error(
                f"Agent returned error for request {request_id}: {error_detail}",
                extra={"request_id": request_id, "user_uuid": user_uuid, "payload_summary": _format_for_log(payload_summary)},
            )
            await _set_stage(request_id, RequestStage.FAILED)
            await edit_message_for_user(editable_message_id, f"❌ En error occurred:\n{error_detail}", user_uuid)
            return

        lot_ids = payload.get("lot_ids") or []
        if not isinstance(lot_ids, list):
            logger.warning(
                f"Agent lot_ids payload for request {request_id} is of type {type(lot_ids).__name__}; expected list",
                extra={"request_id": request_id, "payload_summary": _format_for_log(payload_summary)},
            )
            lot_ids = []
        lot_count = len(lots or [])
        logger.debug(f"Request {request_id} received {lot_count} lots and {len(lot_ids)} lot ids from agent")
        if not lots or not lot_ids:
            logger.warning(
                f"Missing lots or lot_ids for request {request_id}; marking request as failed",
                extra={"request_id": request_id, "lot_count": lot_count, "lot_ids_excerpt": _format_for_log(lot_ids)},
            )
            await _set_stage(request_id, RequestStage.FAILED)
            await edit_message_for_user(editable_message_id, "❌ En error occurred, try again", user_uuid)
            return

        chosen_lots = choose_lot_ids_from_lots(lots, lot_ids)
        logger.debug(f"Chosen {len(chosen_lots)} lots after filtering agent output for request {request_id}")
        lots_with_calc = await GeneratePost.get_calculators_for_lots(chosen_lots)
        logger.debug(f"Fetched calculators for {len(lots_with_calc)} lots for request {request_id}")
        await GeneratePost.create_posts_batch(request_id, lots_with_calc)
        logger.info(f"Posts batch stored for request {request_id} with {len(lots_with_calc)} lots")
        await _finalize_success(request_id, editable_message_id, user_uuid, lots_with_calc)

    except Exception as e:
        try:
            await _set_stage(request_id, RequestStage.FAILED)
        except Exception as stage_exc:
            logger.exception(
                f"Failed to update request stage to FAILED for request {request_id}",
                extra={"request_id": request_id, "stage_error": str(stage_exc)},
            )
        logger.exception(
            f"Error while posts generation occurred for request {request_id}: {str(e)}",
            extra={
                "request_id": request_id,
                "user_uuid": user_uuid,
                "raw_agent_response": raw_response_excerpt,
                "payload_excerpt": _format_for_log(payload),
            },
        )
        await edit_message_for_user(editable_message_id, "❌ En error occurred, try again", user_uuid)


if __name__ == "__main__":
    async def main():
        await run_post_generation_flow(Filters(site="IAAI", make="BMW"), "1", "123456")
    asyncio.run(main())
