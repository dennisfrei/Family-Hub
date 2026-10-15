"""Home module: today's overview across all modules."""

from family_hub.home.pages import register_pages
from family_hub.module import Module

MODULE = Module(name="home", label_key="home.title", icon="dashboard", path="/", register_pages=register_pages)
