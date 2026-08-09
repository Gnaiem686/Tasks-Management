from datetime import datetime, timedelta


def evidence_is_stale(
    *, evidence_timestamp: datetime, checked_at: datetime, max_age: timedelta
) -> bool:
    if max_age <= timedelta(0):
        raise ValueError("maximum evidence age must be positive")
    if checked_at < evidence_timestamp:
        raise ValueError("evidence timestamp cannot be in the future")
    return checked_at - evidence_timestamp > max_age
