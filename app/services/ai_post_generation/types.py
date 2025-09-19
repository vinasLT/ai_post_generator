from pydantic import BaseModel, ConfigDict


class Filters(BaseModel):
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

    model_config = ConfigDict(extra='ignore')

