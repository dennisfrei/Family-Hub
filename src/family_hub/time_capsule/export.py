"""Exports: JSON, Markdown and the yearly PDF booklet per child."""

import json
from pathlib import Path

import matplotlib
from fpdf import FPDF

from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryRead
from family_hub.ui import i18n
from family_hub.ui.i18n import t

A5_MM = (148, 210)
TEXT_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
EMOJI_FONT = Path(__file__).parent / "fonts" / "NotoEmoji.ttf"
FONT = "DejaVu"
TEXT_FONTS = {"": "DejaVuSans.ttf", "B": "DejaVuSans-Bold.ttf", "I": "DejaVuSans-Oblique.ttf"}
EMOJI_WEIGHTS = {"": 400, "B": 600, "I": 400}


def to_json(entries: list[EntryRead]) -> str:
    """All entries as pretty JSON."""
    return json.dumps([entry.model_dump(mode="json") for entry in entries], ensure_ascii=False, indent=2)


def _children_line(entry: EntryRead) -> str:
    return ", ".join(
        f"{child.name} ({i18n.format_age(child.age_months)})" if child.age_months is not None else child.name
        for child in entry.children
    )


def to_markdown(entries: list[EntryRead], title: str) -> str:
    """Entries grouped by month, oldest first."""
    lines = [f"# {title}", ""]
    month = None
    for entry in sorted(entries, key=lambda e: (e.date, e.id)):
        if (entry.date.year, entry.date.month) != month:
            month = (entry.date.year, entry.date.month)
            lines += [f"## {i18n.month_year(entry.date)}", ""]
        lines.append(f"### {i18n.day(entry.date)} · {t(f'tc.type.{entry.type.value}')} · {_children_line(entry)}")
        lines.append("")
        lines.append(f"> {entry.text}" if entry.type is EntryType.SAYING else entry.text)
        if entry.context:
            lines += ["", f"*{entry.context}*"]
        if entry.tags:
            lines += ["", " ".join(f"#{tag}" for tag in entry.tags)]
        lines.append("")
    return "\n".join(lines)


def _quoted(text: str) -> str:
    return f"„{text}“" if i18n.language() is i18n.Language.DE else f"“{text}”"


def _new_pdf() -> FPDF:
    pdf = FPDF(format=A5_MM)
    for style, file_name in TEXT_FONTS.items():
        pdf.add_font(FONT, style, TEXT_FONT_DIR / file_name)
        pdf.add_font("Emoji", style, EMOJI_FONT, variations={"wght": EMOJI_WEIGHTS[style]})
    pdf.set_fallback_fonts(["Emoji"])
    return pdf


def booklet_pdf(entries: list[EntryRead], child_name: str, year: int) -> bytes:
    """A5 booklet: title page, then one block per entry in chronological order."""
    pdf = _new_pdf()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(f"{t('tc.title')} {child_name} {year}")
    pdf.add_page()
    pdf.set_font(FONT, "B", 28)
    pdf.ln(45)
    pdf.cell(0, 14, t("tc.title"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 20)
    pdf.cell(0, 12, child_name, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 16)
    pdf.cell(0, 10, str(year), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font(FONT, "I", 11)
    pdf.cell(0, 8, t("tc.booklet_count", n=len(entries)), align="C")

    pdf.add_page()
    for entry in sorted(entries, key=lambda e: (e.date, e.id)):
        ages = ", ".join(i18n.format_age(c.age_months) for c in entry.children if c.age_months is not None)
        header = " · ".join(part for part in (i18n.day(entry.date), ages, t(f"tc.type.{entry.type.value}")) if part)
        pdf.set_font(FONT, "B", 9)
        pdf.set_text_color(31, 111, 99)
        pdf.multi_cell(0, 5, header, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        if entry.type is EntryType.SAYING:
            pdf.set_font(FONT, "I", 13)
            pdf.multi_cell(0, 6.5, _quoted(entry.text), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(FONT, "B" if entry.type is EntryType.MILESTONE else "", 11)
            pdf.multi_cell(0, 5.5, entry.text, new_x="LMARGIN", new_y="NEXT")
        if entry.context:
            pdf.set_font(FONT, "", 9)
            pdf.set_text_color(100, 116, 139)
            pdf.multi_cell(0, 4.5, entry.context, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        pdf.ln(5)
    return bytes(pdf.output())
