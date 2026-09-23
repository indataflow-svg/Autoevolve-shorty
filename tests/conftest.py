"""Shared pytest configuration.

Rate limiting keeps per-process state (that is deliberate: single node, no
Redis). It is covered explicitly in tests/test_ratelimit.py and disabled by
default here so limiter state cannot leak across the rest of the suite.
Individual tests opt back in with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true", ...}).
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
