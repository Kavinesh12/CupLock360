"""Delivery challan PDF (fpdf2, core fonts: amounts use 'Rs.' since core fonts have no rupee sign)."""

from datetime import timedelta

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Client, Dispatch, MaterialRequest, Project, Site, User, Warehouse
from app.services.requests import item_names

IST = timedelta(hours=5, minutes=30)


def _t(s) -> str:
    return str(s or "").encode("latin-1", "replace").decode("latin-1")


def render(db: Session, d: Dispatch) -> bytes:
    s = get_settings()
    r = db.get(MaterialRequest, d.request_id)
    site, wh = db.get(Site, d.site_id), db.get(Warehouse, d.warehouse_id)
    proj, cl = db.get(Project, r.project_id), db.get(Client, r.client_id)
    by = db.get(User, d.dispatched_by)
    items = item_names(db, [ln.item_id for ln in d.lines])

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, _t(s.company_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if s.company_gstin:
        pdf.cell(0, 5, _t(f"GSTIN {s.company_gstin}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, _t(f"Dispatched from {wh.code} - {wh.name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "DELIVERY CHALLAN (RETURNABLE - NOT FOR SALE)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    when = (d.dispatched_at + IST).strftime("%d %b %Y, %I:%M %p")
    left = [
        ("Challan no", d.challan_no),
        ("Date", when),
        ("Request", r.ref_no),
        ("Vehicle", d.vehicle_no or "-"),
        ("Driver", f"{d.driver_name or '-'}  {d.driver_phone or ''}"),
    ]
    right = [
        ("Client", f"{cl.code} - {cl.name}"),
        ("GSTIN", cl.gstin or "-"),
        ("Project", proj.name),
        ("Site", f"{site.code} - {site.name}"),
        ("Address", ", ".join(x for x in (site.address, site.city) if x) or "-"),
    ]
    y = pdf.get_y()
    for i, (k, v) in enumerate(left):
        pdf.set_xy(10, y + i * 6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(24, 6, _t(k))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(66, 6, _t(v))
    for i, (k, v) in enumerate(right):
        pdf.set_xy(105, y + i * 6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(20, 6, _t(k))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(75, 6, _t(v)[:55])
    pdf.set_xy(10, y + 6 * max(len(left), len(right)) + 4)

    widths = (10, 30, 80, 20, 25, 25)
    heads = ("#", "Item code", "Description", "HSN/SAC", "Qty (nos)", "Received")
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font("Helvetica", "B", 9)
    for w, h in zip(widths, heads, strict=True):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    total = 0
    for n, ln in enumerate(d.lines, 1):
        it = items[ln.item_id]
        total += ln.qty
        row = (
            str(n),
            it.code,
            it.name,
            it.hsn_sac or "",
            str(ln.qty),
            "" if ln.qty_received is None else str(ln.qty_received),
        )
        for i, (w, v) in enumerate(zip(widths, row, strict=True)):
            pdf.cell(w, 7, _t(v)[:48], border=1, align="R" if i >= 4 else "L")
        pdf.ln()
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(sum(widths[:4]), 7, "Total pieces", border=1, align="R")
    pdf.cell(widths[4], 7, str(total), border=1, align="R")
    pdf.cell(widths[5], 7, "", border=1)
    pdf.ln(12)

    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(
        0,
        4,
        _t(
            "Material is supplied on rent and remains the property of the company. Rent is charged from the date of "
            "receipt at site as per the agreed rate card. Shortages must be noted on this challan at receipt; "
            "damaged or missing items on return are charged at replacement cost."
        ),
    )
    pdf.ln(14)
    pdf.set_font("Helvetica", "", 9)
    y = pdf.get_y()
    for x, label in (
        (10, f"Dispatched by: {by.full_name}"),
        (75, "Driver signature"),
        (140, f"Received by: {d.receiver_name or ''}"),
    ):
        pdf.set_xy(x, y)
        pdf.cell(60, 5, "_" * 32)
        pdf.set_xy(x, y + 5)
        pdf.cell(60, 5, _t(label))
    if d.received_at:
        pdf.set_xy(140, y + 10)
        pdf.cell(60, 5, _t((d.received_at + IST).strftime("%d %b %Y, %I:%M %p")))
    return bytes(pdf.output())
