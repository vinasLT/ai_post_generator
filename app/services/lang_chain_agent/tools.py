from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Annotated

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from pydantic import Field

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.rpc_client.auction_api import ApiRpcClient
from app.services.lang_chain_agent.serializer import Serializer
from app.services.lang_chain_agent.state_context import AgentsRuntimeContext
from app.services.lang_chain_agent.types import Filters
from app.services.lang_chain_agent.utils import get_repeated_lots, get_calculators_for_lots

DocumentEnum = Literal["Salvage", "Clean"]
Auctions = Literal["copart", "iaai"]
TransmissionEnum = Literal["Automatic", "Manual"]
StatusEnum = Literal["Run & Drive", "Starts", "Stationary"]
DriveEnum = Literal["Front Wheel Drive", "Rear Wheel Drive", "All Wheel Drive"]



@tool()
async def get_page_of_lots(
    site: Auctions,
    make: str,
    page: Annotated[int, Field(ge=1, description="Page number")] = 1,
    model: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    odo_from: Optional[int] = None,
    odo_to: Optional[int] = None,
    document: Optional[DocumentEnum] = None,
    transmission: Optional[TransmissionEnum] = None,
    status: Optional[StatusEnum] = None,
    drive: Optional[DriveEnum] = None,
    auction_date_from: Optional[str] = None,
    auction_date_to: Optional[str] = None,
    *,
    runtime: ToolRuntime[AgentsRuntimeContext],
) -> Command:


    """
    Fetch a page of auction lots based on provided filters and save unique results for the current request

    Arguments:
        site (Auctions): The auction site to fetch lots from.
        make (str): The make/brand of the vehicle to filter by.
        page (int): Page number, must be greater than or equal to 1.
        model (Optional[str]): Optional model of the vehicle.
        year_from (Optional[int]): Minimum year of the vehicle.
        year_to (Optional[int]): Maximum year of the vehicle.
        odo_from (Optional[int]): Minimum odometer reading.
        odo_to (Optional[int]): Maximum odometer reading.
        document (Optional[DocumentEnum]): Type of document associated with the vehicle.
        transmission (Optional[TransmissionEnum]): Transmission type to filter by.
        status (Optional[StatusEnum]): Status of the lot to filter by.
        drive (Optional[DriveEnum]): Drive type of the vehicle.
        auction_date_from (Optional[str]): Start date of auction in ISO format.
        auction_date_to (Optional[str]): End date of auction in ISO format.
        runtime (ToolRuntime[AgentsRuntimeContext]): Runtime context for the tool.

    Returns:
        str: Serialized response text containing paginated unique lots information.

    """


    if auction_date_from is not None:
        datetime.fromisoformat(auction_date_from)
    if auction_date_to is not None:
        datetime.fromisoformat(auction_date_to)

    site_norm = site.lower() if site else site

    filters = Filters(
        site=site_norm,
        make=make,
        model=model,
        year_from=year_from,
        year_to=year_to,
        odo_from=odo_from,
        odo_to=odo_to,
        document=document,
        transmission=transmission,
        status=status,
        drive=drive,
        auction_date_from=auction_date_from,
        auction_date_to=auction_date_to,
    )

    async with ApiRpcClient() as client:
        response = await client.get_current_lots_with_filters(filters, page=page)

    lot_ids = [lot.lot_id for lot in response.lot]
    user_uuid = runtime.context["user_uuid"]
    request_id = runtime.context["request_id"]
    repeated_lot_ids = await get_repeated_lots(lot_ids, user_uuid, request_id)
    repeated_lot_ids_set = set(repeated_lot_ids)

    error_message = (
        f"Found 20 lots but you already sent them, try to change page number to {page + 1}, "
        f"if there is no new lots for long time try page for example {page + 5} or even more"
    )

    if lot_ids and all(lot_id in repeated_lot_ids_set for lot_id in lot_ids):
        logger.warning(f"No unique lots found for filters: {filters}")
        return error_message
    unique_lots = []
    seen_lot_ids: set[int] = set()
    for lot in response.lot:
        if lot.lot_id in repeated_lot_ids_set or lot.lot_id in seen_lot_ids:
            continue
        unique_lots.append(lot)
        seen_lot_ids.add(lot.lot_id)

    if not unique_lots:
        logger.warning(f"No unique lots found for filters: {filters}")
        return error_message

    async with get_async_db() as db:
        post_service = PostService(db)
        existing_posts = await post_service.get_by_request_id(request_id)
        existing_lot_ids = {post.lot_id for post in existing_posts}
        fresh_lots = [lot for lot in unique_lots if lot.lot_id not in existing_lot_ids]

        if not fresh_lots:
            logger.warning(f"All fetched lots are already saved for current request: {request_id}")
            return error_message

        lots_with_calculator = await get_calculators_for_lots(fresh_lots)
        if lots_with_calculator:
            await post_service.create_posts_batch(request_id, lots_with_calculator)
        else:
            logger.warning(f"Calculator data missing for all lots in current batch, request_id={request_id}")

    lots_serialized = Serializer.transform_lots_for_ai(fresh_lots)

    response_text = (f"Pagination: {Serializer.generate_text_for_pagination(response.pagination)}\n\n"
                     f"Response: {lots_serialized}\n"
                     f"{'Request next page to got more lots' if len(unique_lots) <= 5 else ''}")
    return Command(
        update={
            "lots_from_search": fresh_lots + runtime.state.get("lots_from_search", []),
            "messages": [ToolMessage(
                response_text,
                tool_call_id=runtime.tool_call_id
            )]
        }
    )

def get_instructions(filename: str):
    instructions_folder = Path(__file__).parent / 'instructions'
    with open(instructions_folder / filename, 'r', encoding='utf-8') as f:
        return f.read()
