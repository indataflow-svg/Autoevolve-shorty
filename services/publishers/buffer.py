"""Buffer adapter.

This is deliberately a thin wrapper over the existing app.marketing_api
functions. G3, its handoff, R2 upload, Buffer credentials, and the current UI
behavior are unchanged.
"""
from __future__ import annotations

from typing import Any

from .base import PublisherAccount, PublisherCapabilities, PublisherError


class BufferPublisher:
    name = "buffer"
    label = "Buffer"

    def capabilities(self) -> PublisherCapabilities:
        return PublisherCapabilities(
            draft=True,
            schedule=True,
            confirm=True,
            insights=True,
            platforms=("instagram", "x", "linkedin"),
        )

    def accounts(self) -> list[PublisherAccount]:
        from app.marketing_api import buffer_accounts

        payload = buffer_accounts()
        accounts = []
        for item in payload.get("accounts") or []:
            platforms = tuple(
                platform
                for platform, present in (
                    ("instagram", item.get("instagram_channel_id")),
                    ("x", item.get("x_channel_id")),
                    ("linkedin", item.get("linkedin_channel_id")),
                )
                if present
            )
            accounts.append(
                PublisherAccount(
                    name=str(item.get("name") or "default"),
                    label=f"Buffer · {item.get('name') or 'default'}",
                    platforms=platforms,
                    details={**item, "publisher": self.name, "error": payload.get("error")},
                )
            )
        return accounts

    def draft(self, post: dict[str, Any], account: str | None = None) -> dict[str, Any]:
        from app.marketing_api import create_manual_post_buffer_draft

        return create_manual_post_buffer_draft(post["id"], account)

    def schedule(
        self,
        post: dict[str, Any],
        *,
        account: str | None = None,
        mode: str = "queue",
        due_at: str | None = None,
    ) -> dict[str, Any]:
        from app.marketing_api import BufferScheduleRequest, schedule_manual_post_buffer

        return schedule_manual_post_buffer(
            post["id"],
            BufferScheduleRequest(mode=mode, due_at=due_at),
            account,
        )

    def confirm(self, post: dict[str, Any]) -> dict[str, Any]:
        from app.marketing_api import confirm_manual_post_send

        return confirm_manual_post_send(post["id"])

    def insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]:
        from app.marketing_api import manual_post_buffer_insights

        return manual_post_buffer_insights(post["id"], post_id)
