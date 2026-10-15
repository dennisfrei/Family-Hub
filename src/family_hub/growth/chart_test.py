from datetime import date
from pathlib import Path

from family_hub.growth.chart import growth_chart, sds_chart, velocity_chart
from family_hub.growth.conftest import write_reference
from family_hub.growth.metrics import VelocityBin
from family_hub.growth.models import MeasurementType
from family_hub.growth.reference import parse_reference
from family_hub.growth.schemas import MeasurementRead


def _measurement(age: float, z: float | None) -> MeasurementRead:
    return MeasurementRead(
        id=1,
        person_id=1,
        type=MeasurementType.LENGTH,
        value=80.0,
        unit="cm",
        measured_on=date(2024, 1, 1),
        official=True,
        age_months=age,
        z=z,
        percentile=50.0 if z is not None else None,
    )


def test_growth_chart_with_and_without_reference(tmp_path: Path) -> None:
    write_reference(tmp_path / "ref.csv")
    reference = parse_reference(tmp_path / "ref.csv")
    measurements = [_measurement(10.0, 0.1), _measurement(30.0, 0.2)]

    with_reference = growth_chart(measurements, MeasurementType.LENGTH, reference, age_now=31.0)
    without = growth_chart(measurements, MeasurementType.LENGTH, None, age_now=31.0)

    assert len(with_reference.data) == 8
    assert len(without.data) == 1
    assert with_reference.layout.xaxis.title.text == "Alter (Jahre)"


def test_sds_and_velocity_charts() -> None:
    bins = [
        VelocityBin(
            age_start=0.0,
            age_end=1.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 2, 1),
            velocity=2.0,
            reference_velocity=1.9,
        )
    ]

    assert len(sds_chart([_measurement(5.0, 0.3)], age_now=6.0).data) == 1
    assert len(velocity_chart(bins, MeasurementType.LENGTH).data) == 2
