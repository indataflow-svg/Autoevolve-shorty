"""Publisher port: one small surface for social schedulers.

Buffer is the reference implementation. A publisher is responsible for
accounts, optional draft creation, scheduling, provider status, and insights.
The app stores provider-neutral `publisher_*` metadata; Buffer keeps its legacy
`buffer_*` fields in parallel so existing records and UI keep working.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class PublisherCapabilities:
    draft: bool
    schedule: bool
    confirm: bool
    insights: bool
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class PublisherAccount:
    name: str
    label: str
    platforms: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)


class PublisherError(Exception):
    """A publisher failure that maps directly onto an HTTP response."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class Publisher(Protocol):
    name: str
    label: str

    def capabilities(self) -> PublisherCapabilities: ...
    def accounts(self) -> list[PublisherAccount]: ...
    def draft(self, post: dict[str, Any], account: str | None = None) -> dict[str, Any]: ...
    def schedule(
        self,
        post: dict[str, Any],
        *,
        account: str | None = None,
        mode: str = "queue",
        due_at: str | None = None,
    ) -> dict[str, Any]: ...
    def confirm(self, post: dict[str, Any]) -> dict[str, Any]: ...
    def insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]: ...
