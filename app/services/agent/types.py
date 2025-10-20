from pydantic import BaseModel, ConfigDict


class Filters(BaseModel):
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
    drive: str | None = None
    auction_date_from: str | None = None
    auction_date_to: str | None = None

    model_config = ConfigDict(extra='ignore')

