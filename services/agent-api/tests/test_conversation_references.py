from agent_api.evidence.references import resolve_conversation_references
from agent_api.task_queries import GroundedAnswerContext, TaskFact


def test_generic_singular_reference_resolves_previous_issue() -> None:
    context = GroundedAnswerContext(
        intent="any",
        issues=(
            TaskFact(key="WFD-7", summary="Export", status="Done", assignee="Mohammad"),
        ),
    )
    resolved = resolve_conversation_references("Who completed that task?", context)
    assert [entity.identifier for entity in resolved.entities] == ["WFD-7"]
    assert resolved.needs_clarification is False


def test_generic_singular_reference_with_multiple_issues_is_ambiguous() -> None:
    context = GroundedAnswerContext(
        intent="any",
        issues=(
            TaskFact(key="WFD-7", summary="Export", status="Done"),
            TaskFact(key="WFD-8", summary="Login", status="Done"),
        ),
    )
    resolved = resolve_conversation_references("Who completed that task?", context)
    assert resolved.needs_clarification is True
    assert len(resolved.entities) == 2


def test_generic_plural_reference_preserves_all_issues() -> None:
    context = GroundedAnswerContext(
        intent="any",
        issues=(
            TaskFact(key="WFD-7", summary="Export", status="Done"),
            TaskFact(key="WFD-8", summary="Login", status="Done"),
        ),
    )
    resolved = resolve_conversation_references("Who owns those tasks?", context)
    assert [entity.identifier for entity in resolved.entities] == ["WFD-7", "WFD-8"]
    assert resolved.needs_clarification is False


def test_plural_employee_reference_preserves_all_employee_ids() -> None:
    context = GroundedAnswerContext(
        intent="employee_risk",
        employee_ids=("EMP-002", "EMP-003"),
        exhaustive=True,
    )

    resolved = resolve_conversation_references(
        "Which of those employees has more capacity?", context
    )

    assert [(item.kind, item.identifier) for item in resolved.entities] == [
        ("employee", "EMP-002"),
        ("employee", "EMP-003"),
    ]
    assert resolved.needs_clarification is False
