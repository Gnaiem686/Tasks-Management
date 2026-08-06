from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FactorConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    weight: float = Field(gt=0, le=1)
    direction: Literal["increases_risk", "inverse_risk", "protective"]
    normalization_cap: float = Field(gt=0)


class OverloadConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    max_evidence_age_hours: float = Field(gt=0)
    factors: dict[str, FactorConfiguration]

    @model_validator(mode="after")
    def validate_weights(self) -> OverloadConfiguration:
        if abs(sum(factor.weight for factor in self.factors.values()) - 1.0) > 1e-9:
            raise ValueError("employee-overload weights must sum to 1.0")
        return self


class ScoringConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_overload: OverloadConfiguration
    thresholds: dict[str, int]


def load_scoring_config(path: Path) -> ScoringConfiguration:
    raw = yaml.safe_load(path.read_text())
    return ScoringConfiguration.model_validate(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", type=Path, required=True)
    args = parser.parse_args()
    config = load_scoring_config(args.validate)
    print(f"valid scoring configuration: {config.employee_overload.version}")


if __name__ == "__main__":
    main()
