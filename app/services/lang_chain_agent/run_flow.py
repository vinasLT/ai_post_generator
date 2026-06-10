from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.core.logger import log_async_execution_time
from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.request_filters import RequestFiltersCreate
from app.services.lang_chain_agent.nodes import lot_chooser_agent_node, lot_chooser_tools, images_processing_agent, \
    choose_final_lots_node, tools_router, final_router, send_lots_to_user_node, send_error_node
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.types import Filters

MIN_LOTS_LOT_CHOOSER = 1
MAX_LOTS_LOT_CHOOSER = 35
FINAL_LOTS_COUNT = 35


def get_app() -> CompiledStateGraph[AgentsState, AgentsRuntimeContext]:
    graph: StateGraph[AgentsState, Any, AgentsState, AgentsState] = StateGraph(AgentsState,
                                                                               context_schema=AgentsRuntimeContext)
    graph.add_node("lot_chooser_agent", lot_chooser_agent_node)
    graph.add_node("tools_node", ToolNode(lot_chooser_tools))
    graph.add_node('image_processing', images_processing_agent)
    graph.add_node("choose_final_lots", choose_final_lots_node)
    graph.add_node("send_posts_to_user", send_lots_to_user_node)
    graph.add_node('send_error_handler', send_error_node)

    graph.add_edge(START, "lot_chooser_agent")
    graph.add_conditional_edges("lot_chooser_agent", tools_router, {"tools_node": "tools_node",
                                                                    "process_image": "image_processing",
                                                                    'send_error_to_user': 'send_error_handler'})
    graph.add_edge("tools_node", "lot_chooser_agent")
    graph.add_edge("image_processing", 'choose_final_lots')
    graph.add_conditional_edges("choose_final_lots", final_router, {'more_lots_needed': 'lot_chooser_agent',
                                                                    "send_posts_to_user": 'send_posts_to_user', "send_error_to_user": 'send_error_handler'})
    graph.add_edge("send_posts_to_user", END)
    graph.add_edge("send_error_handler", END)
    app = graph.compile()
    return app


@log_async_execution_time('Generate lots')
async def run_flow(filters: Filters, user_uuid: str, editable_message_id: int) -> AgentsState:
    app = get_app()

    async with get_async_db() as db:
        requests_service = RequestFiltersService(db)
        request = await requests_service.create(
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
                drive=filters.drive,
                auction_time=filters.auction_time,
                auction_date_from=filters.auction_date_from,
                auction_date_to=filters.auction_date_to,
                stage=RequestStage.IN_PROGRESS
            )
        )

    initial_state: AgentsState = {
        "filters": filters,
        "min_lots_lot_chooser": MIN_LOTS_LOT_CHOOSER,
        "max_lots_lot_chooser": MAX_LOTS_LOT_CHOOSER,
    }
    context: AgentsRuntimeContext = {
        "user_uuid": user_uuid,
        "request_id": request.id,
        "result_lots_count": FINAL_LOTS_COUNT,
        "editable_message_id": editable_message_id
    }

    try:
        result_state: AgentsState = await app.ainvoke(
            initial_state,
            context=context,
            recursion_limit=50
        )
        return result_state
    except Exception:
        async with get_async_db() as db:
            post_service = PostService(db)
            await post_service.delete_all_posts_for_request(request.id)
            requests_service = RequestFiltersService(db)
            await requests_service.set_request_stage(request.id, RequestStage.FAILED)
        raise











if __name__ == "__main__":
    async def main() -> None:
        start_time = asyncio.get_event_loop().time()
        async with get_async_db() as db:
            requests_service = RequestFiltersService(db)
            request = await requests_service.create(RequestFiltersCreate(
                site="IAAI", make="BMW", user_uuid="0b340a37-8b89-4b57-adad-0fa1941cf193",
                stage=RequestStage.IN_PROGRESS)
            )

        initial_state: AgentsState = {
            "messages": [],
            "filters": Filters(site="IAAI", make="BMW"),
            "min_lots_lot_chooser": MIN_LOTS_LOT_CHOOSER,
            "max_lots_lot_chooser": MAX_LOTS_LOT_CHOOSER,
            "lot_chooser_result": None,
        }
        context: AgentsRuntimeContext = {
            "user_uuid": request.user_uuid,
            "request_id": request.id,
            "result_lots_count": FINAL_LOTS_COUNT,
        }

        result_state: AgentsState = await app.ainvoke(
            initial_state,
            context=context,
            recursion_limit=50,
            config=RunnableConfig(configurable={"context": context}),
        )

        end_time = asyncio.get_event_loop().time()
        print(f"--- {end_time - start_time} seconds ---")
        print(f"--- {(end_time - start_time) / 60} minutes ---")
        print(result_state.get("final_lot_ids"))


    import asyncio

    asyncio.run(main())

