from langchain_core.prompts import ChatPromptTemplate
from langgraph.runtime import Runtime

from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext
from app.services.lang_chain_agent.tools import get_instructions

choose_final_lots_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_instructions}"),
        (
            "human",
            "Choose the best lots based on the following descriptions:\n"
            "{descriptions_for_lots}\n\n"
            "You must return exactly {final_lots_amount} lots.\n"
            "If there are not enough suitable lots, return an error with amount of needed more lots"
        ),

    ]
)

async def choose_final_lots_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> AgentsState:
    image_descriptions = state['lots_images_descriptions']
    descriptions_for_lots = state['lot_chooser_result']

    final_lots_amount = runtime.context['result_lots_count']

    prompt = choose_final_lots_prompt.invoke(
        {
            'system_instructions': get_instructions('main_agent.txt'),
            'descriptions_for_lots': descriptions_for_lots,
            'final_lots_amount': final_lots_amount,
        }
    ).to_messages()


