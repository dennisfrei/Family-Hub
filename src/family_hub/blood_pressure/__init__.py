"""Blood pressure module: readings per person, optionally read from a photo of the monitor."""

from family_hub.blood_pressure import service
from family_hub.blood_pressure.api import BloodPressureController
from family_hub.blood_pressure.pages import PATH, register_pages
from family_hub.module import Module, PersonData

MODULE = Module(
    name="blood_pressure",
    label_key="bp.title",
    icon="monitor_heart",
    path=PATH,
    register_pages=register_pages,
    api_handlers=[BloodPressureController],
    in_navigation=False,
    person_data=PersonData(count=service.count_person_data, delete=service.delete_person_data),
)
