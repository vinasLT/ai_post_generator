import json
from typing import Any

from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel

from app.config import settings
from app.core.logger import log_async_execution_time
from app.database.crud.post import PostService
from app.database.db.session import get_async_db

from app.services.lang_chain_agent.schemas import get_agent_result_parser, AgentResult
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions, get_page_of_lots
from app.services.lang_chain_agent.utils import GeneratePostUtils

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

@log_async_execution_time('Choosing lots')
async def lot_chooser_agent_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> dict[str, Any]:
    min_lots = state["min_lots_lot_chooser"]
    max_lots = state["max_lots_lot_chooser"]

    is_need_more_lots = state.get("is_need_more_lots")
    if is_need_more_lots:
        min_lots = state.get("lots_needed", 5) + 2
        max_lots = state.get("lots_needed", 5) + 5
        await GeneratePostUtils.edit_message_for_user(
            message_id=runtime.context["editable_message_id"],
            text="🔄 Choosing more lots for you...\n"
                 f"⏳ This phase usually takes {round(0.18 * ((min_lots + max_lots) / 2), 2)} min\n"
                 "▶️ Approximately 5-7 min left",
            user_uuid=runtime.context["user_uuid"],
        )
    else:
        await GeneratePostUtils.edit_message_for_user(
            message_id=runtime.context["editable_message_id"],
            text="🔄 Choosing the best lots for you...\n"
                 f"⏳ This phase usually takes {round(0.18 * ((min_lots + max_lots) / 2), 2)} min\n"
                 "▶️ Approximately 8-10 min left",
            user_uuid=runtime.context["user_uuid"],
        )

    response_schema: type[BaseModel] = get_agent_result_parser(min_lots, max_lots)
    structured_llm = llm.with_structured_output(response_schema)
    system_instructions = get_instructions("main_agent.md")

    base_messages: list[BaseMessage] = lot_chooser_prompt.invoke(
        {
            "system_instructions": system_instructions,
            "history": state["messages"],
            "filters": state["filters"].model_dump(mode="json"),
            "min_lots": min_lots,
            "max_lots": max_lots,
        }
    ).to_messages()

    correction_guard = SystemMessage(content="If you receive validation feedback, you must correct your answer to satisfy the response schema exactly and return only the fixed object.")
    feedback_messages: list[HumanMessage] = []
    attempts = 3
    messages: list[BaseMessage] = list(base_messages)

    for _ in range(attempts):
        ai = await llm.bind_tools(lot_chooser_tools).ainvoke(messages)

        if getattr(ai, "tool_calls", None):
            return {"messages": [ai]}

        parsed = await structured_llm.ainvoke(messages + [ai, correction_guard] + feedback_messages)

        if parsed.is_error:
            err = parsed.error_message
            ai_err = AIMessage(content=parsed.model_dump_json())
            return {"is_error": True, "error_message": err, "messages": [ai_err], "lot_chooser_result": parsed}

        ai_msg = AIMessage(content=parsed.model_dump_json())
        chose_lot_ids = [lot.lot_id for lot in parsed.lots]
        all_cumulated_lot_ids = chose_lot_ids + state.get("cumulated_chose_lot_ids", [])

        try:
            async with get_async_db() as db:
                post_service = PostService(db)
                posts = await post_service.left_only_this_lot_ids(
                    request_filter_id=runtime.context["request_id"], lot_ids=all_cumulated_lot_ids
                )
        except Exception as e:
            return {"is_error": True, "error_message": str(e)}

        if len(posts) < min_lots:
            error_message = HumanMessage(content="Not enough existing lots. Use tools to fetch another page and provide only existing lot_ids.")
            feedback_messages.append(error_message)
            messages = list(base_messages) + [ai, correction_guard] + feedback_messages
            continue

        return {
            "messages": [ai_msg],
            "lot_chooser_result": parsed,
            "chose_lot_ids": chose_lot_ids,
            "cumulated_chose_lot_ids": all_cumulated_lot_ids,
            "cumulated_lots": parsed.lots + state.get("cumulated_lots", []),
        }

    fallback_nudge = HumanMessage(
        content="You could not satisfy the schema yet. Call the available tools now to fetch or refine lots, then return a corrected object strictly matching the schema."
    )

    try:
        ai_final = await llm.bind_tools(lot_chooser_tools).ainvoke(list(base_messages) + [correction_guard] + feedback_messages + [fallback_nudge])
    except Exception as e:
        return {"is_error": True, "error_message": str(e)}

    if getattr(ai_final, "tool_calls", None):
        return {"messages": [ai_final]}

    try:
        parsed_final = await structured_llm.ainvoke(list(base_messages) + [correction_guard] + feedback_messages + [fallback_nudge])
        if parsed_final.is_error:
            err = parsed_final.error_message
            ai_err = AIMessage(content=parsed_final.model_dump_json())
            return {"is_error": True, "error_message": err, "messages": [ai_err], "lot_chooser_result": parsed_final}
    except Exception:
        pass

    return {"is_error": True, "error_message": f"Schema validation failed after {attempts} attempts"}



def tools_router(state: AgentsState) -> str | None:
    messages = state.get("messages", [])
    is_error = state.get("is_error", False)
    if not messages:
        return "process_image"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools_node"
    elif is_error:
        return 'send_error_to_user'
    return "process_image"
