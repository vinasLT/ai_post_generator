import json
from pathlib import Path

from app.core.utils import BASE_DIR
from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import AuctionEnum, RequestStage
from app.rpc_client.auction_api import ApiRpcClient
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.services.agent.client import openai_client
from app.services.agent.response_schemas.image_analyzer import IMAGE_ANALYZER_RESPONSE_SCHEMA
from app.services.agent.transformer import Transformers
from app.services.agent.types import Filters
from app.services.rabbit.rabbit_service import RabbitMQPublisher

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
                "auction_date_from": {"type": ["string", "null"], "format": "date-time", 'description': 'Date from which auction started (change only when you really need it), format: 2025-10-31'},
                "auction_date_to": {"type": ["string", "null"], "format": "date-time", 'description': 'Date to which auction started (change only when you really need it), format: 2025-10-31'},
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
    },

    {
      'type': 'function',
       'name': 'which_lots_repeated',
       'description': 'Get lots that are user already saw',
       'parameters': {
           'type': 'object',
           'properties': {
               "lot_ids": {"type": "array", "items": {"type": "number"}, 'description': 'Lot IDs of vehicle that you choose'},
           },
           'required': ['lot_ids'],
       }
    }
]

async def edit_message_for_user(message_id: str, text: str, user_uuid: str):
    async with RabbitMQPublisher() as publisher:
        await publisher.publish(routing_key='posts_service.update_message',
                                payload={'message': text, 'message_id': message_id, 'user_uuid': user_uuid})

def get_instructions(filename: str):
    instructions_folder = Path(__file__).parent / 'instructions'
    with open(instructions_folder / filename, 'r', encoding='utf-8') as f:
        return f.read()



async def get_page_of_lots(**kwargs):
    print(kwargs)
    filters = Filters(**kwargs)
    page = kwargs.get('page', 1)
    editable_message_id = kwargs.get('editable_message_id')
    user_uuid = kwargs.get('user_uuid')
    await edit_message_for_user(editable_message_id, f'🔍 Getting lots for page: {page}', user_uuid)

    async with ApiRpcClient() as client:
        response = await client.get_current_lots_with_filters(filters, page=page)

    lots_serialized = Transformers.transform_lots_for_ai(response.lot)

    response_text = (f'Pagination: {Transformers.generate_text_for_pagination(response.pagination)}\n\n'
                     f'Response: {lots_serialized}')
    return response_text, response.lot

async def which_lots_repeated(**kwargs):
    print('which_lots_repeated')
    lot_ids = kwargs.get('lot_ids')
    user_uuid = kwargs.get('user_uuid')
    editable_message_id = kwargs.get('editable_message_id')
    repeated_lot_ids = []

    await edit_message_for_user(editable_message_id, f'🔍 Checking which lots Ive already sent you', user_uuid)

    async with get_async_db() as db:
        post_service = PostService(db)
        request_filter_service = RequestFiltersService(db)
        filter_request = await request_filter_service.get_last_request_for_user_uuid(user_uuid, 5)
        if filter_request:
            for request in filter_request:
                if request.stage == RequestStage.COMPLETED:
                    for lot_id in lot_ids:
                        lots = await post_service.get_by_lot_id_and_request_id(lot_id, request.id)
                        if lots:
                            repeated_lot_ids.append(lot_id)

        return f'You need to replace lot IDs: {repeated_lot_ids}'

async def get_detailed_image_info(**kwargs):
    lot_id: int = int(kwargs.get('lot_id'))
    lots: list[Lot] = kwargs.get('lots')
    left_lot = choose_lot_ids_from_lots(lots, [lot_id])
    editable_message_id = kwargs.get('editable_message_id')
    user_uuid = kwargs.get('user_uuid')
    lot = left_lot[0]
    await edit_message_for_user(editable_message_id, f'🔍 Analyzing image for lot: #{lot_id}\n'
                                                     f'Title: {lot.title}\n', user_uuid)


    image_urls =lot.link_img_hd

    content = [{"type": "input_image", "image_url": url} for url in image_urls[:5]]

    response = await openai_client.responses.create(
        model="gpt-4o",
        input=[{"role": "user", "content": content}],
        text=IMAGE_ANALYZER_RESPONSE_SCHEMA,
        instructions=get_instructions('image_analyzer.txt'),
    )
    jsoned_response = json.loads(response.output_text)
    serialized = (f'Small description for lot#{lot_id}: {jsoned_response["description"]}\n'
                  f'Score: {jsoned_response["condition_score"]}/10')

    await edit_message_for_user(editable_message_id, f'🔍 Images for lot #{lot_id} analyzed successfully\n'
                                                     f'Score: {jsoned_response["condition_score"]}/10', user_uuid)

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
    'which_lots_repeated': which_lots_repeated,
}

if __name__ == '__main__':
    import asyncio
    async def main():
        lots = await which_lots_repeated(lot_ids=[43216112, 534534535, 34553535, 43282468], user_uuid='0b340a37-8b89-4b57-adad-0fa1941cf193')
        print(lots)
    asyncio.run(main())