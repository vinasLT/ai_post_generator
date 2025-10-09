from traceback import print_tb

from app.database.enums import AuctionEnum
from app.rpc_client.auction_api import ApiRpcClient
from app.services.ai_post_generation.types import Filters

auction_values = [e.value for e in AuctionEnum]


tools = [
    {
        "type": "function",
        "name": "get_page_of_lots",
        "description": "Get page with lots to choose by filters",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1, "default": 1},
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
                "auction_date_from": {"type": ["string", "null"], "format": "date-time"},
                "auction_date_to": {"type": ["string", "null"], "format": "date-time"}
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
        response = await client.get_current_lots_with_filters(filters, page)

    response_text = (f'Pagination: {response.pagination}\n\n'
                     f'Response: {response.lot}')
    return response_text

async def get_detailed_image_info(**kwargs):
    return 'Good condition'




tool_mapping = {
    'get_page_of_lots': get_page_of_lots,
    'get_detailed_image_info': get_detailed_image_info,
}
