from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict, Annotated

from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.services.lang_chain_agent.schemas import AgentResult, ImageProcessingResult, LotObject
from app.services.lang_chain_agent.types import Filters


class AgentsState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    lots_from_search: list[Lot]

    filters: Filters

    # lot chooser agent
    min_lots_lot_chooser: int
    max_lots_lot_chooser: int

    cumulated_chose_lot_ids: list[int]
    cumulated_lots: list[LotObject]

    chose_lot_ids: list[int]
    lot_chooser_result: AgentResult | None

    #image processor node
    cumulated_images_description: list[ImageProcessingResult]
    lots_images_descriptions: list[ImageProcessingResult] | None

    # final agent
    is_need_more_lots: bool
    lots_needed: int
    final_lot_ids: list[int]
    final_agent_messages: Annotated[list[BaseMessage], add_messages]




class AgentsRuntimeContext(TypedDict):
    user_uuid: str
    request_id: int
    result_lots_count: int
