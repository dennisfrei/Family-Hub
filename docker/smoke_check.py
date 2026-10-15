"""Build-time check that the trimmed image still has everything the app loads."""

import io

import botocore.session
from matplotlib.figure import Figure

import family_hub.admin.cli
import family_hub.app
import family_hub.backup.cli
import family_hub.fever.importer
import family_hub.growth.importer
import family_hub.growth.report
import family_hub.main
from family_hub.time_capsule.export import booklet_pdf

botocore.session.get_session().create_client(
    "s3", region_name="eu-central-1", aws_access_key_id="x", aws_secret_access_key="x"
)
assert booklet_pdf([], "Smoke 🙂", 2026).startswith(b"%PDF")
figure = Figure()
figure.add_subplot().plot([0, 1], [0, 1])
figure.savefig(io.BytesIO(), format="svg")
print("smoke test passed")
