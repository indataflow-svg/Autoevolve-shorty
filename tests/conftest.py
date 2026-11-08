"""Shared pytest configuration.

Rate limiting keeps per-process state (that is deliberate: single node, no
Redis). It is covered explicitly in tests/test_ratelimit.py and disabled by
default here so limiter state cannot leak across the rest of the suite.
Individual tests opt back in with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true", ...}).
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _initialize_default_schema():
    """Keep tests that use the default store paths independent of a pre-existing local DB."""
    from core.bootstrap import init_all_schema

    init_all_schema()
