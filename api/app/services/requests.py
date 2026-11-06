"""Request estimate, availability and document numbering."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Item, MaterialRequest, Site, StockBalance, User, Warehouse
from app.services.rates import effective_rates

IST = timedelta(hours=5, minutes=30)
TWO = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(v).quantize(TWO, rounding=ROUND_HALF_UP)


def today_ist() -> date:
    return (datetime.now(UTC) + IST).date()


def fin_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def next_number(db: Session, model, column, prefix: str, width: int = 6, sep: str = "-") -> str:
    """Gap-tolerant running number per prefix, serialised with an advisory lock."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p))"), {"p": f"ref:{prefix}"})
    n = db.scalar(select(func.count()).select_from(model).where(column.like(f"{prefix}{sep}%")))
    return f"{prefix}{sep}{n + 1:0{width}d}"


@dataclass
class LinePrice:
    item_id: int
    qty: int
    rate_per_day: Decimal
    days: int
    amount: Decimal
    rate_card_id: int | None


@dataclass
class Estimate:
    lines: list[LinePrice]
    rent: Decimal
    transport: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    missing_rates: list[int]

    @property
    def gst(self) -> Decimal:
        return self.cgst + self.sgst + self.igst

    def as_dict(self) -> dict:
        return {
            "lines": [
                {
                    "item_id": ln.item_id,
                    "qty": ln.qty,
                    "rate_per_day": ln.rate_per_day,
                    "days": ln.days,
                    "amount": ln.amount,
                }
                for ln in self.lines
            ],
            "rent": self.rent,
            "transport": self.transport,
            "taxable": self.taxable,
            "cgst": self.cgst,
            "sgst": self.sgst,
            "igst": self.igst,
            "gst": self.gst,
            "total": self.total,
            "missing_rates": self.missing_rates,
        }


def estimate(
    db: Session,
    *,
    client_id: int,
    project_id: int,
    site: Site,
    duration_days: int,
    transport: Decimal,
    qtys: dict[int, int],
    on: date | None = None,
) -> Estimate:
    """Rent for the requested period (at least the rate card's minimum days) + transport + GST."""
    on = on or today_ist()
    rates = effective_rates(db, on=on, item_ids=list(qtys), client_id=client_id, project_id=project_id)
    lines, missing = [], []
    for item_id, qty in qtys.items():
        r = rates.get(item_id)
        if not r:
            missing.append(item_id)
        rate = r.rate_per_day if r else Decimal(0)
        days = max(duration_days, r.min_days if r else 0)
        lines.append(LinePrice(item_id, qty, rate, days, money(rate * qty * days), r.rate_card_id if r else None))
    rent = sum((ln.amount for ln in lines), Decimal(0))
    transport = money(transport or 0)
    taxable = money(rent + transport)
    s = get_settings()
    rate = Decimal(s.gst_rate) / 100
    if site.state_code == s.company_state_code:
        cgst = sgst = money(taxable * rate / 2)
        igst = Decimal("0.00")
    else:
        cgst = sgst = Decimal("0.00")
        igst = money(taxable * rate)
    return Estimate(
        lines, money(rent), transport, taxable, cgst, sgst, igst, money(taxable + cgst + sgst + igst), missing
    )


def availability(db: Session, item_ids: list[int], warehouse_ids: list[int] | None = None) -> dict:
    """{item_id: {warehouse_id: available}} for active warehouses."""
    stmt = (
        select(StockBalance.item_id, StockBalance.location_id, StockBalance.qty)
        .join(Warehouse, Warehouse.id == StockBalance.location_id)
        .where(
            StockBalance.location_type == "warehouse",
            StockBalance.status == "available",
            StockBalance.item_id.in_(item_ids),
            Warehouse.is_active,
            StockBalance.qty > 0,
        )
    )
    if warehouse_ids is not None:
        stmt = stmt.where(StockBalance.location_id.in_(warehouse_ids))
    out: dict[int, dict[int, int]] = {i: {} for i in item_ids}
    for item_id, wh_id, qty in db.execute(stmt):
        out[item_id][wh_id] = qty
    return out


def approval_ref(req: MaterialRequest, approved: dict[int, int]) -> str:
    """OTP binding: request, version and the exact approved quantities. Any change needs a new OTP."""
    body = ",".join(f"{k}:{approved[k]}" for k in sorted(approved))
    return f"request:{req.id}:v{req.version}:{hashlib.sha256(body.encode()).hexdigest()[:16]}"


def approval_limit(user: User) -> Decimal | None:
    """None = no limit. Only the owner role is unlimited by default; others need a limit set on the user."""
    if user.approval_limit is not None:
        return Decimal(user.approval_limit)
    return None if "owner" in {r.code for r in user.roles} else Decimal(0)


def item_names(db: Session, ids) -> dict[int, Item]:
    return {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(list(ids))))}
