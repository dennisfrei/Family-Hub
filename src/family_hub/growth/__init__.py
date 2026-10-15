"""Growth module: height, weight and head circumference against reference percentiles."""

from family_hub.growth import service
from family_hub.growth.api import GrowthController
from family_hub.growth.pages import register_pages
from family_hub.module import Module, PersonData

MODULE = Module(
    name="growth",
    label_key="growth.title",
    icon="straighten",
    path="/growth",
    register_pages=register_pages,
    api_handlers=[GrowthController],
    person_data=PersonData(count=service.count_person_data, delete=service.delete_person_data),
)
