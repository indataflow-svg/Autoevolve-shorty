"""Request-scoped auth context.

The existing app resolves the active org from a global setting. Multi-user
requests need the session's org instead, without threading it through every
store. Middleware binds these context variables for the duration of a request;
legacy Basic-auth requests leave them empty and keep the old behavior.
"""
from __future__ import annotations

from contextvars import ContextVar

current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
current_org_id: ContextVar[int | None] = ContextVar("current_org_id", default=None)
current_session_hash: ContextVar[str | None] = ContextVar("current_session_hash", default=None)


def bind_session(*, user_id: str, org_id: int, session_hash: str) -> tuple:
    return (
        current_user_id.set(user_id),
        current_org_id.set(int(org_id)),
        current_session_hash.set(session_hash),
    )


def reset_session(tokens: tuple) -> None:
    for token in reversed(tokens):
        try:
            token.var.reset(token)
        except (ValueError, RuntimeError):
            pass
