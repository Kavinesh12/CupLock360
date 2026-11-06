"""Opening stock: Excel template and import (preview first, then commit)."""

import io
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import in_scope, scope_ids
from app.models import Item, StockMovement, User, Warehouse
from app.services import stock

COLUMNS = ["Warehouse code", "Item code", "Available", "Damaged", "Under repair"]
STATUS_COLS = {"Available": "available", "Damaged": "damaged", "Under repair": "maintenance"}


def template(db: Session) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Opening stock"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C2410C")
    for col, width in zip("ABCDE", (18, 18, 12, 12, 14), strict=True):
        ws.column_dimensions[col].width = width
    whs = list(db.scalars(select(Warehouse).where(Warehouse.is_active).order_by(Warehouse.code)))
    items = list(db.scalars(select(Item).where(Item.is_active).order_by(Item.code)))
    if whs and items:
        ws.append([whs[0].code, items[0].code, 0, 0, 0])
    dv = DataValidation(
        type="whole",
        operator="greaterThanOrEqual",
        formula1="0",
        allow_blank=True,
        error="Enter a whole number, 0 or more",
    )
    ws.add_data_validation(dv)
    dv.add("C2:E5000")

    ref = wb.create_sheet("Warehouses")
    ref.append(["Code", "Name"])
    for w in whs:
        ref.append([w.code, w.name])
    it = wb.create_sheet("Items")
    it.append(["Code", "Name", "Category"])
    for i in items:
        it.append([i.code, i.name, i.category])
    help_ = wb.create_sheet("How to fill")
    for line in (
        "One row per warehouse and item, counted physically on the opening date.",
        "Use the codes from the Warehouses and Items sheets exactly.",
        "Available = ready to rent. Damaged = needs scrapping or recovery. Under repair = in maintenance.",
        "Leave a cell empty or 0 when there is none. Do not add rows for stock already at client sites;",
        "site stock is loaded with the open rentals.",
    ):
        help_.append([line])
    help_.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _int(v) -> int | None:
    if v is None or v == "":
        return 0
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int) and v >= 0:
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def parse(db: Session, user: User, content: bytes) -> dict:
    """Validate the sheet. Returns rows with per-row errors and totals; nothing is written."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        return {"ok": False, "errors": ["Could not read the file. Upload the .xlsx template."], "rows": []}
    ws = wb["Opening stock"] if "Opening stock" in wb.sheetnames else wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows_iter, [])]
    if header[: len(COLUMNS)] != COLUMNS:
        return {"ok": False, "errors": [f"First row must be: {', '.join(COLUMNS)}"], "rows": []}

    whs = {w.code.upper(): w for w in db.scalars(select(Warehouse))}
    items = {i.code.upper(): i for i in db.scalars(select(Item))}
    wh_scope = scope_ids(user, "warehouse")
    used_whs = set(db.scalars(select(StockMovement.warehouse_id).where(StockMovement.kind != "opening")))
    seen: set[tuple[int, int]] = set()
    rows, errors = [], []
    for n, raw in enumerate(rows_iter, start=2):
        if raw is None or all(v in (None, "") for v in raw[:5]):
            continue
        wc, ic = (str(raw[0] or "").strip().upper(), str(raw[1] or "").strip().upper())
        row = {"row": n, "warehouse_code": wc, "item_code": ic, "errors": []}
        w, it = whs.get(wc), items.get(ic)
        if not w:
            row["errors"].append(f"Unknown warehouse '{wc}'")
        elif not in_scope(user, branch_id=w.branch_id) or (wh_scope is not None and w.id not in wh_scope):
            row["errors"].append(f"Warehouse '{wc}' is outside your scope")
        elif w.id in used_whs:
            row["errors"].append(f"Warehouse '{wc}' already has stock movements; opening stock is closed")
        if not it:
            row["errors"].append(f"Unknown item '{ic}'")
        qtys = {}
        for i, col in enumerate(COLUMNS[2:], start=2):
            q = _int(raw[i] if len(raw) > i else None)
            if q is None:
                row["errors"].append(f"{col} must be a whole number, 0 or more")
            qtys[STATUS_COLS[col]] = q or 0
        if w and it:
            if (w.id, it.id) in seen:
                row["errors"].append("Same warehouse and item appear twice")
            seen.add((w.id, it.id))
            row.update(warehouse_id=w.id, item_id=it.id, item_name=it.name)
        row["qty"] = qtys
        if not row["errors"] and sum(qtys.values()) == 0:
            continue  # nothing to load
        rows.append(row)
        errors.extend(f"Row {n}: {e}" for e in row["errors"])
    totals: dict[str, int] = defaultdict(int)
    for r in rows:
        for s, q in r["qty"].items():
            totals[s] += q
    if not rows and not errors:
        errors.append("The sheet has no quantities")
    return {"ok": not errors, "errors": errors, "rows": rows, "totals": dict(totals)}


def commit(db: Session, user: User, parsed: dict, note: str | None) -> list[StockMovement]:
    by_wh: dict[int, list[stock.Line]] = defaultdict(list)
    for r in parsed["rows"]:
        for status, q in r["qty"].items():
            if q:
                by_wh[r["warehouse_id"]].append(stock.Line("warehouse", r["warehouse_id"], r["item_id"], status, q))
    return [
        stock.post(
            db,
            kind="opening",
            lines=lines,
            user_id=user.id,
            warehouse_id=wh_id,
            reason="Opening stock import",
            note=note,
            source=("import", 0),
        )
        for wh_id, lines in sorted(by_wh.items())
    ]
