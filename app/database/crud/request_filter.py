from typing import Any, Coroutine, Sequence

from sqlalchemy import select, Row, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.base import BaseService
from app.database.enums import RequestStage
from app.database.models.request_filters import RequestFilters
from app.database.schemas.request_filters import RequestFiltersCreate, RequestFiltersUpdate


class RequestFiltersService(BaseService[RequestFilters, RequestFiltersCreate, RequestFiltersUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(RequestFilters, session)

    async def set_request_stage(self, request_id: int, stage: RequestStage)-> RequestFilters | None:
        stmt = (
            select(RequestFilters)
            .where(RequestFilters.id == request_id)
        )
        result = await self.session.execute(stmt)
        request_filter = result.scalar_one_or_none()

        if request_filter:
            request_filter.stage = stage
            await self.session.commit()
            await self.session.refresh(request_filter)
            return request_filter
        return None

    async def get_previous_request_for_user_uuid(
        self,
        user_uuid: str,
        request_id: int | None = None,
        limit: int | None = 1,
    ) -> RequestFilters | None | Sequence[RequestFilters]:
        stmt = (
            select(RequestFilters)
            .where(RequestFilters.user_uuid == user_uuid)
            .order_by(RequestFilters.created_at.desc())
        )

        if request_id is not None:
            stmt = stmt.where(RequestFilters.id != request_id)

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        if limit == 1:
            return result.scalars().first()
        return result.scalars().all()

