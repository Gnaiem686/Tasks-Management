from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def reset_process_local_rate_limiter() -> Generator[None, None, None]:
    """Keep tests independent while each test can still exercise rate limiting."""
    try:
        from agent_api.security.limits import limiter
    except ImportError:
        yield
        return
    limiter.reset()
    yield
    limiter.reset()
