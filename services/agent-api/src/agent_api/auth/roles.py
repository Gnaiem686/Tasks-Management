from __future__ import annotations

from enum import StrEnum


class ApplicationRole(StrEnum):
    VIEWER = "viewer"
    MANAGER = "manager"
    ADMINISTRATOR = "administrator"
