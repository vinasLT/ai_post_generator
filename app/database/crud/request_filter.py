from sqlalchemy import select
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


