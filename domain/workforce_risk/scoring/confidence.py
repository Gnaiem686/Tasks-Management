from workforce_risk.models import ConfidenceLevel


def confidence_for_coverage(coverage: float) -> ConfidenceLevel:
    if coverage >= 0.9:
        return ConfidenceLevel.HIGH
    if coverage >= 0.75:
        return ConfidenceLevel.MEDIUM
    if coverage >= 0.6:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT_DATA
