from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from app.config import settings
from app.core.logger import log_async_execution_time
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions
from app.services.lang_chain_agent.utils import GeneratePostUtils

llm = ChatOpenAI(model='gpt-5-mini', reasoning_effort='medium', api_key=settings.OPENAI_API_KEY, use_responses_api=True)


def _build_choose_final_lots_messages(
    final_agent_messages: list,
    descriptions_for_lots: str,
    final_lots_amount: int,
) -> list:
    return [
        SystemMessage(content=get_instructions('choose_final_lots.md')),
        *final_agent_messages,
        HumanMessage(
            content=(
                "Choose the best lots based on the following descriptions:\n"
                f"{descriptions_for_lots}\n\n"
                f"You must return up to {final_lots_amount} lots, ordered from best to worst.\n"
                "Return every suitable lot you find, even if the count is below the maximum.\n"
                "Do not request more inventory; send the best available lots from the list below."
            )
        ),
    ]


@log_async_execution_time('Choose final lots')
async def choose_final_lots_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> AgentsState:
    await GeneratePostUtils.edit_message_for_user(
        message_id=runtime.context['editable_message_id'],
        text="🔄 Final choosing phase...\n"
             "▶️ Approximately 2-4 min left",
        user_uuid=runtime.context['user_uuid']
    )
    image_descriptions = state['cumulated_images_description']
    lot_chooser_result = state['cumulated_lots']
    final_agent_messages = state.get('final_agent_messages', [])

    descriptions_for_lots_raw = []
    for img_desc in image_descriptions:
        for lot in lot_chooser_result:
            if lot.lot_id == img_desc.lot_id:
                descriptions_for_lots_raw.append(
                    f"# Lot ID: {lot.lot_id}\n"
                    f"Image Description: {img_desc.descriptions.description}\n"
                    f"Image Good Aspects: {img_desc.descriptions.good_aspect}\n"
                    f"Image Bad Aspects: {img_desc.descriptions.bad_aspect}\n"
                    f"Lot Description: {lot.description}\n"
                )
                break

    descriptions_for_lots = "\n\n".join(descriptions_for_lots_raw)
    if not descriptions_for_lots_raw:
        return {
            "is_error": True,
            "error_message": "No lots with image descriptions available for final selection.",
        }

    max_target = runtime.context["result_lots_count"]
    final_lots_amount = min(len(descriptions_for_lots_raw), max_target)

    messages = _build_choose_final_lots_messages(
        final_agent_messages,
        descriptions_for_lots,
        final_lots_amount,
    )

    class ResponseSchema(BaseModel):
        lot_ids: list[int] = Field(
            ...,
            min_length=1,
            max_length=final_lots_amount,
            description="List of lot ids",
        )
        is_need_more_lots: bool = Field(False, description="Is need more lots to finish")
        lots_needed: int = Field(0, description="How many lots you need more to finish")

    structured_llm = llm.with_structured_output(ResponseSchema)

    response: ResponseSchema = await structured_llm.ainvoke(messages)

    ai_msg = AIMessage(content=response.model_dump_json())

    return {
        'is_need_more_lots': False,
        'lots_needed': 0,
        'final_lot_ids': response.lot_ids,
        'final_agent_messages': [ai_msg] + messages,
        'messages': [RemoveMessage(id="__remove_all__")]
    }


def final_router(state: AgentsState) -> str | None:
    is_need_more_lots = state.get('is_need_more_lots')
    is_error = state.get('is_error', False)
    if is_error:
        return 'send_error_to_user'

    if is_need_more_lots:
        return 'more_lots_needed'
    else:
        return 'send_posts_to_user'
