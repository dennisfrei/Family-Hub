"""Family Hub: one self-hosted app for growth, fever, weekly duties and memories."""

from importlib.metadata import PackageNotFoundError, version


def app_version() -> str:
    """Installed package version, or `dev` when running from a source tree without installation."""
    try:
        return version("family-hub")
    except PackageNotFoundError:
        return "dev"
