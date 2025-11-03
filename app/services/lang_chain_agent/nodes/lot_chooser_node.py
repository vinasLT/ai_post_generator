import json
from typing import Any

from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel

from app.config import settings

from app.services.lang_chain_agent.schemas import get_agent_result_parser, AgentResult
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions, get_page_of_lots

llm = ChatOpenAI(model='gpt-5-mini', reasoning_effort="medium", api_key=settings.OPENAI_API_KEY, use_responses_api=True)

lot_chooser_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_instructions}"),
        MessagesPlaceholder(variable_name="history"),
        (
            "human",
            "You must pick best lots using this filters: {filters}"
            "You must return this amount of lots - from {min_lots} to {max_lots}"
        ),
    ]
)

lot_chooser_tools: list[BaseTool] = [get_page_of_lots]

async def lot_chooser_agent_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> dict[str, Any]:
    min_lots = state["min_lots_lot_chooser"]
    max_lots = state["max_lots_lot_chooser"]

    print(min_lots, max_lots)

    response_schema: type[BaseModel] = get_agent_result_parser(min_lots, max_lots)
    structured_llm = llm.with_structured_output(response_schema)

    system_instructions = get_instructions("main_agent.txt")
    prompt_messages: list[BaseMessage] = lot_chooser_prompt.invoke(
        {
            "system_instructions": system_instructions,
            "history": state["messages"],
            "filters": state["filters"].model_dump(mode="json"),
            "min_lots": min_lots,
            "max_lots": max_lots,
        }
    ).to_messages()


    ai = await llm.bind_tools(lot_chooser_tools).ainvoke(prompt_messages)

    # if the model calls tool -> tools_node
    if getattr(ai, "tool_calls", None):
        return {"messages": [ai]}

    correction_guard = SystemMessage(content="If you receive validation feedback, you must correct your answer to satisfy the response schema exactly and return only the fixed object.")
    feedback_messages: list[HumanMessage] = []
    attempts = 3
    last_error: str | None = None
    for _ in range(attempts):
        try:
            parsed: AgentResult = await structured_llm.ainvoke(prompt_messages + [ai, correction_guard] + feedback_messages)
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



def tools_router(state: AgentsState) -> str | None:
    messages = state.get("messages", [])
    if not messages:
        return "choose_best_lots_agent"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools_node"
    elif isinstance(last, HumanMessage):
        data = json.loads(last.content)
        if data.get('is_error'):
            return 'end'
    return "choose_best_lots_agent"
