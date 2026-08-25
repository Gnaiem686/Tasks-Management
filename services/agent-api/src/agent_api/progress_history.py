from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from workforce_contracts.jira import JiraIssueEvidence
from workforce_persistence.database import Database
from workforce_persistence.progress_repository import (
    TaskProgressObservation,
    TaskProgressRepository,
)


class ProgressRepository(Protocol):
    async def record_observations(
        self,
        *,
        environment: str,
        observations: tuple[TaskProgressObservation, ...],
        timezone_name: str,
    ) -> object: ...

    async def load_history_records(
        self, *, environment: str, project_key: str, limit: int
    ) -> tuple[dict[str, object], ...]: ...


class DatabaseProgressHistoryReader:
    def __init__(
        self,
        *,
        environment: str,
        database_url: str | None = None,
        repository_factory: Callable[[], ProgressRepository] | None = None,
        limit: int = 200,
    ) -> None:
        if database_url is None and repository_factory is None:
            raise ValueError("database_url or repository_factory is required")
        self._environment = environment
        self._database_url = database_url
        self._repository_factory = repository_factory
        self._limit = max(1, min(limit, 500))

    async def load(
        self, project_key: str, correlation_id: str
    ) -> tuple[dict[str, object], ...]:
        del correlation_id
        if self._repository_factory is not None:
            return await self._repository_factory().load_history_records(
                environment=self._environment,
                project_key=project_key,
                limit=self._limit,
            )
        assert self._database_url is not None
        database = Database(self._database_url)
        try:
            async with database.transaction() as session:
                return await TaskProgressRepository(session).load_history_records(
                    environment=self._environment,
                    project_key=project_key,
                    limit=self._limit,
                )
        finally:
            await database.close()


class DatabaseProgressHistoryRecorder:
    def __init__(
        self,
        *,
        environment: str,
        database_url: str | None = None,
        timezone_name: str = "Asia/Jerusalem",
        repository_factory: Callable[[], ProgressRepository] | None = None,
    ) -> None:
        if database_url is None and repository_factory is None:
            raise ValueError("database_url or repository_factory is required")
        self._environment = environment
        self._database_url = database_url
        self._timezone_name = timezone_name
        self._repository_factory = repository_factory

    async def record(
        self,
        project_key: str,
        rows: tuple[JiraIssueEvidence, ...],
        correlation_id: str,
    ) -> None:
        del correlation_id
        observations = tuple(self._observation(project_key, row) for row in rows)
        if self._repository_factory is not None:
            await self._repository_factory().record_observations(
                environment=self._environment,
                observations=observations,
                timezone_name=self._timezone_name,
            )
            return
        assert self._database_url is not None
        database = Database(self._database_url)
        try:
            async with database.transaction() as session:
                await TaskProgressRepository(session).record_observations(
                    environment=self._environment,
                    observations=observations,
                    timezone_name=self._timezone_name,
                )
        finally:
            await database.close()

    @staticmethod
    def _observation(
        project_key: str, row: JiraIssueEvidence
    ) -> TaskProgressObservation:
        blocker_keys = tuple(
            sorted(
                {
                    link.issue_key
                    for link in row.links
                    if link.relationship.casefold().strip() == "is blocked by"
                }
            )
        )
        blocker_category = next(
            (
                field.value
                for field in row.custom_fields
                if field.logical_name == "blocker_category" and field.value
            ),
            None,
        )
        return TaskProgressObservation(
            project_key=project_key,
            issue_key=row.key,
            assignee_id=None if row.assignee is None else row.assignee.account_id,
            captured_at=row.evidence_timestamp,
            jira_updated_at=row.activity_timestamp,
            status=row.status,
            original_estimate_hours=(
                None
                if row.original_estimate_seconds is None
                else row.original_estimate_seconds / 3600
            ),
            remaining_estimate_hours=(
                None
                if row.remaining_estimate_seconds is None
                else row.remaining_estimate_seconds / 3600
            ),
            time_spent_hours=(
                None
                if row.time_spent_seconds is None
                else row.time_spent_seconds / 3600
            ),
            due_date=row.due_date,
            priority=row.priority,
            blocked=bool(blocker_category) or bool(blocker_keys),
            blocker_issue_keys=blocker_keys,
        )
