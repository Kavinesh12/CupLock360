from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # CL-0001
    name: Mapped[str] = mapped_column(String(200), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)  # home branch
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True)
    pan: Mapped[str | None] = mapped_column(String(10))
    billing_address: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    state_code: Mapped[str] = mapped_column(String(2), default="33")  # GST state code, decides CGST+SGST vs IGST
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(15))
    email: Mapped[str | None] = mapped_column(String(200))
    # Credit profile (deck slide 6)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    security_deposit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    credit_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | hold
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    projects: Mapped[list["Project"]] = relationship(back_populates="client", order_by="Project.id")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # P-0001-01
    name: Mapped[str] = mapped_column(String(200))
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    client: Mapped[Client] = relationship(back_populates="projects")
    sites: Mapped[list["Site"]] = relationship(back_populates="project", order_by="Site.id")


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # S-0001
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    state_code: Mapped[str] = mapped_column(String(2), default="33")
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    contact_phone: Mapped[str | None] = mapped_column(String(15))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="sites")


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # STD-3.0
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), index=True)
    size_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    unit: Mapped[str] = mapped_column(String(10), default="nos")
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    hsn_sac: Mapped[str | None] = mapped_column(String(10))
    # Charged when an item is returned damaged beyond repair or not returned.
    replacement_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RateCard(Base, TimestampMixin):
    """Rental rates. client_id/project_id empty = standard card. Most specific card wins."""

    __tablename__ = "rate_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    min_days: Mapped[int] = mapped_column(Integer, default=30)  # minimum billing period per dispatch
    grace_days: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    lines: Mapped[list["RateCardLine"]] = relationship(
        back_populates="rate_card", cascade="all, delete-orphan", lazy="selectin"
    )


class RateCardLine(Base):
    __tablename__ = "rate_card_lines"
    __table_args__ = (UniqueConstraint("rate_card_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_card_id: Mapped[int] = mapped_column(ForeignKey("rate_cards.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    rate_per_day: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rate_per_month: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # optional flat monthly rate

    rate_card: Mapped[RateCard] = relationship(back_populates="lines")
