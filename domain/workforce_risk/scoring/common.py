from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def normalize_capped(value: float, cap: float) -> float:
    if cap <= 0:
        raise ValueError("normalization cap must be positive")
    return clamp(value / cap, 0.0, 1.0)
