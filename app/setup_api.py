"""Setup wizard API: provider status, key test + save, setup step.

Reads use dashboard auth only and never return secret values.
Writes additionally require the founder action token header.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.sales_api import verify_founder_action

router = APIRouter(prefix="/company/setup", tags=["setup"])


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


@router.post("/keys/test")
def test_setup_keys(payload: SetupKeysPayload, _: None = Depends(verify_founder_action)):
    from core.setup_keys import PROVIDER_GROUPS, validate_group

    if payload.group not in PROVIDER_GROUPS:
        raise HTTPException(422, f"unknown group: {payload.group}")
    result = validate_group(payload.group, payload.values)
    if not result.get("ok"):
        raise HTTPException(422, result.get("error") or result.get("errors"))
    return result


@router.post("/keys")
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
def set_setup_step_route(payload: SetupStepPayload):
    from core.state import set_setup_step

    set_setup_step(payload.step.strip())
    return {"ok": True, "step": payload.step.strip()}
