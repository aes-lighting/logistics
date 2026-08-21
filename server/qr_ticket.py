"""
qr_ticket.py

Generates a one-page printable PDF for a checked-in shipment: a QR code
(linking back to that shipment's record in the app) plus human-readable
details underneath, so it's identifiable at a glance even without scanning.

No printer is wired up yet (none has been purchased) — this just produces
the PDF. The "Print" action in the app opens this PDF, and the browser's
own print dialog sends it to whatever printer is set up on that device.
Once a specific printer is chosen, direct network printing (its make/model
determines the right approach — e.g. IPP) can replace this if wanted.
"""

import io

import qrcode
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def _font(name, size):
    import os
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def build_qr_pdf(entry_id, job_number, po_number, base_url, locations, pallet_count):
    """
    base_url: the app's public URL (e.g. https://yourdomain.com) so the QR
    code links to a real, reachable page for this entry.
    Returns PDF bytes (single page).
    """
    detail_url = f"{base_url.rstrip('/')}/inventory/{entry_id}"

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(detail_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    width = 500
    qr_size = 320
    height = qr_size + 260

    page = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(page)

    title_font = _font("DejaVuSans-Bold.ttf", 20)
    label_font = _font("DejaVuSans-Bold.ttf", 13)
    text_font = _font("DejaVuSans.ttf", 14)

    d.text((20, 16), "AES LOGISTICS — RECEIVING", font=title_font, fill="black")

    qr_resized = qr_img.resize((qr_size, qr_size))
    qr_x = (width - qr_size) // 2
    page.paste(qr_resized, (qr_x, 55))

    y = 55 + qr_size + 14
    locations_str = ", ".join(f"{loc['location']} ({loc['count']})" for loc in (locations or []))

    lines = [
        ("JOB #", job_number),
        ("PO #", po_number or "(none)"),
        ("PALLETS", str(pallet_count)),
        ("LOCATION(S)", locations_str or "(none)"),
    ]
    for label, value in lines:
        d.text((20, y), label, font=label_font, fill="#555555")
        d.text((140, y), str(value), font=text_font, fill="black")
        y += 26

    buf = io.BytesIO()
    page.save(buf, format="PDF")
    return buf.getvalue()
