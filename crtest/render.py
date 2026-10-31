"""ReportLab helpers: page templates, formatting variants, layout hazards."""
from __future__ import annotations

import datetime as dt
import io
import os
import random
import re
import subprocess
import tempfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, FrameBreak, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
SYNTHETIC_MARK = "SYNTHETIC TEST DOCUMENT - fictional authority and supplier - not a real notice"

_ss = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_ss["Title"], fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=4, alignment=0),
    "subtitle": ParagraphStyle("subtitle", parent=_ss["Normal"], fontName="Helvetica", fontSize=10.5, leading=14, textColor=colors.HexColor("#333333"), spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, spaceBefore=9, spaceAfter=4),
    "body": ParagraphStyle("body", parent=_ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=5),
    "small": ParagraphStyle("small", parent=_ss["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#444444")),
    "cell": ParagraphStyle("cell", parent=_ss["Normal"], fontName="Helvetica", fontSize=8.6, leading=10.8),
    "cellb": ParagraphStyle("cellb", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=8.6, leading=10.8),
    "label": ParagraphStyle("label", parent=_ss["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#555555")),
    "value": ParagraphStyle("value", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12.5, spaceAfter=6),
}


# ---------------------------------------------------------------- formatting
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def fmt_date(d: dt.date | str | None, style: str = "long") -> str:
    if d is None:
        return "Not stated"
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    if style == "long":
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    if style == "ordinal":
        return f"{ordinal(d.day)} {MONTHS[d.month - 1]} {d.year}"
    if style == "uk":
        return d.strftime("%d/%m/%Y")
    if style == "iso":
        return d.isoformat()
    if style == "abbr":
        return d.strftime("%d-%b-%Y")
    raise ValueError(style)


def _words(n: int) -> str:
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def chunk(x: int) -> str:
        out = []
        if x >= 100:
            out.append(ones[x // 100] + " hundred")
            x %= 100
            if x:
                out.append("and")
        if x >= 20:
            out.append(tens[x // 10] + (("-" + ones[x % 10]) if x % 10 else ""))
        elif x:
            out.append(ones[x])
        return " ".join(out)

    if n == 0:
        return "zero"
    parts = []
    for div, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand"), (1, "")):
        q, n = divmod(n, div)
        if q:
            parts.append((chunk(q) + (" " + name if name else "")).strip())
    return " ".join(parts)


def fmt_money(v: float | int | None, style: str = "standard", vat_note: str | None = None) -> str:
    if v is None:
        return "Not stated"
    v = float(v)
    if style == "standard":
        s = f"£{v:,.2f}"
    elif style == "nodp":
        s = f"£{v:,.0f}"
    elif style == "short":
        s = f"£{v / 1e6:.2f}m".replace(".00m", "m") if v >= 1e6 else f"£{v / 1e3:.0f}k"
    elif style == "spaced":
        s = "£" + f"{v:,.0f}".replace(",", " ")
    elif style == "gbp_suffix":
        s = f"{v:,.2f} GBP"
    elif style == "words":
        s = f"{_words(int(round(v)))} pounds (£{v:,.0f})"
    else:
        raise ValueError(style)
    if vat_note:
        s += f" {vat_note}"
    return s


def fmt_cpv(codes: list[str]) -> str:
    return ", ".join(codes)


def months_between(a: dt.date, b: dt.date) -> int:
    """Whole months from a to the day after b (contract terms end on the day before an anniversary)."""
    b1 = b + dt.timedelta(days=1)
    return (b1.year - a.year) * 12 + (b1.month - a.month)


# ---------------------------------------------------------------- page furniture
class NumberedCanvas(canvas.Canvas):
    """Canvas that knows the total page count so footers can print 'Page x of y'."""

    def __init__(self, *args, footer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._footer = footer

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._footer:
                self._footer(self, self._pageNumber, total)
            super().showPage()
        super().save()


def make_footer(authority: str, doc_label: str, footer_style: str = "standard"):
    def footer(c: canvas.Canvas, page: int, total: int):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#555555"))
        y = 11 * mm
        if footer_style == "standard":
            c.drawString(MARGIN, y, f"{authority} · {doc_label}")
            c.drawRightString(PAGE_W - MARGIN, y, f"Page {page} of {total}")
        elif footer_style == "centred":
            c.drawCentredString(PAGE_W / 2, y, f"{doc_label} — {authority} — page {page}/{total}")
        c.setFont("Helvetica-Oblique", 6.8)
        c.setFillColor(colors.HexColor("#8a1c1c"))
        c.drawCentredString(PAGE_W / 2, 6.5 * mm, SYNTHETIC_MARK)
        c.restoreState()
    return footer


def build_pdf(path: str, story: list, authority: str, doc_label: str, two_column: bool = False,
              footer_style: str = "standard", header: str | None = None) -> None:
    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN + (6 * mm if header else 0), bottomMargin=MARGIN,
                          title=doc_label, author=authority, subject="Synthetic test document")
    width = PAGE_W - 2 * MARGIN
    height = PAGE_H - doc.topMargin - doc.bottomMargin

    def on_page(c: canvas.Canvas, d):
        if header:
            c.saveState()
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(colors.HexColor("#1f3a5f"))
            c.drawString(MARGIN, PAGE_H - MARGIN + 2 * mm, header)
            c.setStrokeColor(colors.HexColor("#1f3a5f"))
            c.setLineWidth(0.6)
            c.line(MARGIN, PAGE_H - MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN)
            c.restoreState()

    templates = []
    full = Frame(MARGIN, doc.bottomMargin, width, height, id="full", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    if two_column:
        # First page: a full-width heading band, then two columns. Story order: heading, FrameBreak, left, FrameBreak, right.
        gutter = 8 * mm
        lw = width * 0.38
        rw = width - lw - gutter
        band_h = 26 * mm
        col_h = height - band_h
        band = Frame(MARGIN, doc.bottomMargin + col_h, width, band_h, id="band", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        left = Frame(MARGIN, doc.bottomMargin, lw, col_h, id="left", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        right = Frame(MARGIN + lw + gutter, doc.bottomMargin, rw, col_h, id="right", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        templates.append(PageTemplate(id="two", frames=[band, left, right], onPage=on_page))
    templates.append(PageTemplate(id="full", frames=[full], onPage=on_page))
    doc.addPageTemplates(templates)
    doc.build(story, canvasmaker=lambda *a, **k: NumberedCanvas(*a, footer=make_footer(authority, doc_label, footer_style), **k))


# ---------------------------------------------------------------- flowable builders
_ENTITY = re.compile(r"&(?!(?:amp|lt|gt|nbsp|quot|#\d+);)")


def esc(text: str) -> str:
    """Escape bare ampersands and angle brackets for ReportLab's mini-HTML."""
    return _ENTITY.sub("&amp;", str(text)).replace("<", "&lt;").replace(">", "&gt;") if text is not None else ""


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(esc(text), STYLES[style])


def kv_table_grid(rows: list[tuple[str, str]], col_widths=(58 * mm, None)) -> Table:
    width = PAGE_W - 2 * MARGIN
    cw = [col_widths[0], width - col_widths[0]]
    data = [[Paragraph(esc(k), STYLES["cellb"]), Paragraph(esc(v), STYLES["cell"])] for k, v in rows]
    t = Table(data, colWidths=cw, repeatRows=0)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9a9a9a")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def kv_table_borderless_grouped(groups: list[tuple[str, list[tuple[str, str]]]]) -> Table:
    """Three columns: group label (printed once per group), label, value. No rules at all."""
    width = PAGE_W - 2 * MARGIN
    data = []
    spans = []
    for g, rows in groups:
        start = len(data)
        for i, (k, v) in enumerate(rows):
            data.append([Paragraph(esc(g) if i == 0 else "", STYLES["cellb"]), Paragraph(esc(k), STYLES["cell"]), Paragraph(esc(v), STYLES["cell"])])
        spans.append((start, len(data) - 1))
    t = Table(data, colWidths=[34 * mm, 58 * mm, width - 92 * mm])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for s, e in spans:
        style.append(("SPAN", (0, s), (0, e)))
        style.append(("LINEBELOW", (0, e), (-1, e), 0, colors.white))
    t.setStyle(TableStyle(style))
    return t


def data_table(header: list[str], rows: list[list[str]], col_widths: list[float], total_row: list[str] | None = None,
               grid: bool = True, repeat_header: bool = True, align_right_cols: tuple[int, ...] = ()) -> Table:
    data = [[Paragraph(esc(h), STYLES["cellb"]) for h in header]]
    for r in rows:
        data.append([Paragraph(esc(c), STYLES["cell"]) for c in r])
    if total_row:
        data.append([Paragraph(esc(c), STYLES["cellb"]) for c in total_row])
    t = Table(data, colWidths=col_widths, repeatRows=1 if repeat_header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe6ef")),
    ]
    if grid:
        style.append(("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8c8c8c")))
    else:
        style.append(("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#333333")))
    if total_row:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#333333")))
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f3f3")))
    for c in align_right_cols:
        style.append(("ALIGN", (c, 1), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def stacked_kv(rows: list[tuple[str, str]]) -> list:
    out = []
    for k, v in rows:
        out.append(Paragraph(esc(k), STYLES["label"]))
        out.append(Paragraph(esc(v), STYLES["value"]))
    return out


def signature_block(authority_officer: str, supplier: str, date_text: str) -> Table:
    width = PAGE_W - 2 * MARGIN
    data = [
        [Paragraph("Signed for and on behalf of the Authority", STYLES["cell"]), Paragraph("Signed for and on behalf of the Supplier", STYLES["cell"])],
        [Paragraph("<br/><br/>______________________________<br/>" + esc(authority_officer), STYLES["cell"]),
         Paragraph("<br/><br/>______________________________<br/>Director, " + esc(supplier), STYLES["cell"])],
        [Paragraph("Date: " + date_text, STYLES["cell"]), Paragraph("Date: " + date_text, STYLES["cell"])],
    ]
    t = Table(data, colWidths=[width / 2, width / 2])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


# ---------------------------------------------------------------- scanned simulation
def rasterise_to_scanned_pdf(src_pdf: str, dst_pdf: str, seed: int = 1, dpi: int = 120, skew_deg: float = 0.7) -> None:
    """Replace a text PDF by an image-only PDF that looks like a photocopy scan."""
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", src_pdf, os.path.join(td, "p")], check=True)
        pages = sorted(f for f in os.listdir(td) if f.endswith(".png"))
        c = canvas.Canvas(dst_pdf, pagesize=A4)
        c.setTitle("Scanned contract (synthetic)")
        for name in pages:
            im = Image.open(os.path.join(td, name)).convert("L")
            angle = skew_deg * rnd.choice((-1, 1))
            im = im.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=245)
            im = im.filter(ImageFilter.GaussianBlur(0.55))
            # light speckle noise
            px = im.load()
            w, h = im.size
            for _ in range(int(w * h * 0.0012)):
                x, y = rnd.randrange(w), rnd.randrange(h)
                px[x, y] = rnd.choice((40, 60, 200, 215))
            # slightly grey background band like a photocopier edge
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=58, optimize=True)
            buf.seek(0)
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(buf), 0, 0, width=PAGE_W, height=PAGE_H)
            c.showPage()
        c.save()


def pdf_page_count(path: str) -> int:
    from pypdf import PdfReader
    return len(PdfReader(path).pages)
