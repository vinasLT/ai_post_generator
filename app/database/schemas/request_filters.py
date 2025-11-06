from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.database.enums import RequestStage


class RequestFiltersCreate(BaseModel):
    user_uuid: str

    site: str
    make: str
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    odo_from: int | None = None
    odo_to: int | None = None
    document: str | None = None
    transmission: str | None = None
    status: str | None = None
    auction_date_from: datetime | None = None
    auction_date_to: datetime | None = None
    drive: str | None = None
    auction_time: str | None = None
    stage: RequestStage

    created_at: Optional[datetime] = None


class RequestFiltersUpdate(BaseModel):
    user_uuid: str | None = None

    site: str | None = None
    make: str | None = None
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    odo_from: int | None = None
    odo_to: int | None = None
    document: str | None = None
    transmission: str | None = None
    status: str | None = None
    stage: RequestStage | None = None
    drive: str | None = None
    auction_time: str | None = None

    created_at: Optional[datetime] = None


class RequestFiltersRead(RequestFiltersCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)