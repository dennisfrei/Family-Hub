"""Vitals: the navigation entry that groups fever and blood pressure."""

from family_hub.module import Module
from family_hub.vitals.pages import PATH, register_pages

MODULE = Module(
    name="vitals",
    label_key="vitals.title",
    icon="monitor_heart",
    path=PATH,
    register_pages=register_pages,
)
