"""Rhythm module (Takt): weekly plan of family duties."""

from family_hub.module import Module, PersonData
from family_hub.rhythm import service
from family_hub.rhythm.api import RhythmController
from family_hub.rhythm.pages import register_pages

MODULE = Module(
    name="rhythm",
    label_key="rhythm.title",
    icon="event_repeat",
    path="/rhythm",
    register_pages=register_pages,
    api_handlers=[RhythmController],
    person_data=PersonData(count=service.count_person_data, delete=service.delete_person_data),
)
