from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from family_hub.core.importing import MappingError
from family_hub.core.models import Sex
from family_hub.growth.importer import build_measurements, profile_mismatches
from family_hub.growth.models import MeasurementType

BACKUP: dict[str, Any] = {
    "tables": {
        "profile": [
            {"id": "p1", "name": "Ada", "birthday": "2022-03-15", "gender": "female"},
            {"id": "p2", "name": "Demo", "birthday": "2020-01-01", "gender": "male"},
        ],
        "measurement": [
            {
                "id": "m1",
                "profile_id": "p1",
                "type": "weight",
                "value": 3400,
                "unit": "g",
                "date": "2022-03-15",
                "official": True,
            },
            {
                "id": "m2",
                "profile_id": "p1",
                "type": "length",
                "value": 0.52,
                "unit": "m",
                "date": "2022-03-15",
                "official": False,
            },
            {
                "id": "m3",
                "profile_id": "p2",
                "type": "length",
                "value": 80,
                "unit": "cm",
                "date": "2021-01-01",
                "official": True,
            },
        ],
        "default_profile": [],
    }
}
MAPPING = {"growth": {"profiles": {"p1": 1, "p2": None}}}


def test_unmapped_profile_aborts() -> None:
    with pytest.raises(MappingError, match="p2"):
        build_measurements(BACKUP, {"growth": {"profiles": {"p1": 1}}})


def test_units_are_normalised_and_skipped_profiles_left_out() -> None:
    items = build_measurements(BACKUP, MAPPING)

    assert [(i.import_ref, i.measurement.type, i.measurement.value, i.measurement.official) for i in items] == [
        ("kiggs-plot:m1", MeasurementType.WEIGHT, 3.4, True),
        ("kiggs-plot:m2", MeasurementType.LENGTH, 52.0, False),
    ]


def test_profile_mismatch() -> None:
    people = {1: SimpleNamespace(name="Ada", birth_date=date(2022, 3, 16), sex=Sex.MALE)}

    problems = profile_mismatches(BACKUP, MAPPING, people)

    assert len(problems) == 2


def test_profile_match() -> None:
    people = {1: SimpleNamespace(name="Ada", birth_date=date(2022, 3, 15), sex=Sex.FEMALE)}

    assert profile_mismatches(BACKUP, MAPPING, people) == []
