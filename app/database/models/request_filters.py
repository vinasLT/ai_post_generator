from datetime import datetime, UTC
from typing import TYPE_CHECKING

from sqlalchemy import Integer, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

from ..enums import AuctionEnum

if TYPE_CHECKING:
    from .post import Post


class RequestFilters(Base):
    __tablename__ = "request_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_uuid: Mapped[str] = mapped_column(nullable=False)

    site: Mapped[AuctionEnum] = mapped_column(Enum(AuctionEnum),nullable=False)
    make: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(nullable=False)
    year_from: Mapped[int] = mapped_column(nullable=True)
    year_to: Mapped[int] = mapped_column(nullable=True)
    odo_from: Mapped[int] = mapped_column(nullable=True)
    odo_to: Mapped[int] = mapped_column(nullable=True)
    document: Mapped[str] = mapped_column(nullable=True)
    transmission: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(UTC))

    posts: Mapped[list["Post"]] = relationship(
        "Post",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )