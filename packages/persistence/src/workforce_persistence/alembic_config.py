from __future__ import annotations


def escape_config_interpolation(value: str) -> str:
    """Escape percent signs before storing a URL in Alembic's ConfigParser."""
    return value.replace("%", "%%")
