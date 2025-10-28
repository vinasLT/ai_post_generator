from datetime import datetime
from typing import Literal, Optional, Any, List, TypedDict
from typing_extensions import Annotated
import operator

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, add_messages
from langchain_core.messages import BaseMessage, SystemMessage

from pydantic import field_validator, BaseModel, ConfigDict, Field

from app.core.logger import logger
from app.rpc_client.auction_api import ApiRpcClient
from app.services.agent.ai_tools import get_repeated_lots
from app.services.agent.transformer import Transformers
from app.services.agent.types import Filters
from app.config import settings

DocumentEnum = Literal["Salvage", "Clean"]
Auctions = Literal["copart", "iaai"]
TransmissionEnum = Literal["Automatic", "Manual"]
StatusEnum = Literal["Run & Drive", "Starts", "Stationary"]
DriveEnum = Literal["Front Wheel Drive", "Rear Wheel Drive", "All Wheel Drive"]

class GetPageOfLotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(1, ge=1, le=10, description="Page number")
    site: Auctions = Field(..., description="Auction site identifier from allowed values")
    make: str = Field(..., description="Vehicle make")
    model: Optional[str] = Field(None, description="Vehicle model or null")
    year_from: Optional[int] = Field(None, description="Production year from or null")
    year_to: Optional[int] = Field(None, description="Production year to or null")
    odo_from: Optional[int] = Field(None, description="Odometer from or null")
    odo_to: Optional[int] = Field(None, description="Odometer to or null")
    document: Optional[DocumentEnum] = Field(None, description="Salvage, Clean, or null")
    transmission: Optional[TransmissionEnum] = Field(None, description="Automatic, Manual, or null")
    status: Optional[StatusEnum] = Field(None, description="Run & Drive, Starts, Stationary, or null")
    drive: Optional[DriveEnum] = Field(None, description="Front Wheel Drive, Rear Wheel Drive, All Wheel Drive, or null")
    auction_date_from: Optional[str] = Field(None, description="Date from which auction started (change only when you really need it), format: 2025-10-31")
    auction_date_to: Optional[str] = Field(None, description="Date to which auction started (change only when you really need it), format: 2025-10-31")
    describe_action: str = Field(..., description="Describe what you want to do in one sentence")

    @field_validator("auction_date_from", "auction_date_to")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        datetime.fromisoformat(v)
        return v

def make_get_page_of_lots(user_uuid: str):
    @tool(args_schema=GetPageOfLotsInput)
    async def get_page_of_lots(
        page: int,
        site: str,
        make: str,
        model: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        odo_from: Optional[int] = None,
        odo_to: Optional[int] = None,
        document: Optional[str] = None,
        transmission: Optional[str] = None,
        status: Optional[str] = None,
        drive: Optional[str] = None,
        auction_date_from: Optional[str] = None,
        auction_date_to: Optional[str] = None,
        describe_action: str = ""
    ) -> dict:
        """Get auction lots by filters. Return up to 20 lots per page."""

        filters = Filters(site=site, make=make, model=model, year_from=year_from, year_to=year_to, odo_from=odo_from, odo_to=odo_to, document=document, transmission=transmission, status=status, drive=drive, auction_date_from=auction_date_from, auction_date_to=auction_date_to)
        async with ApiRpcClient() as client:
            response = await client.get_current_lots_with_filters(filters, page=page)
        lot_ids = [lot.lot_id for lot in response.lot]
        repeated_lot_ids = await get_repeated_lots(lot_ids, user_uuid)
        if len(repeated_lot_ids) == 20:
            logger.warning(f"No unique lots found for filters: {filters}")
            return "Found 20 lots but you already sent them, try to change page number"
        unique_lots = []
        for lot in response.lot:
            if lot.lot_id not in repeated_lot_ids:
                unique_lots.append(lot)
        if len(unique_lots) == 0:
            logger.warning(f"No unique lots found for filters: {filters}")
            return "Found 20 lots but you already sent them, try to change page number"
        lots_serialized = Transformers.transform_lots_for_ai(unique_lots)
        response_text = f"Pagination: {Transformers.generate_text_for_pagination(response.pagination)}\n\nResponse: {lots_serialized}"
        return response_text
    return get_page_of_lots

class AppState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_uuid: str
