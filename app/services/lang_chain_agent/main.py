from typing import Any

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage

from app.config import settings

MODEL = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")

@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

llm = ChatOpenAI(model=MODEL, api_key=settings.OPENAI_API_KEY)

def agent1_node(state: MessagesState) -> dict[str, Any]:
    system = SystemMessage(content="You are a math solver. Prefer calling tools for any arithmetic.")
    resp = llm.bind_tools([add]).invoke([system] + state["messages"])
    return {"messages": [resp]}

def agent2_node(state: MessagesState) -> dict[str, Any]:
    system = SystemMessage(content="You are a verifier and formatter. Verify all results and return one concise final answer.")
    resp = llm.invoke([system] + state["messages"])
    return {"messages": [resp]}

graph = StateGraph(MessagesState)
graph.add_node("agent1", agent1_node)
graph.add_node("tools", ToolNode([add]))
graph.add_node("agent2", agent2_node)

graph.add_edge(START, "agent1")

# КЛЮЧЕВОЕ: используем END как ключ, а не строку "end"
graph.add_conditional_edges(
    "agent1",
    tools_condition,
    {"tools": "tools", END: "agent2"}
)

graph.add_edge("tools", "agent1")
graph.add_edge("agent2", END)

app = graph.compile()

result = app.invoke({
    "messages": [
        {"role": "user", "content": "What is 43565 + 23425 and 23543 + 5467? Use the tool for arithmetic, then produce a single final answer."}
    ]
})

print(result)
