"""
Build a downloadable PDF impact report with optional "what changed" per label.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from io import BytesIO

from fpdf import FPDF

from scrapers.dailymed import LabelUpdate


def _sanitize(s: str, max_len: int = 2000) -> str:
    """Remove characters that can break fpdf2 and truncate."""
    s = (s or "").encode("latin-1", errors="replace").decode("latin-1")
    return s[:max_len] if len(s) > max_len else s


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, "LabelWatch AI - FDA DailyMed Impact Report", ln=True)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.multi_cell(0, 6, _sanitize(title[:200]))
        self.ln(2)

    def body_text(self, text: str, max_per_cell: int = 2500):
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, _sanitize(text, max_per_cell))
        self.ln(2)


def build_pdf(
    matches: list[LabelUpdate],
    change_texts: list[str],
    fda_validation: list[tuple[str, int | None]] | None = None,
) -> bytes:
    """
    Build PDF bytes. change_texts[i] is the "what changed" summary for matches[i].
    fda_validation[i] = (message, lag_days) for FDA cross-check per label.
    """
    pdf = ReportPDF()
    pdf.add_page()
    pdf.section_title("Label Updates (Last 7 Days) - Watchlist Matches")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, f"This report contains {len(matches)} label(s) from the FDA DailyMed feed.")
    pdf.ln(4)

    for i, label in enumerate(matches):
        change = change_texts[i] if i < len(change_texts) else ""
        pdf.section_title(label.title[:180] + ("..." if len(label.title) > 180 else ""))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"Updated: {_sanitize(label.updated_date or label.pub_date, 80)}", ln=True)
        pdf.cell(0, 5, f"Set ID: {label.setid}  |  Version: {label.version}", ln=True)
        pdf.cell(0, 5, f"Link: {_sanitize(label.link, 120)}", ln=True)
        if fda_validation and i < len(fda_validation):
            msg, _ = fda_validation[i]
            pdf.cell(0, 5, f"FDA cross-check: {_sanitize(msg, 150)}", ln=True)
        pdf.ln(2)

        if change:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, "What changed in this label:", ln=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.body_text(change, max_per_cell=3000)
        else:
            pdf.set_font("Helvetica", "", 8)
            pdf.multi_cell(0, 5, "No change summary (use live data with 'Include what changed' for diff).")
            pdf.ln(2)
        pdf.ln(2)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
