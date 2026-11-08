import os
import secrets

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.ratelimit import check_auth_failure
from core.auth_context import current_org_id, current_user_id


load_dotenv()

security = HTTPBasic(auto_error=False)


def require_operator() -> None:
    """Deployment-level engineering/monitor routes are not tenant features."""
    if current_org_id.get():
        raise HTTPException(403, "this capability is operator-only")


def authenticate(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str:
    # A verified website session is already authenticated and org-bound by
    # middleware. Basic auth remains the operator/legacy path.
    if current_user_id.get():
        return "session"

    user = os.getenv("DASHBOARD_USER", "founder")
    password = os.getenv("DASHBOARD_PASSWORD")
    if not password:
        raise RuntimeError("DASHBOARD_PASSWORD is missing from .env")

    if credentials is None:
        challenge = request.headers.get("x-requested-with", "").lower() != "xmlhttprequest"
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"} if challenge else None,
        )

    valid = secrets.compare_digest(credentials.username, user)
    valid = valid and secrets.compare_digest(credentials.password, password)
    if not valid:
        check_auth_failure(request)  # may raise 429 before the 401
        # Fetch requests should render their own sign-in error. Keep the Basic
        # challenge for direct navigation to the legacy dashboard.
        challenge = request.headers.get("x-requested-with", "").lower() != "xmlhttprequest"
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"} if challenge else None,
        )
    return credentials.username
