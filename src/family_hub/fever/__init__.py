"""Fever module: temperature readings grouped into illness episodes."""

from family_hub.fever import service
from family_hub.fever.api import FeverController
from family_hub.fever.pages import register_pages
from family_hub.module import Module, PersonData

MODULE = Module(
    name="fever",
    label_key="fever.title",
    icon="thermostat",
    path="/fever",
    register_pages=register_pages,
    api_handlers=[FeverController],
    person_data=PersonData(count=service.count_person_data, delete=service.delete_person_data),
)
