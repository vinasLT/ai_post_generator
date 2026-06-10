from langgraph.runtime import Runtime

from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.utils import GeneratePostUtils


async def send_error_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]):
    error_message = state.get("error_message")
    request_id = runtime.context["request_id"]
    async with get_async_db() as db:
        post_service = PostService(db)
        await post_service.delete_all_posts_for_request(request_id)
        requests_service = RequestFiltersService(db)
        await requests_service.set_request_stage(request_id, RequestStage.FAILED)
    await GeneratePostUtils.send_error_to_user(
        request_id=request_id,
        user_uuid=runtime.context["user_uuid"],
        error_message=error_message
    )