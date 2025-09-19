from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.base import BaseService
from app.database.models.request_filters import RequestFilters
from app.database.schemas.request_filters import RequestFiltersCreate, RequestFiltersUpdate


class RequestFiltersService(BaseService[RequestFilters, RequestFiltersCreate, RequestFiltersUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(RequestFilters, session)


