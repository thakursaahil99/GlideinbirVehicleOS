"""Invoice PDF rendering with ReportLab (pure Python, no system dependencies)."""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#4535c9")
MUTED = colors.HexColor("#64748b")


def _money(value):
    return f"Rs. {value:,.2f}"


def render_invoice_pdf(invoice):
    buf = BytesIO()
    org = invoice.organization
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=invoice.invoice_number, author="Glideinbir")
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, leading=11)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9.5, leading=13)
    heading = ParagraphStyle("heading", parent=styles["Heading1"], fontSize=18, textColor=BRAND, spaceAfter=2)

    org_lines = [org.legal_name or org.name, org.address, f"{org.city} {org.state} {org.pincode}".strip(),
                 f"Phone: {org.phone} · {org.email}"]
    if org.gst_number:
        org_lines.append(f"GSTIN: {org.gst_number}")
    customer = invoice.customer
    cust_lines = [customer.full_name, customer.phone, customer.email, customer.address, customer.city]

    story = [
        Table([[Paragraph(f"<b>{org.name}</b>", heading), Paragraph("<b>TAX INVOICE</b>", heading)]],
              colWidths=[110 * mm, 64 * mm], style=[("ALIGN", (1, 0), (1, 0), "RIGHT")]),
        Table([[Paragraph("<br/>".join(filter(None, org_lines)), small),
                Paragraph(f"<b>{invoice.invoice_number}</b><br/>Date: {invoice.invoice_date:%d %b %Y}"
                          + (f"<br/>Booking: {invoice.booking.booking_number}" if invoice.booking_id else "")
                          + f"<br/>Status: {invoice.payment_status.replace('_', ' ').title()}", normal)]],
              colWidths=[110 * mm, 64 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                     ("ALIGN", (1, 0), (1, 0), "RIGHT")]),
        Spacer(1, 6 * mm),
        Paragraph("<b>Bill to</b>", normal),
        Paragraph("<br/>".join(filter(None, cust_lines)), small),
    ]
    if invoice.booking_id:
        v = invoice.booking.vehicle
        story.append(Paragraph(f"Vehicle: {v.brand} {v.model} — {v.registration_number}", small))
    story.append(Spacer(1, 6 * mm))

    rows = [["#", "Description", "Qty", "Rate", "GST %", "Tax", "Amount"]]
    for i, item in enumerate(invoice.items.all(), start=1):
        rows.append([str(i), Paragraph(item.description, normal), f"{item.quantity:g}", _money(item.unit_price),
                     f"{item.tax_rate:g}", _money(item.tax_amount), _money(item.total)])
    table = Table(rows, colWidths=[8 * mm, 66 * mm, 12 * mm, 24 * mm, 14 * mm, 22 * mm, 28 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7fb")]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, MUTED),
    ]))
    story += [table, Spacer(1, 4 * mm)]

    totals = [["Subtotal", _money(invoice.subtotal)]]
    if invoice.discount:
        totals.append(["Discount", f"- {_money(invoice.discount)}"])
    totals += [["GST", _money(invoice.tax)], ["Total", _money(invoice.total)], ["Paid", _money(invoice.amount_paid)],
               ["Balance due", _money(invoice.balance_due)]]
    story.append(Table(totals, colWidths=[140 * mm, 34 * mm], style=[
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"), ("TEXTCOLOR", (0, 3), (-1, 3), BRAND),
    ]))
    if invoice.notes:
        story += [Spacer(1, 5 * mm), Paragraph(f"<b>Notes:</b> {invoice.notes}", small)]
    story += [Spacer(1, 10 * mm),
              Paragraph(f"Generated {timezone.localtime():%d %b %Y %H:%M} · Glideinbir · "
                        "<b>Built by Sahil Thakur</b>", small)]
    doc.build(story)
    return buf.getvalue()
