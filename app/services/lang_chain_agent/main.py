from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.request_filters import RequestFiltersCreate
from app.services.agent.types import Filters
from app.services.lang_chain_agent.nodes.choose_best_lots_node import choose_best_lots_agent
from app.services.lang_chain_agent.nodes.images_processing_node import images_processing_agent
from app.services.lang_chain_agent.nodes.lot_chooser_node import lot_chooser_agent_node, tools_router, lot_chooser_tools
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext


graph: StateGraph[AgentsState, Any, AgentsState, AgentsState] = StateGraph(AgentsState, context_schema=AgentsRuntimeContext)
graph.add_node("lot_chooser_agent", lot_chooser_agent_node)
graph.add_node("tools_node", ToolNode(lot_chooser_tools))
graph.add_node("choose_best_lots_agent", choose_best_lots_agent)

graph.add_node('image_processing', images_processing_agent)

graph.add_edge(START, "lot_chooser_agent")
graph.add_conditional_edges("lot_chooser_agent", tools_router, {"tools_node": "tools_node",
                                                                "choose_best_lots_agent": "choose_best_lots_agent",
                                                                'end': END})
graph.add_edge("tools_node", "lot_chooser_agent")
graph.add_edge("choose_best_lots_agent", "image_processing")
graph.add_edge("image_processing", END)

app = graph.compile()


if __name__ == "__main__":
    async def main() -> None:
        async with get_async_db() as db:
            requests_service = RequestFiltersService(db)
            request = await requests_service.create(RequestFiltersCreate(
                site="IAAI", make="BMW", user_uuid="0b340a37-8b89-4b57-adad-0fa1941cf193",
                stage=RequestStage.IN_PROGRESS)
            )

        initial_state: AgentsState = {
            "messages": [],
            "filters": Filters(site="IAAI", make="BMW"),
            "min_lots_lot_chooser": 2,
            "max_lots_lot_chooser": 2,
            "min_best_picked_lots": 2,
            "max_best_picked_lots": 2,
            "lot_chooser_result": None,
            "best_picked_lots": None,
        }
        context: AgentsRuntimeContext = {
            "user_uuid": request.user_uuid,
            "request_id": request.id,
            "result_lots_count": 30,
        }

        result_state: AgentsState = await app.ainvoke(
            initial_state,
            context=context,
            config=RunnableConfig(configurable={"context": context}),
        )
        print(result_state.get("lot_chooser_result"))
        print(result_state.get("best_picked_lots"))
        print(result_state['lots_images_descriptions'])


    import asyncio
    asyncio.run(main())
