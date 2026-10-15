import json
from datetime import UTC, date, datetime

from family_hub.time_capsule.export import booklet_pdf, to_json, to_markdown
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryChild, EntryRead

ENTRIES = [
    EntryRead(
        id=1,
        text="Warum ist der Mond so rund? „Weil er satt ist“ – 🌙",
        type=EntryType.SAYING,
        date=date(2025, 3, 2),
        children=[EntryChild(person_id=1, name="Ada", color="#e91e63", age_months=35)],
        tags=["lustig"],
        created_at=datetime(2025, 3, 2, tzinfo=UTC),
        context="beim Abendessen",
    ),
    EntryRead(
        id=2,
        text="Fährt Fahrrad ohne Stützräder",
        type=EntryType.MILESTONE,
        date=date(2025, 6, 1),
        children=[EntryChild(person_id=1, name="Ada", color="#e91e63", age_months=38)],
        tags=[],
        created_at=datetime(2025, 6, 1, tzinfo=UTC),
    ),
]


def test_json() -> None:
    data = json.loads(to_json(ENTRIES))

    assert data[0]["text"].startswith("Warum")
    assert data[1]["type"] == "milestone"


def test_markdown_groups_by_month() -> None:
    markdown = to_markdown(ENTRIES, "Zeitkapsel")

    assert "## März 2025" in markdown
    assert "> Warum ist der Mond" in markdown
    assert "#lustig" in markdown
    assert "Ada (2 J. 11 Mon.)" in markdown


def test_pdf_handles_non_latin_characters() -> None:
    pdf = booklet_pdf(ENTRIES, "Ada", 2025)

    assert pdf.startswith(b"%PDF")
    assert b"DejaVuSans" in pdf
    assert b"NotoEmoji" in pdf
