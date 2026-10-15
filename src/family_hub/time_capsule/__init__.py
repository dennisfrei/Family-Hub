"""Time capsule module (Zeitkapsel): sayings, moments and milestones per child."""

from family_hub.module import Module, PersonData
from family_hub.time_capsule import service
from family_hub.time_capsule.api import TimeCapsuleController
from family_hub.time_capsule.pages import register_pages

MODULE = Module(
    name="time_capsule",
    label_key="tc.title",
    icon="auto_stories",
    path="/time-capsule",
    register_pages=register_pages,
    api_handlers=[TimeCapsuleController],
    person_data=PersonData(count=service.count_person_data, delete=service.delete_person_data),
)
