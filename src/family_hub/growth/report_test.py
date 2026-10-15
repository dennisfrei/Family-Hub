from datetime import date
from pathlib import Path

import pytest

from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonRead
from family_hub.growth.conftest import value_at, write_reference
from family_hub.growth.metrics import age_months
from family_hub.growth.models import MeasurementType
from family_hub.growth.reference import parse_reference
from family_hub.growth.report import ReportData, build_csv, build_html, build_pdf
from family_hub.growth.schemas import MeasurementRead

BIRTH = date(2022, 1, 1)
PERSON = PersonRead(
    id=1, name="Ada", kind=PersonKind.CHILD, color="#000000", active=True, birth_date=BIRTH, sex=Sex.FEMALE
)


def _measurement(index: int, day: date, *, official: bool = True, z: float | None = 0.5) -> MeasurementRead:
    age = age_months(BIRTH, day)
    return MeasurementRead(
        id=index,
        person_id=1,
        type=MeasurementType.LENGTH,
        value=value_at(age, 0.5),
        unit="cm",
        measured_on=day,
        official=official,
        age_months=age,
        z=z,
        percentile=69.0 if z is not None else None,
    )


@pytest.fixture
def data(tmp_path: Path) -> ReportData:
    write_reference(tmp_path / "ref.csv")
    measurements = [
        _measurement(1, date(2022, 1, 1)),
        _measurement(2, date(2022, 4, 1), official=False),
        _measurement(3, date(2023, 1, 1)),
        _measurement(4, date(2024, 1, 1)),
    ]
    return ReportData(
        person=PERSON,
        measurements=measurements,
        references={MeasurementType.LENGTH: parse_reference(tmp_path / "ref.csv")},
        age_now=40.0,
    )


def test_csv_german(data: ReportData) -> None:
    lines = build_csv(data).decode("utf-8-sig").splitlines()

    assert lines[0].split(";")[:3] == ["Datum", "Alter", "Alter (Monate)"]
    assert len(lines) == 5
    assert "," in lines[1].split(";")[4]


def test_html_contains_charts_and_table(data: ReportData) -> None:
    page = build_html(data).decode()

    assert page.count('<section class="chart">') == 3
    assert "<svg" in page
    assert "Ada" in page


def test_pdf(data: ReportData) -> None:
    pdf = build_pdf(data)

    assert pdf.startswith(b"%PDF")


def test_report_without_reference_and_sds(data: ReportData) -> None:
    plain = ReportData(
        person=PERSON,
        measurements=[_measurement(1, date(2022, 1, 1), z=None)],
        references={},
        age_now=40.0,
    )

    assert build_pdf(plain).startswith(b"%PDF")
    assert '<section class="chart">' in build_html(plain).decode()
