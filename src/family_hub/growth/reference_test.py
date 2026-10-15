from pathlib import Path

import pytest

from family_hub.growth.conftest import LMS_L, LMS_S, median_at, value_at, write_reference
from family_hub.growth.reference import parse_reference, z_to_percentile


def test_years_are_converted_to_months(tmp_path: Path) -> None:
    write_reference(tmp_path / "ref.csv")

    reference = parse_reference(tmp_path / "ref.csv")

    assert reference.ages[0] == 0
    assert reference.max_age == 18 * 12
    assert 21.0 in reference.ages and 24.0 in reference.ages and 30.0 in reference.ages


def test_missing_lms_is_fitted(tmp_path: Path) -> None:
    write_reference(tmp_path / "ref.csv", fitted_rows=3)

    reference = parse_reference(tmp_path / "ref.csv")

    assert reference.lms_l[0] == pytest.approx(LMS_L, abs=0.05)
    assert reference.lms_s[0] == pytest.approx(LMS_S, abs=0.002)


@pytest.mark.parametrize("z", [-1.88, 0.0, 1.28])
def test_z_score_roundtrip(tmp_path: Path, z: float) -> None:
    write_reference(tmp_path / "ref.csv")
    reference = parse_reference(tmp_path / "ref.csv")

    assert reference.z_score(value_at(60.0, z), 60.0) == pytest.approx(z, abs=1e-3)
    assert reference.median(60.0) == pytest.approx(median_at(60.0), rel=1e-4)


def test_unknown_unit(tmp_path: Path) -> None:
    path = tmp_path / "ref.csv"
    path.write_text("age;unit;P3;P10;P25;P50;P75;P90;P97;L;S\n1;Wochen;1;2;3;4;5;6;7;;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Wochen"):
        parse_reference(path)


def test_percentile() -> None:
    assert z_to_percentile(0.0) == pytest.approx(50.0)
    assert z_to_percentile(1.281552) == pytest.approx(90.0, abs=0.01)
