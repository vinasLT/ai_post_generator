from langchain_core.messages import AIMessage, RemoveMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from app.config import settings
from app.services.lang_chain_agent.schemas import AgentResult
from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions

choose_final_lots_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_instructions}"),
        MessagesPlaceholder(variable_name="final_agent_messages_history", optional=True),
        (
            "human",
            "Choose the best lots based on the following descriptions:\n"
            "{descriptions_for_lots}\n\n"
            "You must return exactly {final_lots_amount} lots.\n"
            "If there are not enough suitable lots, return an error with amount of needed more lots"
        ),

    ]
)

llm = ChatOpenAI(model='gpt-5-mini', reasoning_effort='medium', api_key=settings.OPENAI_API_KEY, use_responses_api=True)

async def choose_final_lots_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> AgentsState:
    image_descriptions = state['lots_images_descriptions']
    lot_chooser_result = state['lot_chooser_result']
    final_agent_messages = state.get('final_agent_messages', [])

    descriptions_for_lots_raw = []
    for img_desc in image_descriptions:
        for lot in lot_chooser_result.lots:
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
    print(len(descriptions_for_lots_raw))
    print(descriptions_for_lots)



    final_lots_amount = runtime.context['result_lots_count']

    prompt = choose_final_lots_prompt.invoke(
        {
            'system_instructions': get_instructions('choose_final_lots.md'),
            'final_agent_messages_history': final_agent_messages,
            'descriptions_for_lots': descriptions_for_lots,
            'final_lots_amount': final_lots_amount,
        }
    ).to_messages()


    class ResponseSchema(BaseModel):
        lot_ids: list[int] = Field(..., min_length=final_lots_amount, max_length=final_lots_amount, description="List of lot ids")
        is_need_more_lots: bool = Field(..., description="Is need more lots to finish")
        lots_needed: int = Field(..., description="How many lots you need more to finish")

    structured_llm = llm.with_structured_output(ResponseSchema)

    response: ResponseSchema = await structured_llm.ainvoke(prompt)

    ai_msg = AIMessage(content=response.model_dump_json())

    return {
        'is_need_more_lots': response.is_need_more_lots,
        'lots_needed': response.lots_needed,
        'final_lot_ids': response.lot_ids,
        'final_agent_messages':[ai_msg] + prompt,
        'messages': [RemoveMessage(id="__remove_all__")]
    }



def final_router(state: AgentsState) -> str | None:
    is_need_more_lots = state.get('is_need_more_lots')
    if is_need_more_lots:
        return 'more_lots_needed'
    else:
        return 'end'



