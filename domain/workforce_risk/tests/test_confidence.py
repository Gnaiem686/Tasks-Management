import pytest
from workforce_risk.models import ConfidenceLevel
from workforce_risk.scoring.confidence import confidence_for_coverage


@pytest.mark.unit
@pytest.mark.parametrize(
    ("coverage", "expected"),
    [
        (1.0, ConfidenceLevel.HIGH),
        (0.9, ConfidenceLevel.HIGH),
        (0.899, ConfidenceLevel.MEDIUM),
        (0.75, ConfidenceLevel.MEDIUM),
        (0.749, ConfidenceLevel.LOW),
        (0.6, ConfidenceLevel.LOW),
        (0.599, ConfidenceLevel.INSUFFICIENT_DATA),
    ],
)
def test_confidence_boundaries(coverage: float, expected: ConfidenceLevel) -> None:
    assert confidence_for_coverage(coverage) is expected
