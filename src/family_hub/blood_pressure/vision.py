"""Reads blood pressure values from photos with a self-hosted vision model (OpenAI-compatible API).

A photo shows either the display of a monitor (one reading) or a written list of earlier readings.
"""

import asyncio
import base64
import io
import json
import logging
import re
from datetime import date, time

import httpx2
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from family_hub.blood_pressure import service
from family_hub.blood_pressure.schemas import ListEntry, Measurement
from family_hub.config import Settings, get_settings

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
MAX_ANSWER_TOKENS = 100
MAX_LIST_TOKENS = 1000
MAX_YEARS_BACK = 5

PROMPT = (
    "The photo shows the display of a blood pressure monitor. Read the numbers from the display. "
    'Answer with JSON only: {"systolic": <SYS in mmHg>, "diastolic": <DIA in mmHg>, "pulse": <pulse per minute>}. '
    "Use null for a value you cannot read."
)
ANSWER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "systolic": {"type": ["integer", "null"]},
        "diastolic": {"type": ["integer", "null"]},
        "pulse": {"type": ["integer", "null"]},
    },
    "required": ["systolic", "diastolic", "pulse"],
    "additionalProperties": False,
}


LIST_PROMPT = (
    "The image shows a list or table of blood pressure measurements, possibly handwritten. "
    "Transcribe it line by line from top to bottom. Each line that has a time is one measurement. Output one "
    "line per measurement in exactly this format:\ndate;time;SYS;DIA;pulse\n"
    "SYS is the higher blood pressure value, DIA the lower one. If a line shows no date, write - as its date. "
    "Write ? for a value you cannot read. Do not skip any line. Output only these lines."
)
LIST_FIELDS = 5
MIN_SPREAD = 20

_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:hH]([0-5]\d)(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2})(?!\d))?[./]?")
_NUMBER = re.compile(r"(?<!\d)\d{2,3}(?!\d)")


class VisionError(RuntimeError):
    """Raised when the photo cannot be processed or the model service fails."""


def is_enabled(settings: Settings | None = None) -> bool:
    """Whether a vision model is configured."""
    return bool((settings or get_settings()).vision_url.strip())


def has_accurate_model(settings: Settings | None = None) -> bool:
    """Whether display photos can also be read by the list model, because it is a different one."""
    settings = settings or get_settings()
    display, accurate = (
        name or settings.vision_model for name in (settings.vision_display_model, settings.vision_list_model)
    )
    return is_enabled(settings) and display != accurate


def prepare_image(data: bytes, max_edge: int) -> bytes:
    """Turn a phone photo into an upright JPEG with at most `max_edge` pixels per side.

    Raises:
        VisionError: If the data is not a readable image.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VisionError("Not a readable image") from exc
    upright.thumbnail((max_edge, max_edge))
    buffer = io.BytesIO()
    upright.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def parse_answer(content: str) -> Measurement | None:
    """Extract plausible values from the model's answer; None if there are none."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match is None:
        return None
    try:
        measurement = Measurement.model_validate(json.loads(match.group()))
        service.validate(measurement)
    except (ValueError, ValidationError):
        return None
    return measurement


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_day(text: str, today: date) -> tuple[date | None, str]:
    """Find a date in `text`; returns it with the rest of the text."""
    iso = _ISO_DATE.search(text)
    if iso is not None:
        year, month, day = (int(part) for part in iso.groups())
        return _date(year, month, day), text[: iso.start()] + " " + text[iso.end() :]
    match = _DATE.search(text)
    if match is None:
        return None, text
    rest = text[: match.start()] + " " + text[match.end() :]
    day, month = int(match.group(1)), int(match.group(2))
    written = match.group(3)
    if written is not None:
        year = int(written) if len(written) == 4 else 2000 + int(written)
        found = _date(year, month, day)
        if found is not None and today.year - MAX_YEARS_BACK <= found.year and found <= today:
            return found, rest
    # No usable year: the latest such day that is not in the future
    found = _date(today.year, month, day)
    if found is not None and found > today:
        found = _date(today.year - 1, month, day)
    return found, rest


def _parse_moment(text: str, today: date) -> tuple[date | None, time | None, str]:
    """Find date and time in `text`; returns them with the rest of the text."""
    at = None
    match = _TIME.search(text)
    if match is not None:
        at = time(int(match.group(1)), int(match.group(2)))
        text = _TIME.sub(" ", text)
    day, rest = _parse_day(text, today)
    return day, at, rest


def _value(field: str) -> int | None:
    match = _NUMBER.search(field)
    return None if match is None else int(match.group())


def parse_list(content: str, today: date) -> list[ListEntry]:
    """Extract the readings from the model's transcription of a list, one per line.

    A line in the asked format is read by position, so an unreadable value stays empty. Other lines are read
    by order and need two values; two values too close for SYS and DIA count as DIA and pulse. Dates without a
    year are placed in the past year up to `today`. A line without a date takes the date of the line above.
    """
    entries: list[ListEntry] = []
    for line in content.splitlines():
        fields = line.split(";")
        day, at, rest = _parse_moment(line, today)
        # The model often joins date and time into one field
        joined = len(fields) == LIST_FIELDS - 1 and None not in _parse_moment(fields[0], today)[:2]
        if len(fields) == LIST_FIELDS or joined:
            systolic, diastolic, pulse = (_value(field) for field in fields[-3:])
            if systolic is None and diastolic is None:
                continue
        else:
            numbers = [int(number) for number in _NUMBER.findall(rest)]
            if len(numbers) < 2:
                continue
            systolic, diastolic = numbers[:2]
            pulse = numbers[2] if len(numbers) > 2 else None
            if pulse is None and systolic - diastolic < MIN_SPREAD:
                systolic, diastolic, pulse = None, systolic, diastolic
        if day is None and entries:
            day = entries[-1].day
        entries.append(ListEntry(day=day, at=at, systolic=systolic, diastolic=diastolic, pulse=pulse))
    return entries


def _request_body(model: str, image: bytes, prompt: str, max_tokens: int) -> dict[str, object]:
    encoded = base64.b64encode(image).decode()
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                ],
            }
        ],
    }


async def _ask(
    data: bytes,
    prompt: str,
    settings: Settings,
    transport: httpx2.AsyncBaseTransport | None,
    *,
    model: str,
    max_edge: int,
    max_tokens: int,
    answer_schema: dict[str, object] | None = None,
) -> str:
    """Send the photo with a prompt; returns the model's answer text (`model` empty: the server's default)."""
    model = model or settings.vision_model
    image = await asyncio.to_thread(prepare_image, data, max_edge)
    body = _request_body(model, image, prompt, max_tokens)
    if answer_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "blood_pressure", "strict": True, "schema": answer_schema},
        }
    key = settings.vision_api_key.get_secret_value() if settings.vision_api_key else None
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = f"{settings.vision_url.rstrip('/')}/v1/chat/completions"
    logger.info(f"Asking vision model {model or 'default'} to read a photo")
    try:
        async with httpx2.AsyncClient(timeout=settings.vision_timeout_seconds, transport=transport) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except (httpx2.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise VisionError(f"Vision model request failed: {exc}") from exc
    logger.debug(f"Vision model answered: {content}")
    return content if isinstance(content, str) else ""


async def read_photo(
    data: bytes,
    settings: Settings | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
    *,
    accurate: bool = False,
) -> Measurement | None:
    """Ask the vision model for the values on a photo of a monitor display.

    Args:
        data: The uploaded image.
        settings: App settings; defaults to the process settings.
        transport: HTTP transport, replaced in tests.
        accurate: Use the list model, which is slower.

    Returns:
        The values, or None if the model found no plausible ones.

    Raises:
        VisionError: If the image is unreadable or the model service fails.
    """
    settings = settings or get_settings()
    content = await _ask(
        data,
        PROMPT,
        settings,
        transport,
        model=settings.vision_list_model if accurate else settings.vision_display_model,
        max_edge=settings.vision_display_max_edge,
        max_tokens=MAX_ANSWER_TOKENS,
        answer_schema=ANSWER_SCHEMA,
    )
    return parse_answer(content)


async def read_list(
    data: bytes,
    today: date,
    settings: Settings | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> list[ListEntry]:
    """Ask the vision model to transcribe a photo of a written list of readings.

    Args:
        data: The uploaded image.
        today: Local date, used for dates written without a year.
        settings: App settings; defaults to the process settings.
        transport: HTTP transport, replaced in tests.

    Returns:
        The lines the model found, unchecked; empty if there are none.

    Raises:
        VisionError: If the image is unreadable or the model service fails.
    """
    settings = settings or get_settings()
    content = await _ask(
        data,
        LIST_PROMPT,
        settings,
        transport,
        model=settings.vision_list_model,
        max_edge=settings.vision_list_max_edge,
        max_tokens=MAX_LIST_TOKENS,
    )
    return parse_list(content, today)
