"""The only code that changes stock. Every change is an append-only ledger line plus a locked
balance update in the same transaction, so balances can always be traced and never go negative."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import StockBalance, StockEntry, StockMovement
from app.models.stock import LOCATION_TYPES, STATUSES

REF_PREFIX = {
    "opening": "OPN",
    "transfer_send": "TRS",
    "transfer_receive": "TRR",
    "status_change": "STC",
    "write_off": "WOF",
    "stock_check": "CHK",
    "reserve": "RSV",
    "release": "RLS",
    "dispatch": "DSP",
    "site_receipt": "RCP",
}

# Allowed status changes inside one warehouse (deck slide 7).
TRANSITIONS: dict[tuple[str, str], str] = {
    ("available", "maintenance"): "Sent for repair",
    ("maintenance", "available"): "Repaired",
    ("available", "damaged"): "Found damaged",
    ("damaged", "maintenance"): "Sent for repair",
    ("maintenance", "damaged"): "Beyond repair",
    ("returned", "inspection"): "Inspection started",
    ("inspection", "available"): "Passed QC",
    ("inspection", "maintenance"): "Needs repair",
    ("inspection", "damaged"): "Failed QC",
    ("missing", "available"): "Found",
    ("available", "missing"): "Not found",
}
WRITE_OFF_FROM = ("damaged", "missing")


@dataclass(frozen=True)
class Line:
    location_type: str
    location_id: int
    item_id: int
    status: str
    qty: int  # signed


class StockError(Exception):
    def __init__(self, message: str, shortages: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.shortages = shortages or []


def next_ref(db: Session, prefix: str) -> str:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p))"), {"p": f"ref:{prefix}"})
    n = db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.ref_no.like(f"{prefix}-%")))
    return f"{prefix}-{n + 1:06d}"


def replay(db: Session, idempotency_key: str | None) -> StockMovement | None:
    """The movement already posted with this key, if any (safe retries from flaky mobile networks)."""
    if not idempotency_key:
        return None
    return db.scalar(select(StockMovement).where(StockMovement.idempotency_key == idempotency_key))


def post(
    db: Session,
    *,
    kind: str,
    lines: list[Line],
    user_id: int,
    warehouse_id: int | None = None,
    reason: str | None = None,
    note: str | None = None,
    source: tuple[str, int] | None = None,
    idempotency_key: str | None = None,
) -> StockMovement:
    """Post one movement. Raises StockError (nothing written) if any balance would go negative."""
    if not lines:
        raise StockError("Nothing to post")
    for ln in lines:
        if ln.status not in STATUSES or ln.location_type not in LOCATION_TYPES:
            raise StockError(f"Invalid status or location: {ln.status}/{ln.location_type}")
        if ln.qty == 0:
            raise StockError("Quantity cannot be zero")

    # Net the changes per balance key, then lock keys in a fixed order (no deadlocks).
    deltas: dict[tuple, int] = defaultdict(int)
    for ln in lines:
        deltas[(ln.location_type, ln.location_id, ln.item_id, ln.status)] += ln.qty
    keys = sorted(deltas)
    if keys:
        db.execute(
            insert(StockBalance)
            .values(
                [{"location_type": k[0], "location_id": k[1], "item_id": k[2], "status": k[3], "qty": 0} for k in keys]
            )
            .on_conflict_do_nothing()
        )
    shortages = []
    balances = {}
    for k in keys:
        bal = db.get(StockBalance, k, with_for_update=True, populate_existing=True)
        balances[k] = bal
        if bal.qty + deltas[k] < 0:
            shortages.append(
                {
                    "location_type": k[0],
                    "location_id": k[1],
                    "item_id": k[2],
                    "status": k[3],
                    "have": bal.qty,
                    "need": -deltas[k],
                }
            )
    if shortages:
        raise StockError("Not enough stock", shortages)

    mv = StockMovement(
        ref_no=next_ref(db, REF_PREFIX.get(kind, "MOV")),
        kind=kind,
        warehouse_id=warehouse_id,
        reason=reason,
        note=note,
        created_by=user_id,
        idempotency_key=idempotency_key,
        source_type=source[0] if source else None,
        source_id=source[1] if source else None,
    )
    db.add(mv)
    try:
        db.flush()
    except IntegrityError:
        raise StockError("This request was already processed (duplicate idempotency key)") from None
    for ln in lines:
        db.add(
            StockEntry(
                movement_id=mv.id,
                location_type=ln.location_type,
                location_id=ln.location_id,
                item_id=ln.item_id,
                status=ln.status,
                qty=ln.qty,
            )
        )
    for k, bal in balances.items():
        bal.qty += deltas[k]
    db.flush()
    db.refresh(mv)
    return mv


def move(
    location: tuple[str, int],
    item_id: int,
    qty: int,
    from_status: str,
    to_status: str,
    to_location: tuple[str, int] | None = None,
) -> list[Line]:
    """Two balanced lines moving qty between statuses (and optionally locations)."""
    to_location = to_location or location
    return [
        Line(location[0], location[1], item_id, from_status, -qty),
        Line(to_location[0], to_location[1], item_id, to_status, qty),
    ]


def balance(db: Session, location: tuple[str, int], item_id: int, status: str) -> int:
    return (
        db.scalar(
            select(StockBalance.qty).where(
                StockBalance.location_type == location[0],
                StockBalance.location_id == location[1],
                StockBalance.item_id == item_id,
                StockBalance.status == status,
            )
        )
        or 0
    )
