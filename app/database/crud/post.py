from typing import Any, Coroutine, Sequence, Union

from sqlalchemy import select, Row, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.base import BaseService
from app.database.models.post import Post
from app.database.schemas.post import PostCreate, PostUpdate


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

    async def get_by_request_id(self, request_id: int) -> Sequence[Post]:
        stmt = select(Post).where(Post.request_id == request_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_request_id_and_lot_id(self, request_id: int, lot_id: int) -> Sequence[Post]:
        stmt = select(Post).where(Post.request_id == request_id, Post.lot_id == lot_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()