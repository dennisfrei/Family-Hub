import io
import json
from datetime import date, time

import httpx2
import pytest
from PIL import Image
from pydantic import SecretStr

from family_hub.blood_pressure import vision
from family_hub.blood_pressure.schemas import ListEntry, Measurement
from family_hub.config import Settings

SETTINGS = Settings(
    vision_url="http://vision:8080/", vision_model="internvl", vision_api_key=SecretStr("k"), _env_file=None
)


def _photo(size: tuple[int, int] = (3000, 2000)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _answering(content: str, seen: list[httpx2.Request]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx2.MockTransport(handler)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"systolic": 124, "diastolic": 81, "pulse": 64}', Measurement(systolic=124, diastolic=81, pulse=64)),
        ('```json\n{"systolic": 124, "diastolic": 81, "pulse": null}\n```', Measurement(systolic=124, diastolic=81)),
        ('{"systolic": null, "diastolic": 81, "pulse": 64}', None),
        ('{"systolic": 81, "diastolic": 124, "pulse": 64}', None),
        ('{"systolic": 1240, "diastolic": 81, "pulse": 64}', None),
        ("I cannot read the display.", None),
        ("{broken", None),
    ],
)
def test_parse_answer(content: str, expected: Measurement | None) -> None:
    assert vision.parse_answer(content) == expected


def test_prepare_image_shrinks_to_jpeg() -> None:
    with Image.open(io.BytesIO(vision.prepare_image(_photo(), 512))) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 512


def test_prepare_image_rejects_other_files() -> None:
    with pytest.raises(vision.VisionError):
        vision.prepare_image(b"not an image", 512)


def test_enabled_only_with_url() -> None:
    assert vision.is_enabled(SETTINGS)
    assert not vision.is_enabled(Settings(_env_file=None))


async def test_read_photo_sends_image_to_model() -> None:
    seen: list[httpx2.Request] = []

    result = await vision.read_photo(
        _photo(), SETTINGS, _answering('{"systolic": 124, "diastolic": 81, "pulse": 64}', seen)
    )

    assert result == Measurement(systolic=124, diastolic=81, pulse=64)
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == "http://vision:8080/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer k"
    assert body["model"] == "internvl"
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_read_photo_service_down() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(vision.VisionError):
        await vision.read_photo(_photo(), SETTINGS, httpx2.MockTransport(handler))


async def test_read_photo_server_error() -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(503))

    with pytest.raises(vision.VisionError):
        await vision.read_photo(_photo(), SETTINGS, transport)


TODAY = date(2026, 11, 14)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "03.11.;07:15;128;82;67",
            ListEntry(day=date(2026, 11, 3), at=time(7, 15), systolic=128, diastolic=82, pulse=67),
        ),
        (
            "3.11.2025 7:15 128/82 67",
            ListEntry(day=date(2025, 11, 3), at=time(7, 15), systolic=128, diastolic=82, pulse=67),
        ),
        (
            "28.10.07:20;121/82;75",
            ListEntry(day=date(2026, 10, 28), at=time(7, 20), systolic=121, diastolic=82, pulse=75),
        ),
        ("2026-11-03 19:40 135 88", ListEntry(day=date(2026, 11, 3), at=time(19, 40), systolic=135, diastolic=88)),
        ("24.12.;08:00;130;85;?", ListEntry(day=date(2025, 12, 24), at=time(8, 0), systolic=130, diastolic=85)),
        (
            "03.11.99 07:15 128 82 67",
            ListEntry(day=date(2026, 11, 3), at=time(7, 15), systolic=128, diastolic=82, pulse=67),
        ),
        ("?;?;128;82;67", ListEntry(systolic=128, diastolic=82, pulse=67)),
        (
            "28.10. 07:20 07:20 121 82 75",
            ListEntry(day=date(2026, 10, 28), at=time(7, 20), systolic=121, diastolic=82, pulse=75),
        ),
        ("31.02.;07:15;128;82;67", ListEntry(at=time(7, 15), systolic=128, diastolic=82, pulse=67)),
        ("03.11.;07:15;?;82;67", ListEntry(day=date(2026, 11, 3), at=time(7, 15), diastolic=82, pulse=67)),
        ("03.11.;07:15;;82;67", ListEntry(day=date(2026, 11, 3), at=time(7, 15), diastolic=82, pulse=67)),
        ("03.11.07:15;?;82;67", ListEntry(day=date(2026, 11, 3), at=time(7, 15), diastolic=82, pulse=67)),
        ("03.11.;07:15;82;67", ListEntry(day=date(2026, 11, 3), at=time(7, 15), diastolic=82, pulse=67)),
        (
            "03.11.07:15;121;82;75",
            ListEntry(day=date(2026, 11, 3), at=time(7, 15), systolic=121, diastolic=82, pulse=75),
        ),
        ("03.11.;07:15;128;?;67", ListEntry(day=date(2026, 11, 3), at=time(7, 15), systolic=128, pulse=67)),
    ],
)
def test_parse_list_line(line: str, expected: ListEntry) -> None:
    assert vision.parse_list(line, TODAY) == [expected]


def test_parse_list_skips_other_lines() -> None:
    content = "Here is the list:\n\nDatum;Zeit;SYS;DIA;Puls\n03.11.;07:15;128;82;67\n04.11.;07:05;?;?;64\n"

    assert [entry.systolic for entry in vision.parse_list(content, TODAY)] == [128]


def test_parse_list_repeats_a_date_written_once() -> None:
    content = "03.11.;07:15;128;82;67\n?;19:30;131;84;70\n12:10 125 80 66\n04.11.;07:05;122;79;64\n"

    assert [(entry.day, entry.at) for entry in vision.parse_list(content, TODAY)] == [
        (date(2026, 11, 3), time(7, 15)),
        (date(2026, 11, 3), time(19, 30)),
        (date(2026, 11, 3), time(12, 10)),
        (date(2026, 11, 4), time(7, 5)),
    ]


async def test_read_list_asks_for_a_transcription() -> None:
    seen: list[httpx2.Request] = []

    entries = await vision.read_list(_photo(), TODAY, SETTINGS, _answering("03.11.;07:15;128;82;67", seen))

    assert entries == [ListEntry(day=date(2026, 11, 3), at=time(7, 15), systolic=128, diastolic=82, pulse=67)]
    body = json.loads(seen[0].content)
    assert "response_format" not in body
    assert body["max_tokens"] == vision.MAX_LIST_TOKENS


async def test_each_mode_can_use_its_own_model() -> None:
    settings = SETTINGS.model_copy(update={"vision_display_model": "small", "vision_list_model": "large"})
    seen: list[httpx2.Request] = []

    await vision.read_photo(_photo(), settings, _answering("{}", seen))
    await vision.read_list(_photo(), TODAY, settings, _answering("", seen))
    await vision.read_photo(_photo(), settings, _answering("{}", seen), accurate=True)

    assert [json.loads(request.content)["model"] for request in seen] == ["small", "large", "large"]
    assert vision.has_accurate_model(settings)
    assert not vision.has_accurate_model(SETTINGS)
