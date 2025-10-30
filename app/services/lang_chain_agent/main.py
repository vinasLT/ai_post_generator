import json
from typing import Any, List, TypedDict, Optional
from typing_extensions import Annotated

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import StructuredTool

from app.config import settings
from app.services.lang_chain_agent.schemas import get_agent_result_parser, AgentResult, get_best_lot_chooser_schema
from app.services.lang_chain_agent.tools import make_get_page_of_lots, get_instructions

MODEL = getattr(settings, "OPENAI_MODEL", "gpt-5-nano")


class AgentsState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_uuid: str
    min_lots: int | None
    max_lots: int | None
    lot_chooser_result: AgentResult | None
    best_picked_lots: AgentResult | None


llm = ChatOpenAI(model=MODEL, reasoning_effort="low", api_key=settings.OPENAI_API_KEY, use_responses_api=True)
image_processor_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=settings.OPENAI_API_KEY, use_responses_api=True)


async def lot_chooser_agent(state: AgentsState) -> dict[str, Any]:
    min_lots = state.get("min_lots") or 30
    max_lots = state.get("max_lots") or 60
    schema: type[BaseModel] = get_agent_result_parser(min_lots, max_lots)
    structured_llm = llm.with_structured_output(schema)
    system = SystemMessage(content=get_instructions("main_agent.txt"))
    tools: List[StructuredTool] = [make_get_page_of_lots(state["user_uuid"])]
    history: List[BaseMessage] = [system] + state["messages"]
    ai = await llm.bind_tools(tools).ainvoke(history)
    if getattr(ai, "tool_calls", None):
        return {"messages": [ai]}
    correction_guard = SystemMessage(content="If you receive validation feedback, you must correct your answer to satisfy the response schema exactly and return only the fixed object.")
    feedback_messages: List[HumanMessage] = []
    attempts = 3
    last_error: Optional[str] = None
    for _ in range(attempts):
        try:
            parsed: AgentResult = await structured_llm.ainvoke(history + [ai, correction_guard] + feedback_messages)
            ai_msg = AIMessage(content=parsed.model_dump_json())
            return {"messages": [ai_msg], "lot_chooser_result": parsed}
        except Exception as e:
            print(e)
            last_error = str(e)
            feedback = HumanMessage(content=f"Validation failed: {last_error}. Fix it now. Ensure lot_ids are unique integers with length between {min_lots} and {max_lots}. Return only the corrected object that matches the schema exactly.")
            feedback_messages.append(feedback)
    error_payload = AgentResult(lots=None, is_error=True, error_detail=f"Schema validation failed after {attempts} attempts: {last_error}")
    ai_msg = AIMessage(content=error_payload.model_dump_json())
    return {"messages": [ai_msg], "lot_chooser_result": error_payload}


async def tools_node(state: AgentsState) -> dict[str, Any]:
    tools: List[StructuredTool] = [make_get_page_of_lots(state["user_uuid"])]
    node = ToolNode(tools=tools)
    return await node.ainvoke(state)


def tools_router(state: AgentsState) -> str | None:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools_node"
    return "choose_best_lots_agent"


async def choose_best_lots_agent(state: AgentsState) -> dict[str, Any]:
    agent_results = state["lot_chooser_result"]
    if agent_results is None or agent_results.is_error:
        return {}
    lot_ids = agent_results.lot_ids
    serialized = json.dumps(lot_ids)
    schema: type[BaseModel] = get_best_lot_chooser_schema()
    structured_llm = llm.with_structured_output(schema)
    system = SystemMessage(content=get_instructions("main_agent.txt"))
    prompt = HumanMessage(content=f"Filter the list of lot ids and return only the best valid ones as per the schema: {serialized}")
    best = await structured_llm.ainvoke([system, prompt])
    return {"best_picked_lots": best}


graph = StateGraph(AgentsState)
graph.add_node("lot_chooser_agent", lot_chooser_agent)
graph.add_node("tools_node", tools_node)
graph.add_node("choose_best_lots_agent", choose_best_lots_agent)

graph.add_edge(START, "lot_chooser_agent")
graph.add_conditional_edges("lot_chooser_agent", tools_router, {"tools_node": "tools_node", "choose_best_lots_agent": "choose_best_lots_agent"})
graph.add_edge("tools_node", "lot_chooser_agent")
graph.add_edge("choose_best_lots_agent", END)

app = graph.compile()


if __name__ == "__main__":
    async def main():
        result = await app.ainvoke({
            "messages": [
                HumanMessage(content="Find the best lots from IAAI, make: BMW, i need only 5 lots")
            ],
            "user_uuid": "0b340a37-8b89-4b57-adad-0fa1941cf193",
            "min_lots": 5,
            "max_lots": 5
        })
        print(result.get("lot_chooser_result"))
        print(result.get("best_picked_lots"))

    import asyncio
    asyncio.run(main())
