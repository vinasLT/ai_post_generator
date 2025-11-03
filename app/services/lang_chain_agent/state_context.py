from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel
from typing_extensions import TypedDict, Annotated

from app.services.agent.types import Filters
from app.services.lang_chain_agent.schemas import AgentResult, ImageProcessingResult


class AgentsState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    filters: Filters

    min_lots_lot_chooser: int
    max_lots_lot_chooser: int
    min_best_picked_lots: int
    max_best_picked_lots: int

    lot_chooser_result: AgentResult | None
    best_picked_lots: BaseModel | None

    lots_images_descriptions: ImageProcessingResult | None


class AgentsRuntimeContext(TypedDict):
    user_uuid: str
    request_id: int
    result_lots_count: int
