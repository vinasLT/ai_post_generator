import asyncio
import json

from app.core.logger import logger
from app.database.crud.post import PostService
from app.database.crud.request_filter import RequestFiltersService
from app.database.db.session import get_async_db
from app.database.enums import RequestStage
from app.database.schemas.post import PostUpdate
from app.database.schemas.request_filters import RequestFiltersCreate, RequestFiltersUpdate
from app.services.agent.ai_tools import edit_message_for_user, choose_lot_ids_from_lots
from app.services.agent.run import RunAgent
from app.services.agent.types import Filters
from app.services.ai_post_generation.generate_post import GeneratePost
from app.services.rabbit.rabbit_service import RabbitMQPublisher


async def run_post_generation_flow(filters: Filters, editable_message_id: str, user_uuid: str):
    async with get_async_db() as db:
        filter_service = RequestFiltersService(db)

        last_request = await filter_service.get_last_request_for_user_uuid(user_uuid)
        if not last_request or last_request.stage == RequestStage.FAILED or last_request.stage == RequestStage.COMPLETED:

            request = await filter_service.create(RequestFiltersCreate(site=filters.site, make=filters.make, user_uuid=user_uuid,
                                                             model=filters.model, year_from=filters.year_from, year_to=filters.year_to,
                                                             odo_from=filters.odo_from, odo_to=filters.odo_to,
                                                             document=filters.document,
                                                             transmission=filters.transmission,
                                                             status=filters.status,
                                                             auction_date_from=filters.auction_date_from,
                                                             auction_date_to=filters.auction_date_to,
                                                             stage=RequestStage.IN_PROGRESS
                                                             ))
        else:
            await edit_message_for_user(editable_message_id, '❌ Please wait until your previous request will be completed', user_uuid)
            return

    try:
        start_prompt = f'Start searching with this filters: {filters.model_dump()}'

        agent = RunAgent(editable_message_id, user_uuid)
        response, lots = await agent.run_agent_async(start_prompt)
        jsoned_response = json.loads(response)
        is_error = jsoned_response.get('is_error')
        error_detail = jsoned_response.get('error_detail')
        if is_error:
            logger.error(f'Error while posts generation occurred (response from agent): {error_detail}')
            async with get_async_db() as db:
                filter_service = RequestFiltersService(db)
                await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.FAILED))
            text = (f'❌ En error occurred:\n'
                    f'{error_detail}')
            await edit_message_for_user(editable_message_id, text, user_uuid)



        chosen_lots = choose_lot_ids_from_lots(lots, jsoned_response['lot_ids'])
        lots_with_calculator = await GeneratePost.get_calculators_for_lots(chosen_lots)

        await GeneratePost.create_posts_batch(request.id, lots_with_calculator)
        async with get_async_db() as db:
            posts_service = PostService(db)
            for lots_with_calculator in lots_with_calculator:
                avg = await GeneratePost.get_average_price(lots_with_calculator[0])
                if avg:
                    post = await posts_service.get_by_request_id_and_lot_id(request.id, lots_with_calculator[0].lot_id)
                    if post:
                        await posts_service.update(post.id, PostUpdate(average_sell_price=avg))

            await edit_message_for_user(editable_message_id, '✉️ Done! Sending Posts to you', user_uuid)


            await RabbitMQPublisher().publish(routing_key='posts_service.generated_posts', payload={
                'posts': GeneratePost.generate_response_for_user(list(await posts_service.get_by_request_id(request.id))),
                'user_uuid': user_uuid,
                'request_id': request.id
            })



        async with get_async_db() as db:
            filter_service = RequestFiltersService(db)
            await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.COMPLETED))
    except Exception as e:
        async with get_async_db() as db:
            filter_service = RequestFiltersService(db)
            await filter_service.update(request.id, RequestFiltersUpdate(stage=RequestStage.FAILED))
        logger.exception(f'Error while posts generation occurred: {str(e)}')
        text = f'❌ En error occurred, try again'
        await edit_message_for_user(editable_message_id, text, user_uuid)











if __name__ == '__main__':
    async def main():
        await run_post_generation_flow(Filters(site='IAAI', make='BMW'), 1, '123456')
    asyncio.run(main())

