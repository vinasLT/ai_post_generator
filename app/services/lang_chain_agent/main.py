from typing import Any, List, TypedDict, Optional
from typing_extensions import Annotated
import json

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, BaseMessage

from app.config import settings
from app.services.agent.ai_tools import get_instructions
from app.services.lang_chain_agent.tools import make_get_page_of_lots

MODEL = getattr(settings, "OPENAI_MODEL", "gpt-5-nano")

class AgentsState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_uuid: str
    tool_outputs: Optional[List[dict]]

llm = ChatOpenAI(model=MODEL, api_key=settings.OPENAI_API_KEY)

async def agent1_node(state: AgentsState) -> dict[str, Any]:
    system = SystemMessage(content=get_instructions("main_agent.txt"))
    tool = make_get_page_of_lots(state["user_uuid"])
    resp = await llm.bind_tools([tool]).ainvoke([system] + state["messages"])
    return {"messages": [resp]}

def route_after_agent1(state: AgentsState) -> str:
    if not state["messages"]:
        return "agent2"
    last = state["messages"][-1]
    if isinstance(last, AIMessage):
        tool_calls = getattr(last, "tool_calls", []) or []
        if tool_calls:
            return "tools_exec"
    return "agent2"

async def tools_exec_node(state: AgentsState) -> dict[str, Any]:
    tool = make_get_page_of_lots(state["user_uuid"])
    tool_node = ToolNode(tools=[tool])
    msgs = await tool_node.ainvoke(state["messages"])
    return {"messages": msgs}

def collect_tool_outputs_node(state: AgentsState) -> dict[str, Any]:
    outputs: List[dict] = list(state.get("tool_outputs") or [])
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                print(data)
                if isinstance(data, dict):
                    outputs.append(data)
                elif isinstance(data, list):
                    outputs.extend([x for x in data if isinstance(x, dict)])
                else:
                    outputs.append({"content": data})
            except Exception:
                outputs.append({"content": msg.content})
            break
    return {"tool_outputs": outputs}

def agent2_node(state: AgentsState) -> dict[str, Any]:
    payload = {
        "verified": True,
        "results": state.get("tool_outputs", []) or []
    }
    return {"messages": [AIMessage(content=json.dumps(payload, ensure_ascii=False))]}

graph = StateGraph(AgentsState)
graph.add_node("agent1", agent1_node)
graph.add_node("tools_exec", tools_exec_node)
graph.add_node("collect_tool_outputs", collect_tool_outputs_node)
graph.add_node("agent2", agent2_node)

graph.add_edge(START, "agent1")
graph.add_conditional_edges("agent1", route_after_agent1, {"tools_exec": "tools_exec", "agent2": "agent2"})
graph.add_edge("tools_exec", "collect_tool_outputs")
graph.add_edge("collect_tool_outputs", "agent1")
graph.add_edge("agent2", END)

app = graph.compile()

if __name__ == "__main__":
    async def main():


        result = await app.ainvoke({
            "messages": [
                {"role": "user", "content": "Find the best lots from IAAI, make: BMW"}
            ],
            "user_uuid": "0b340a37-8b89-4b57-adad-0fa1941cf193",
            "tool_outputs": []
        })

        print(result)

    import asyncio
    asyncio.run(main())
