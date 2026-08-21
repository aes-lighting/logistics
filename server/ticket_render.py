"""
ticket_render.py

Renders a delivery ticket (job info + line items) as a PNG image, for the
PM Portal's "Generate Ticket" feature. Laid out to match AES Lighting
Group's actual "Delivery Receipt" paper form, so a generated ticket looks
like the real thing rather than a generic placeholder.

This produces the same kind of artifact as a photo of a paper ticket would
— everything downstream (the driver's ticket-view screen, the warehouse
packing screen, emailing) treats an uploaded and a generated ticket
identically.

Column meaning (matches the paper form):
    LOADED    — warehouse checks this off as each item is pulled/packed
                (this is the existing Outgoing Inventory packing step)
    DELIVERED — the driver checks this off as each item is unloaded on site
    RECEIVED  — reserved for future use; not yet checked off anywhere in
                the app (the receiver's overall signature covers this today)
The checkbox squares on the generated image are always empty — the real
checked/unchecked state lives in the app's data and is shown there, not
edited into this image after the fact.
"""

import io
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"

COMPANY_NAME = "AES Lighting Group"
COMPANY_ADDRESS = "32 S Jefferson Road, Whippany, NJ 07981  \u00b7  Phone: (973) 515-2090  \u00b7  Fax: (973) 515-2065"

# Column layout for the line-items table: (header, width, align).
# x positions are computed automatically from widths so they can never drift out of sync.
COLUMN_DEFS = [
    ("TYPE", 60, "left"),
    ("QTY", 38, "center"),
    ("BOXES", 46, "center"),
    ("MODEL #", 90, "left"),
    ("DESCRIPTION", 230, "left"),
    ("MFG", 65, "left"),
    ("LOADED", 62, "center"),
    ("DELIVERED", 78, "center"),
    ("RECEIVED", 68, "center"),
]
TABLE_LEFT = 30


def _compute_columns():
    cols = []
    x = TABLE_LEFT
    for header, w, align in COLUMN_DEFS:
        cols.append((header, x, w, align))
        x += w
    return cols, x  # cols, right_edge


COLUMNS, TABLE_RIGHT = _compute_columns()


def _font(name, size):
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_checkbox(d, cx, cy, size=14):
    d.rectangle([(cx - size // 2, cy - size // 2), (cx + size // 2, cy + size // 2)], outline="black", width=1)


def _fit_text(d, text, font, max_width):
    """Truncates with an ellipsis if the text is wider than max_width, so a
    long value can never bleed into the next column regardless of content."""
    if d.textlength(text, font=font) <= max_width:
        return text
    while text and d.textlength(text + "\u2026", font=font) > max_width:
        text = text[:-1]
    return text + "\u2026" if text else ""


def _field(d, x, y, label, value, label_font, text_font, label_color="#444444"):
    d.text((x, y), label, font=label_font, fill=label_color)
    d.text((x, y + 16), str(value) if value else "", font=text_font, fill="black")


def render_ticket_image(
    job_number,
    delivery_date,
    receiver_name,
    receiver_email,
    site_address,
    line_items,
    customer_name="",
    customer_po="",
    job_name="",
    delivery_method="",
    pm_name="",
):
    """
    line_items: list of dicts, each may contain:
        description (required), quantity, type, model_number, mfg, boxes
    Returns PNG bytes.
    """
    width = TABLE_RIGHT + 30
    row_height = 30
    header_height = 300
    footer_height = 340
    height = header_height + max(len(line_items), 1) * row_height + footer_height

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    company_font = _font("DejaVuSans-Bold.ttf", 20)
    title_font = _font("DejaVuSans-Bold.ttf", 22)
    label_font = _font("DejaVuSans-Bold.ttf", 11)
    text_font = _font("DejaVuSans.ttf", 14)
    header_font = _font("DejaVuSans-Bold.ttf", 9)
    small_font = _font("DejaVuSans.ttf", 10)
    ack_font = _font("DejaVuSans.ttf", 9)

    # --- Top header: company name + form title ---
    y = 20
    d.text((30, y), COMPANY_NAME, font=company_font, fill="black")
    title_w = d.textlength("DELIVERY RECEIPT", font=title_font)
    d.text((width - 30 - title_w, y + 2), "DELIVERY RECEIPT", font=title_font, fill="black")
    y += 36
    d.line([(30, y), (width - 30, y)], fill="black", width=2)
    y += 14

    # --- Left block: Delivered To / Site Contact ---
    left_x = 30
    _field(d, left_x, y, "DELIVERED TO:", site_address or "", label_font, text_font)

    # --- Right block: Date / Customer / PO# / Job Name / Job # / Delivery Method ---
    right_x = width - 260
    ry = y
    field_gap = 30
    _field(d, right_x, ry, "DATE:", delivery_date, label_font, text_font)
    ry += field_gap
    _field(d, right_x, ry, "CUSTOMER:", customer_name, label_font, text_font)
    ry += field_gap
    _field(d, right_x, ry, "CUSTOMER PO#:", customer_po, label_font, text_font)
    ry += field_gap
    _field(d, right_x, ry, "JOB NAME:", job_name, label_font, text_font)
    ry += field_gap
    _field(d, right_x, ry, "AES JOB NUMBER:", job_number, label_font, text_font)
    ry += field_gap
    _field(d, right_x, ry, "DELIVERY METHOD:", delivery_method, label_font, text_font)

    y += field_gap
    _field(d, left_x, y, "SITE CONTACT:", f"{receiver_name}  ({receiver_email})" if receiver_email else receiver_name, label_font, text_font)
    y += 40
    _field(d, left_x, y, "AES PROJECT MANAGER:", pm_name, label_font, text_font)

    y = header_height - 15
    d.line([(30, y), (width - 30, y)], fill="#999999", width=1)
    y += 10

    # --- Line items table ---
    table_top = y
    d.rectangle([(30, y), (width - 30, y + 26)], fill="#EEEEEE", outline="black", width=1)
    for header, cx, cw, align in COLUMNS:
        tx = cx + 4 if align == "left" else cx + cw / 2 - d.textlength(header, font=header_font) / 2
        d.text((tx, y + 7), header, font=header_font, fill="#222222")
    y += 26

    items = line_items or [{}]
    for item in items:
        row_top = y
        for header, cx, cw, align in COLUMNS:
            if header in ("LOADED", "DELIVERED", "RECEIVED"):
                _draw_checkbox(d, int(cx + cw / 2), int(y + row_height / 2))
                continue
            key_map = {
                "TYPE": "type", "QTY": "quantity", "BOXES": "boxes",
                "MODEL #": "model_number", "DESCRIPTION": "description", "MFG": "mfg",
            }
            value = str(item.get(key_map[header], "") or "")
            if not value:
                continue
            value = _fit_text(d, value, text_font, cw - 8)
            tx = cx + 4 if align == "left" else cx + cw / 2 - d.textlength(value, font=text_font) / 2
            d.text((tx, y + 6), value, font=text_font, fill="black")
        y += row_height
        d.line([(30, y), (width - 30, y)], fill="#DDDDDD", width=1)

    # Vertical column separators for the whole table
    table_bottom = y
    for header, cx, cw, align in COLUMNS[1:]:
        d.line([(cx - 3, table_top), (cx - 3, table_bottom)], fill="#DDDDDD", width=1)
    d.rectangle([(30, table_top), (width - 30, table_bottom)], outline="black", width=1)

    y += 20
    d.text((30, y), "REMARKS:", font=label_font, fill="#444444")
    y += 34
    d.line([(30, y), (width - 30, y)], fill="#CCCCCC", width=1)
    y += 30

    # --- Signature blocks ---
    col2_x = width // 2 + 10
    d.text((30, y), "WAREHOUSE MANAGER \u2014 PRINT NAME", font=small_font, fill="#444444")
    d.text((col2_x, y), "WAREHOUSE MANAGER \u2014 SIGNATURE / DATE", font=small_font, fill="#444444")
    y += 26
    d.line([(30, y), (width // 2 - 15, y)], fill="black", width=1)
    d.line([(col2_x, y), (width - 30, y)], fill="black", width=1)
    y += 26

    d.text((30, y), "DRIVER \u2014 PRINT NAME", font=small_font, fill="#444444")
    d.text((col2_x, y), "DRIVER \u2014 SIGNATURE / DATE", font=small_font, fill="#444444")
    y += 26
    d.line([(30, y), (width // 2 - 15, y)], fill="black", width=1)
    d.line([(col2_x, y), (width - 30, y)], fill="black", width=1)
    y += 26

    d.text((30, y), "RECEIVED BY \u2014 PRINT NAME", font=small_font, fill="#444444")
    d.text((col2_x, y), "RECEIVED BY \u2014 SIGNATURE / DATE", font=small_font, fill="#444444")
    y += 26
    d.line([(30, y), (width // 2 - 15, y)], fill="black", width=1)
    d.line([(col2_x, y), (width - 30, y)], fill="black", width=1)
    y += 22

    ack_text = (
        "I ACKNOWLEDGE ALL MATERIAL LISTED ABOVE HAS BEEN RECEIVED AND ACCOUNTED FOR. ANY DISCREPANCY BETWEEN THE "
        "LISTED QUANTITY AND MY ACCOUNTING HAS BEEN NOTED ABOVE, AND HAS BEEN ACKNOWLEDGED AND INITIALLED BY ME "
        "AND BY THE AES DELIVERY DRIVER."
    )
    words = ack_text.split()
    line = ""
    max_w = width - 60
    for word in words:
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=ack_font) > max_w:
            d.text((30, y), line, font=ack_font, fill="#333333")
            y += 13
            line = word
        else:
            line = trial
    if line:
        d.text((30, y), line, font=ack_font, fill="#333333")
        y += 13

    y += 10
    d.line([(30, y), (width - 30, y)], fill="#CCCCCC", width=1)
    y += 8
    d.text((30, y), f"{COMPANY_NAME}  \u00b7  {COMPANY_ADDRESS}", font=small_font, fill="#888888")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
