"""Imports every module's models so `Base.metadata` is complete (migrations, backups)."""

from family_hub.core import models as core_models
from family_hub.db import Base
from family_hub.fever import models as fever_models
from family_hub.growth import models as growth_models
from family_hub.rhythm import models as rhythm_models
from family_hub.time_capsule import models as time_capsule_models

SCHEMAS = {
    core_models.SCHEMA,
    fever_models.SCHEMA,
    growth_models.SCHEMA,
    rhythm_models.SCHEMA,
    time_capsule_models.SCHEMA,
}

metadata = Base.metadata
