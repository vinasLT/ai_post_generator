from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.request_filters import RequestFiltersCreate
from app.services.lang_chain_agent.nodes import lot_chooser_agent_node, lot_chooser_tools, images_processing_agent, \
    choose_final_lots_node, tools_router, final_router
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.types import Filters

graph: StateGraph[AgentsState, Any, AgentsState, AgentsState] = StateGraph(AgentsState, context_schema=AgentsRuntimeContext)
graph.add_node("lot_chooser_agent", lot_chooser_agent_node)
graph.add_node("tools_node", ToolNode(lot_chooser_tools))
graph.add_node('image_processing', images_processing_agent)
graph.add_node("choose_final_lots", choose_final_lots_node)

graph.add_edge(START, "lot_chooser_agent")
graph.add_conditional_edges("lot_chooser_agent", tools_router, {"tools_node": "tools_node",
                                                                "process_image": "image_processing",
                                                                'end': END})
graph.add_edge("tools_node", "lot_chooser_agent")
graph.add_edge("image_processing", 'choose_final_lots')
graph.add_conditional_edges("choose_final_lots", final_router, {'more_lots_needed': 'lot_chooser_agent',
                                                                "end": END})
app = graph.compile()


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
            "min_lots_lot_chooser": 30,
            "max_lots_lot_chooser": 35,
            "lot_chooser_result": None,
        }
        context: AgentsRuntimeContext = {
            "user_uuid": request.user_uuid,
            "request_id": request.id,
            "result_lots_count": 30,
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

