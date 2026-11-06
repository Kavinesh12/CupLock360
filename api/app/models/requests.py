"""Material request -> approval (OTP) -> reservation -> dispatch (challan) -> site receipt.
Deck slides 5 and 8. Approval never equals dispatch: stock leaves only when dispatch confirms
the actual quantities."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

REQUEST_STATUSES = ("submitted", "approved", "rejected", "cancelled", "part_dispatched", "dispatched", "closed")
OPEN_STATUSES = ("submitted", "approved", "part_dispatched")


class MaterialRequest(Base):
    __tablename__ = "material_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # amendments bump it; approval and OTP bind to it
    required_on: Mapped[date] = mapped_column(Date)
    duration_days: Mapped[int] = mapped_column(Integer)
    transport_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # Estimate snapshot (recomputed on create/amend/approve)
    est_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    est_taxable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    est_gst: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    est_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_version: Mapped[int | None] = mapped_column(Integer)
    decision_note: Mapped[str | None] = mapped_column(Text)  # approval note, rejection or cancel reason
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["RequestLine"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="RequestLine.id"
    )
    dispatches: Mapped[list["Dispatch"]] = relationship(back_populates="request", order_by="Dispatch.id")
    client = relationship("Client", lazy="selectin", viewonly=True)
    site = relationship("Site", lazy="selectin", viewonly=True)
    warehouse = relationship("Warehouse", lazy="selectin", viewonly=True)

    @property
    def client_name(self) -> str:
        return self.client.name

    @property
    def site_name(self) -> str:
        return f"{self.site.code} · {self.site.name}"

    @property
    def warehouse_code(self) -> str:
        return self.warehouse.code


class RequestLine(Base):
    __tablename__ = "material_request_lines"
    __table_args__ = (UniqueConstraint("request_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("material_requests.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    qty_requested: Mapped[int] = mapped_column(Integer)
    qty_approved: Mapped[int | None] = mapped_column(Integer)
    qty_dispatched: Mapped[int] = mapped_column(Integer, default=0)
    rate_per_day: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    rate_card_id: Mapped[int | None] = mapped_column(ForeignKey("rate_cards.id"))

    request: Mapped[MaterialRequest] = relationship(back_populates="lines")


class Dispatch(Base):
    __tablename__ = "dispatches"

    id: Mapped[int] = mapped_column(primary_key=True)
    challan_no: Mapped[str] = mapped_column(String(40), unique=True)  # DC/CHN/2026-27/00001
    request_id: Mapped[int] = mapped_column(ForeignKey("material_requests.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="in_transit")  # in_transit | received
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    driver_name: Mapped[str | None] = mapped_column(String(120))
    driver_phone: Mapped[str | None] = mapped_column(String(15))
    note: Mapped[str | None] = mapped_column(Text)
    dispatched_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receiver_name: Mapped[str | None] = mapped_column(String(120))
    receipt_note: Mapped[str | None] = mapped_column(Text)

    request: Mapped[MaterialRequest] = relationship(back_populates="dispatches")
    site = relationship("Site", lazy="selectin", viewonly=True)

    @property
    def site_name(self) -> str:
        return f"{self.site.code} · {self.site.name}"

    @property
    def request_ref(self) -> str:
        return self.request.ref_no
    lines: Mapped[list["DispatchLine"]] = relationship(
        back_populates="dispatch", cascade="all, delete-orphan", order_by="DispatchLine.id"
    )


class DispatchLine(Base):
    __tablename__ = "dispatch_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    qty: Mapped[int] = mapped_column(Integer)
    qty_received: Mapped[int | None] = mapped_column(Integer)
    qty_short: Mapped[int | None] = mapped_column(Integer)

    dispatch: Mapped[Dispatch] = relationship(back_populates="lines")
