from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RequestFiltersCreate(BaseModel):
    user_uuid: str

    site: str
    make: str
    model: str
    year_from: int
    year_to: int
    odo_from: int
    odo_to: int
    document: str
    transmission: str
    status: str

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

    created_at: Optional[datetime] = None


class RequestFiltersRead(RequestFiltersCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)