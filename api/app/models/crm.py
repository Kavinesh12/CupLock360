from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(15), index=True)
    email: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str | None] = mapped_column(String(40))  # referral, walk-in, call, website...
    requirement: Mapped[str | None] = mapped_column(Text)
    est_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new|contacted|quoted|won|lost
    lost_reason: Mapped[str | None] = mapped_column(String(300))
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    converted_client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))

    follow_ups: Mapped[list["FollowUp"]] = relationship(
        back_populates="lead", order_by="FollowUp.id.desc()", lazy="selectin"
    )


class FollowUp(Base):
    __tablename__ = "lead_follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(20), default="call")  # call|visit|whatsapp|email|meeting
    note: Mapped[str] = mapped_column(Text)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped[Lead] = relationship(back_populates="follow_ups")
