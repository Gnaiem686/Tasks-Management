from __future__ import annotations


class ScenarioScopeError(PermissionError):
    """The requested scenario operation is outside the approved dev scope."""


def validate_scenario_scope(*, environment: str, project_key: str) -> None:
    if environment != "dev":
        raise ScenarioScopeError("scenario environment must be exactly dev")
    if project_key != "WRD":
        raise ScenarioScopeError("scenario project must be exactly WRD")
