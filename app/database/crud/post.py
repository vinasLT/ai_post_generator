from typing import Any, Coroutine, Sequence, Union

from dateutil import parser
from sqlalchemy import select, Row, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.database.crud.base import BaseService
from app.database.enums import AuctionEnum
from app.database.models.post import Post
from app.database.models.request_filters import RequestFilters
from app.database.schemas.post import PostCreate, PostUpdate
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2


class PostService(BaseService[Post, PostCreate, PostUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Post, session)

    async def get_repeated_posts(self, lot_ids: list[int], return_ids: bool = False) -> Union[
        Sequence[Post], list[int]]:
        result = await self.session.execute(
            select(Post if not return_ids else Post.lot_id).where(
                Post.lot_id.in_(lot_ids)
            )
        )
        return result.scalars().all()


    async def get_by_lot_id(self, lot_id: int) -> Post:
        result = await self.session.execute(
            select(Post).where(
                Post.lot_id == lot_id
            )
        )
        return result.scalars().first()

    async def left_only_this_lot_ids(self, request_filter_id: int, lot_ids: list[int]) -> list[Post]:
        stmt = select(Post).where(Post.request_id == request_filter_id)
        result = await self.session.execute(stmt)
        posts = result.scalars().all()

        posts_to_delete = [post for post in posts if post.lot_id not in lot_ids]
        posts_to_keep = [post for post in posts if post.lot_id in lot_ids]

        for post in posts_to_delete:
            await self.session.delete(post)

        await self.session.commit()

        return posts_to_keep

    async def get_posts_by_lot_ids(self, lot_ids: list[int], request_id: int) -> Sequence[Post]:
        stmt = select(Post).where(Post.lot_id.in_(lot_ids), Post.request_id == request_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_request_id(self, request_id: int) -> Sequence[Post]:
        stmt = select(Post).where(Post.request_id == request_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    async def get_by_lot_id_and_request_id(self, lot_id: int, request_id: int) -> Post | None:
        stmt = select(Post).where(Post.lot_id == lot_id, Post.request_id == request_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_request_id_and_lot_id(self, request_id: int, lot_id: int) -> Post | None:
        stmt = select(Post).where(Post.request_id == request_id, Post.lot_id == lot_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_repeated_lot_ids_for_user(
        self,
        user_uuid: str,
        lot_ids: list[int],
        exclude_request_id: int | None = None,
    ) -> set[int]:
        if not lot_ids:
            return set()

        stmt = (
            select(Post.lot_id)
            .join(RequestFilters, Post.request_id == RequestFilters.id)
            .where(RequestFilters.user_uuid == user_uuid)
            .where(Post.lot_id.in_(lot_ids))
        )

        if exclude_request_id is not None:
            stmt = stmt.where(Post.request_id != exclude_request_id)

        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def create_post(self, lot: lot_pb2.Lot, calculator: calculator_pb2.GetCalculatorWithDataResponse,
                          request_id: int, flush: bool = False,
                          average_sell_price: int = None) -> Post | None:
        try:
            post = await self.create(PostCreate(
                lot_id=lot.lot_id,
                auction=AuctionEnum(lot.base_site),
                title=lot.title,
                odometer=lot.odometer,
                vin=lot.vin,
                status=lot.status,
                primary_damage=lot.damage_pr.upper() if lot.damage_pr else None,
                year=lot.year,
                auction_date=parser.parse(lot.auction_date) if lot.auction_date else None,
                delivery_price=calculator.data.calculator.transportation_price[0].price,
                shipping_price=calculator.data.calculator.ocean_ship[0].price,
                average_sell_price=average_sell_price,
                request_id=request_id,
                images=','.join(list(lot.link_img_hd)[:10])
            ), flush=flush)
        except Exception as e:
            logger.error(f"Error processing lot {lot.lot_id} to DB: {e}")
            return None
        return post

    async def create_posts_batch(
            self,
            request_id: int,
            lots_with_calculators: list[tuple[lot_pb2.Lot, calculator_pb2.GetCalculatorWithDataResponse]]
    ) -> list[lot_pb2.Lot]:
        processed_lots = []


        for lot_calculator_pair in lots_with_calculators:
            lot, calculator = lot_calculator_pair
            try:
                post = await self.create_post(lot, calculator, request_id, flush=True)
                if post:
                    processed_lots.append(post)
            except Exception as e:
                logger.error(f"Error processing lot {lot.lot_id} to DB: {e}")

        await self.session.commit()

        return processed_lots
