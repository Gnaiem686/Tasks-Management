from __future__ import annotations

import os

from fastapi import HTTPException
from workforce_contracts.auth import AuthenticatedPrincipal


def enforce_project_scope(project_key: str, principal: AuthenticatedPrincipal) -> None:
    configured = os.getenv("JIRA_PROJECT_KEY", "WRD")
    if project_key != configured or project_key not in principal.project_scopes:
        raise HTTPException(status_code=403, detail="project scope is not authorized")
