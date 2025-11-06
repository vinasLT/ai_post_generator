from langgraph.runtime import Runtime

from app.core.logger import log_async_execution_time
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.utils import GeneratePostUtils

@log_async_execution_time('Sending lots to user')
async def send_lots_to_user_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]):
    final_lot_ids = state.get("final_lot_ids", [])
    request_id = runtime.context["request_id"]
    user_uuid = runtime.context["user_uuid"]
    async with get_async_db() as db:
        requests_service = PostService(db)
        posts = await requests_service.left_only_this_lot_ids(request_filter_id=request_id, lot_ids=final_lot_ids)

        posts = await GeneratePostUtils.update_average_price_for_posts(posts)

    await GeneratePostUtils.edit_message_for_user(
        message_id=runtime.context['editable_message_id'],
        text="Sending your lots...",
        user_uuid=user_uuid
    )
    await GeneratePostUtils.send_response_to_user(posts, request_id, user_uuid)