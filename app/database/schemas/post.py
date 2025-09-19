from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.database.enums import AuctionEnum


class PostCreate(BaseModel):
    lot_id: int
    auction: AuctionEnum
    title: str
    odometer: int
    reserve_price: int | None = None
    vin: str
    status: str
    auction_date: datetime | None = None
    delivery_price: int
    shipping_price: int
    average_sell_price: int | None = None
    is_posted: bool | None = False
    images: str
    image_description: str | None = None
    image_score: int | None = None

    request_id: int



class PostUpdate(BaseModel):
    lot_id: int | None = None
    auction: AuctionEnum | None = None
    title: str | None = None
    odometer: int | None = None
    reserve_price: int | None = None
    vin: str | None = None
    status: str | None = None
    auction_date: datetime | None = None
    delivery_price: int | None = None
    shipping_price: int | None = None
    average_sell_price: int | None = None
    image_description: str | None = None
    image_score: int | None = None
    is_posted: bool | None = None


class PostRead(PostCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)