import enum
from datetime import datetime, UTC
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from ..enums import AuctionEnum

if TYPE_CHECKING:
    from . import RequestFilters

class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(nullable=False)
    auction: Mapped[AuctionEnum] = mapped_column(Enum(AuctionEnum), nullable=False)

    title: Mapped[str] = mapped_column(nullable=False)
    odometer: Mapped[int] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    reserve_price: Mapped[int] = mapped_column(nullable=True)
    vin: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)

    auction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery_price: Mapped[int] = mapped_column(nullable=False)
    shipping_price: Mapped[int] = mapped_column(nullable=False)
    average_sell_price: Mapped[int] = mapped_column(nullable=True)

    is_posted: Mapped[bool] = mapped_column(nullable=False, default=False)

    image_description: Mapped[str] = mapped_column(nullable=True)
    image_score: Mapped[int] = mapped_column(nullable=True)

    images: Mapped[str] = mapped_column(nullable=False)

    request_id: Mapped[int] = mapped_column(ForeignKey('request_filters.id'), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(UTC))

    request: Mapped["RequestFilters"] = relationship(
        "RequestFilters",
        back_populates="posts",
        lazy="selectin"
    )