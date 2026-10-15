"""Admin module: deleting people for good, API tokens, backups and system facts."""

from family_hub.admin.pages import register_pages
from family_hub.module import Module

MODULE = Module(
    name="admin",
    label_key="admin.title",
    icon="settings",
    path="/admin",
    register_pages=register_pages,
    admin_only=True,
    navigation_bottom=True,
)
