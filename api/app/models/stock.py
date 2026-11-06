"""Stock is never edited directly. Every change is a movement with ledger lines; balances are a
locked running total of those lines, one row per (location, item, status)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Deck slide 7. "Passes QC" is the move inspection -> available.
STATUSES = (
    "available",
    "reserved",
    "in_transit",
    "at_site",
    "returned",
    "inspection",
    "maintenance",
    "damaged",
    "missing",
)
LOCATION_TYPES = ("warehouse", "site", "transit")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), index=True)
    reason: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(30))  # transfer | stock_check | import | ...
    source_id: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["StockEntry"]] = relationship(
        back_populates="movement", lazy="selectin", order_by="StockEntry.id"
    )


class StockEntry(Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("stock_movements.id"), index=True)
    location_type: Mapped[str] = mapped_column(String(12))
    location_id: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int] = mapped_column(Integer)  # signed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    movement: Mapped[StockMovement] = relationship(back_populates="entries")


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        PrimaryKeyConstraint("location_type", "location_id", "item_id", "status"),
        CheckConstraint("qty >= 0", name="stock_balance_non_negative"),
    )

    location_type: Mapped[str] = mapped_column(String(12))
    location_id: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    status: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Transfer(Base):
    __tablename__ = "stock_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(30), unique=True)
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="in_transit")  # in_transit | received
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    sent_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["TransferLine"]] = relationship(
        back_populates="transfer", lazy="selectin", cascade="all, delete-orphan", order_by="TransferLine.id"
    )


class TransferLine(Base):
    __tablename__ = "stock_transfer_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfers.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    qty_sent: Mapped[int] = mapped_column(Integer)
    qty_received: Mapped[int | None] = mapped_column(Integer)
    qty_damaged: Mapped[int | None] = mapped_column(Integer)
    qty_missing: Mapped[int | None] = mapped_column(Integer)

    transfer: Mapped[Transfer] = relationship(back_populates="lines")


class StockCheck(Base):
    __tablename__ = "stock_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(30), unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    status_counted: Mapped[str] = mapped_column(String(20), default="available")
    note: Mapped[str | None] = mapped_column(Text)
    counted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["StockCheckLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockCheckLine.id"
    )


class StockCheckLine(Base):
    __tablename__ = "stock_check_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("stock_checks.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    system_qty: Mapped[int] = mapped_column(Integer)
    counted_qty: Mapped[int] = mapped_column(Integer)
    variance: Mapped[int] = mapped_column(Integer)
