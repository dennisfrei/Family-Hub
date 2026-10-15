from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from family_hub.config import Settings
from family_hub.fever.chart import Interpolation, fever_chart
from family_hub.fever.schemas import ReadingRead
from family_hub.fever.thresholds import AgeGroup, Level, thresholds_for

THRESHOLDS = thresholds_for(AgeGroup.CHILD, Settings(_env_file=None))


def _readings(count: int) -> list[ReadingRead]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        ReadingRead(
            id=i, episode_id=1, temperature=37 + i * 0.5, measured_at=start + timedelta(hours=i), level=Level.NORMAL
        )
        for i in range(count)
    ]


@pytest.mark.parametrize("interpolation", list(Interpolation))
@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_chart_builds(interpolation: Interpolation, count: int) -> None:
    figure = fever_chart(_readings(count), THRESHOLDS, tz=ZoneInfo("Europe/Berlin"), interpolation=interpolation)

    assert figure.data[-1].mode == "markers"
    assert len(figure.data[-1].x) == count
