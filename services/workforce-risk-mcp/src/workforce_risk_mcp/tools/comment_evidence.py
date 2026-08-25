from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from workforce_risk.comments.classifier import CommentClassifier
from workforce_risk.comments.lifecycle import CommentLifecycleObservation
from workforce_risk.comments.models import CommentObservation


class CommentObservationStore(Protocol):
    async def append(
        self, observation: CommentLifecycleObservation, *, environment: str
    ) -> UUID: ...


class NormalizeCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1, max_length=128)
    observation: CommentObservation


class NormalizeCommentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    environment: Literal["dev", "prod", "test"]
    correlation_id: str
    status: Literal["stored", "no_signal"]
    observation_id: str | None = None
    category: str | None = None
    reason: str
    report_only: bool = True
    scoring_eligible: bool = False
    candidate_eligible: bool = False
    proposal_evidence_eligible: bool = False


async def normalize_comment_evidence(
    request: NormalizeCommentRequest,
    *,
    classifier: CommentClassifier,
    repository: CommentObservationStore,
    service_environment: str,
) -> NormalizeCommentResponse:
    if request.environment != service_environment:
        raise ValueError("request environment mismatch")
    classification = classifier.classify(request.observation)
    if classification.signal is None:
        return NormalizeCommentResponse(
            environment=request.environment,
            correlation_id=request.correlation_id,
            status="no_signal",
            reason=classification.reason,
        )
    lifecycle = CommentLifecycleObservation.from_signal(classification.signal)
    observation_id = await repository.append(lifecycle, environment=request.environment)
    return NormalizeCommentResponse(
        environment=request.environment,
        correlation_id=request.correlation_id,
        status="stored",
        observation_id=str(observation_id),
        category=lifecycle.category.value,
        reason=classification.reason,
    )
