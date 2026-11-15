from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from family_hub.blood_pressure import export
from family_hub.blood_pressure.levels import Level
from family_hub.blood_pressure.schemas import ReadingRead
from family_hub.blood_pressure.stats import Average

TZ = ZoneInfo("Europe/Berlin")
LIMITS = ((130, 85), (140, 90))
READINGS = [
    ReadingRead(
        id=2,
        person_id=1,
        systolic=142,
        diastolic=88,
        pulse=70,
        measured_at=datetime(2026, 7, 2, 6, tzinfo=UTC),
        level=Level.HIGH,
        note="<b>nach Sport</b>",
    ),
    ReadingRead(
        id=1,
        person_id=1,
        systolic=118,
        diastolic=76,
        measured_at=datetime(2026, 7, 1, 6, tzinfo=UTC),
        level=Level.NORMAL,
    ),
]
AVERAGE = Average(systolic=130, diastolic=82, pulse=70, count=2, by_days=False, level=Level.ELEVATED)


def test_html_report() -> None:
    html = export.to_html("Alex & Co", READINGS, AVERAGE, LIMITS, TZ)

    assert "Blutdruck Alex &amp; Co" in html
    assert "2 Messungen, 01.07.2026 bis 02.07.2026" in html
    assert "Ø letzte 2 Messungen: 130/82 mmHg · Puls 70" in html
    assert '<tr class="high"><td>02.07.2026</td><td>08:00</td><td>142</td>' in html
    assert "&lt;b&gt;nach Sport&lt;/b&gt;" in html
    assert "Grenzwerte: erhöht ab 130/85 mmHg, hoch ab 140/90 mmHg" in html
    assert '<img alt="" src="data:image/png;base64,' in html
    assert "<img" not in export.to_html("Alex", READINGS[:1], None, LIMITS, TZ)


def test_chart_png() -> None:
    assert (export.chart_png(READINGS, LIMITS[1], TZ) or b"").startswith(b"\x89PNG")
    assert export.chart_png(READINGS[:1], LIMITS[1], TZ) is None


def test_pdf_report() -> None:
    assert export.to_pdf("Alex", READINGS, AVERAGE, LIMITS, TZ).startswith(b"%PDF")
    assert export.to_pdf("Alex", [], None, LIMITS, TZ).startswith(b"%PDF")
