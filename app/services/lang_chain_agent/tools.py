from langchain_core.tools import tool

from app.core.logger import logger
from app.rpc_client.auction_api import ApiRpcClient
from app.services.agent.ai_tools import get_repeated_lots
from app.services.agent.transformer import Transformers
from app.services.agent.types import Filters


@tool
async def search_lots(
        site: str,
        make: str,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        odo_from: int | None = None,
        odo_to: int | None = None,
        document: str | None = None,
        transmission: str | None = None,
        status: str | None = None,
        drive: str | None = None,
        auction_date_from: str | None = None,
        auction_date_to: str | None = None,

        page: int = 1,
        user_uuid: str = ''
) -> str:
    filters = Filters(site=site, make=make, model=model, year_from=year_from, year_to=year_to, odo_from=odo_from,
                       odo_to=odo_to, document=document, transmission=transmission, status=status, drive=drive,
                       auction_date_from=auction_date_from, auction_date_to=auction_date_to)

    async with ApiRpcClient() as client:
        response = await client.get_current_lots_with_filters(filters, page=page)

    lot_ids = [lot.lot_id for lot in response.lot]

    repeated_lot_ids = await get_repeated_lots(lot_ids, user_uuid)

    if len(repeated_lot_ids) == 20:
        logger.warning(f'No unique lots found for filters: {filters}')
        return 'Found 20 lots but you already sent them, try to change page number'

    unique_lots = []
    for lot in response.lot:
        if lot.lot_id not in repeated_lot_ids:
            unique_lots.append(lot)

    if len(unique_lots) == 0:
        logger.warning(f'No unique! lots found for filters: {filters}')
        return 'Found 20 lots but you already sent them, try to change page number'

    lots_serialized = Transformers.transform_lots_for_ai(unique_lots)

    response_text = (f'Pagination: {Transformers.generate_text_for_pagination(response.pagination)}\n\n'
                     f'Response: {lots_serialized}')
    return response_text, response.lot