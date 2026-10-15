"""Core module: people, children and (later) accounts and access."""

from family_hub.core.api import CoreController
from family_hub.core.pages import register_pages
from family_hub.module import Module

MODULE = Module(
    name="core",
    label_key="core.title",
    icon="group",
    path="/people",
    register_pages=register_pages,
    api_handlers=[CoreController],
)
