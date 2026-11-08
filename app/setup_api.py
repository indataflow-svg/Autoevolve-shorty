"""Setup wizard API: provider status, key test + save, setup step.

Reads use dashboard auth only and never return secret values.
Writes additionally require the founder action token header.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.sales_api import verify_founder_action

def _require_operator() -> None:
    """Provider keys, setup steps, and Buffer accounts are deployment-level.

    A free website session must not overwrite the operator's global credentials;
    Basic-auth operator requests have no scoped org and pass through.
    """
    from core.auth_context import current_org_id
    from core.state import get_org

    scoped = current_org_id.get()
    if scoped and (get_org(int(scoped)) or {}).get("plan") == "free":
        raise HTTPException(403, "provider setup is not available on the free plan")


router = APIRouter(prefix="/company/setup", tags=["setup"], dependencies=[Depends(_require_operator)])


def _block_free_buffer() -> None:
    from core.auth_context import current_org_id
    from core.state import get_org

    scoped = current_org_id.get()
    if scoped and (get_org(int(scoped)) or {}).get("plan") == "free":
        raise HTTPException(403, "free workspaces use their own publisher webhook")


@router.get("/providers")
def setup_providers():
    from core.setup_keys import PROVIDER_GROUPS, group_status

    return {
        "groups": [
            {"id": group, "label": spec["label"], **group_status()[group]}
            for group, spec in PROVIDER_GROUPS.items()
        ]
    }


class SetupKeysPayload(BaseModel):
    group: str = Field(min_length=1, max_length=40)
    values: dict[str, str] = Field(default_factory=dict)


class SetupKeyTestResult(BaseModel):
    ok: bool
    checked: list[str]


class SetupKeySaveResult(BaseModel):
    ok: bool
    group: str
    saved: list[str]
    backup: str | None
    restart_required: bool


@router.post("/keys/test", response_model=SetupKeyTestResult)
def test_setup_keys(payload: SetupKeysPayload, _: None = Depends(verify_founder_action)):
    from core.setup_keys import PROVIDER_GROUPS, validate_group

    if payload.group not in PROVIDER_GROUPS:
        raise HTTPException(422, f"unknown group: {payload.group}")
    result = validate_group(payload.group, payload.values)
    if not result.get("ok"):
        raise HTTPException(422, result.get("error") or result.get("errors"))
    return result


@router.post("/keys", response_model=SetupKeySaveResult)
def save_setup_keys(payload: SetupKeysPayload, _: None = Depends(verify_founder_action)):
    from core.setup_keys import PROVIDER_GROUPS, save_group

    if payload.group not in PROVIDER_GROUPS:
        raise HTTPException(422, f"unknown group: {payload.group}")
    result = save_group(payload.group, payload.values)
    if not result.get("ok"):
        raise HTTPException(422, result.get("error") or result.get("errors"))
    return result


@router.get("/step")
def get_setup_step_route():
    from core.state import get_active_org, get_setup_step

    active = get_active_org()
    return {
        "step": get_setup_step(),
        "active_org": {"id": active["id"], "slug": active["slug"]} if active else None,
    }


class SetupStepPayload(BaseModel):
    step: str = Field(min_length=1, max_length=40)


@router.post("/step")
def set_setup_step_route(payload: SetupStepPayload, _: None = Depends(verify_founder_action)):
    from core.state import set_setup_step

    set_setup_step(payload.step.strip())
    return {"ok": True, "step": payload.step.strip()}


# --- Guided Buffer setup ---------------------------------------------------
#
# The Buffer token is the only secret. Channels are identifiers discovered
# from that token, so the UI asks for the token once, lists what it can reach,
# and then binds the Instagram/X/LinkedIn channel IDs. No token is ever returned.


class BufferAccountView(BaseModel):
    name: str
    api_key_present: bool
    organization_id: str | None
    instagram_channel_id: str | None
    x_channel_id: str | None
    linkedin_channel_id: str | None


class BufferSetupAccountsView(BaseModel):
    accounts: list[BufferAccountView]


class BufferChannelView(BaseModel):
    id: str
    name: str
    display_name: str
    descriptor: str
    service: str
    type: str
    platform: str | None
    supported: bool
    usable: bool


class BufferOrganizationView(BaseModel):
    id: str
    name: str
    channels: list[BufferChannelView]


class BufferDiscoveryView(BaseModel):
    account: str
    account_id: str
    organizations: list[BufferOrganizationView]


class BufferDiscoverPayload(BaseModel):
    account: str = Field(default="default", min_length=1, max_length=40)
    api_key: str | None = Field(default=None, max_length=500)


class BufferConnectPayload(BaseModel):
    account: str = Field(default="default", min_length=1, max_length=40)
    api_key: str | None = Field(default=None, max_length=500)
    organization_id: str = Field(min_length=1, max_length=200)
    instagram_channel_id: str | None = Field(default=None, max_length=200)
    x_channel_id: str | None = Field(default=None, max_length=200)
    linkedin_channel_id: str | None = Field(default=None, max_length=200)


class BufferConnectResult(BaseModel):
    ok: bool
    account: str
    organization_id: str
    instagram_channel_id: str | None
    x_channel_id: str | None
    linkedin_channel_id: str | None
    warnings: list[str]
    saved: list[str]
    backup: str | None
    restart_required: bool


def _buffer_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(502, f"Buffer request failed: {exc}")


@router.get("/buffer/accounts", response_model=BufferSetupAccountsView)
def buffer_setup_accounts():
    from services.buffer_setup import list_accounts

    _block_free_buffer()
    return {"accounts": list_accounts()}


@router.post("/buffer/discover", response_model=BufferDiscoveryView)
def discover_buffer_channels(
    payload: BufferDiscoverPayload, _: None = Depends(verify_founder_action)
):
    from services.buffer_setup import discover

    _block_free_buffer()
    try:
        return discover(payload.account, payload.api_key)
    except Exception as exc:
        raise _buffer_failure(exc) from exc


@router.post("/buffer/connect", response_model=BufferConnectResult)
def connect_buffer_account(
    payload: BufferConnectPayload, _: None = Depends(verify_founder_action)
):
    from services.buffer_setup import bind

    _block_free_buffer()
    try:
        return bind(
            payload.account,
            api_key=payload.api_key,
            organization_id=payload.organization_id,
            instagram_channel_id=payload.instagram_channel_id,
            x_channel_id=payload.x_channel_id,
            linkedin_channel_id=payload.linkedin_channel_id,
        )
    except Exception as exc:
        raise _buffer_failure(exc) from exc
