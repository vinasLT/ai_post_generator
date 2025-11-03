from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from app.config import settings
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions

choose_best_lots_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_instructions}"),
        (
            "human",
            "Here is the list of candidate lots in JSON format:\n{lot_chooser_result}"
        ),
        (
            "human",
            "You must only remove worst few lots from the result you got based on its description"
            "You must return this amount of lots - from {min_lots} to {max_lots}"
        ),
    ]
)

llm = ChatOpenAI(model='gpt-5-mini', reasoning_effort="medium", api_key=settings.OPENAI_API_KEY, use_responses_api=True)


async def choose_best_lots_agent(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> dict[str, Any]:
    min_lots = state["min_best_picked_lots"]
    max_lots = state["max_best_picked_lots"]
    agent_results = state.get("lot_chooser_result")
    if agent_results is None or agent_results.is_error:
        return {}
    serialized = [lot.model_dump() for lot in agent_results.lots]


    class ResponseSchema(BaseModel):
        lot_ids: list[int] = Field(
            ...,
            min_length=min_lots,
            max_length=max_lots,
            description="Lot IDs of vehicles that you choose (ONLY UNIQUE VALUES)"
        )
    structured_llm = llm.with_structured_output(ResponseSchema)

    prompt = choose_best_lots_prompt.invoke(
        {
            'system_instructions': get_instructions('main_agent.txt'),
            'lot_chooser_result': serialized,
            'min_lots': min_lots,
            "max_lots": max_lots,
        }
    ).to_messages()

    best: ResponseSchema = await structured_llm.ainvoke(prompt)

    async with get_async_db() as db:
        post_service = PostService(db)
        await post_service.left_only_this_lot_ids(request_filter_id=runtime.context["request_id"], lot_ids=best.lot_ids)

    ai_msg = AIMessage(content=best.model_dump_json())
    return {"best_picked_lots": best, 'messages': [ai_msg]}
