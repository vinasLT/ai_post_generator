import json

from app.database.enums import AuctionEnum
from app.rpc_client.auction_api import ApiRpcClient
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.services.agent.client import openai_client
from app.services.agent.response_schemas.image_analyzer import IMAGE_ANALYZER_RESPONSE_SCHEMA
from app.services.agent.transformer import Transformers
from app.services.agent.types import Filters

auction_values = [e.value for e in AuctionEnum]


ai_tools = [
    {
        "type": "function",
        "name": "get_page_of_lots",
        "description": "Get page with lots, chosen by filters",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1, "default": 1, 'maximum': 10},
                "site": {"type": "string", "enum": auction_values},
                "make": {"type": "string"},
                "model": {"type": ["string", "null"]},
                "year_from": {"type": ["integer", "null"]},
                "year_to": {"type": ["integer", "null"]},
                "odo_from": {"type": ["integer", "null"]},
                "odo_to": {"type": ["integer", "null"]},
                "document": {"type": ["string", "null"], "enum": ["Salvage", "Clean", None]},
                "transmission": {"type": ["string", "null"], "enum": ["Automatic", "Manual", None]},
                "status": {"type": ["string", "null"], "enum": ["Run & Drive", "Starts", "Stationary", None]},
                "auction_date_from": {"type": ["string", "null"], "format": "date-time", 'description': 'Date from which auction started (change only when you really need it)'},
                "auction_date_to": {"type": ["string", "null"], "format": "date-time", 'description': 'Date to which auction started (change only when you really need it)'},
            },
            "required": ["site", "make", "page"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "get_detailed_image_info",
        "description": "Get detailed image description",
        "parameters": {
            "type": "object",
            "properties": {
                "lot_id": {"type": "string", 'description': 'Lot ID of vehicle'},
                "auction": {"type": "string", 'description': 'Auction of vehicle', "enum": auction_values}
            },
            'required': ['lot_id', 'auction'],
            'additionalProperties': False,
        }
    }
]




async def get_page_of_lots(**kwargs):
    print(kwargs)
    filters = Filters(**kwargs)
    page = kwargs.get('page', 1)
    async with ApiRpcClient() as client:
        response = await client.get_current_lots_with_filters(filters, page=page)

    lots_serialized = Transformers.transform_lots_for_ai(response.lot)

    response_text = (f'Pagination: {Transformers.generate_text_for_pagination(response.pagination)}\n\n'
                     f'Response: {lots_serialized}')
    return response_text, response.lot

async def get_detailed_image_info(**kwargs):
    lot_id: int = int(kwargs.get('lot_id'))
    lots: list[Lot] = kwargs.get('lots')
    left_lot = choose_lot_ids_from_lots(lots, [lot_id])

    image_urls = left_lot[0].link_img_hd

    with open('instructions/image_analyzer.txt', 'r', encoding='utf-8') as f:
        instructions = f.read()

    content = [{"type": "input_image", "image_url": url} for url in image_urls[:5]]

    response = await openai_client.responses.create(
        model="gpt-4o",
        input=[{"role": "user", "content": content}],
        text=IMAGE_ANALYZER_RESPONSE_SCHEMA,
        instructions=instructions,
    )
    jsoned_response = json.loads(response.output_text)
    serialized = (f'Small description for lot#{lot_id}: {jsoned_response["description"]}\n'
                  f'Score: {jsoned_response["condition_score"]}/10')
    print(serialized)
    return serialized

def choose_lot_ids_from_lots(lots: list[Lot], lot_ids: list[int])-> list[Lot]:
    left_lots = []
    for lot in lots:
        if lot.lot_id in lot_ids:
            left_lots.append(lot)
    return left_lots

tool_mapping = {
    'get_page_of_lots': get_page_of_lots,
    'get_detailed_image_info': get_detailed_image_info,
}

if __name__ == '__main__':
    import asyncio
    async def main():
        text, lots = await get_page_of_lots(page=1, site='IAAI', make='BMW')
        response = await get_detailed_image_info(lots[0], lot_id=42807735, )
        print(response)
    asyncio.run(main())