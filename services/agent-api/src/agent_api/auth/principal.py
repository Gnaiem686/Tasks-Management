from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_api.auth.roles import ApplicationRole


class AuthenticatedPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    display_label: str
    role: ApplicationRole
    environment: Literal["dev", "prod", "test"]
    project_scopes: tuple[str, ...]
