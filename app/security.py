import os
import secrets

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.ratelimit import check_auth_failure


load_dotenv()

security = HTTPBasic()


def authenticate(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    user = os.getenv("DASHBOARD_USER", "founder")
    password = os.getenv("DASHBOARD_PASSWORD")
    if not password:
        raise RuntimeError("DASHBOARD_PASSWORD is missing from .env")

    valid = secrets.compare_digest(credentials.username, user)
    valid = valid and secrets.compare_digest(credentials.password, password)
    if not valid:
        check_auth_failure(request)  # may raise 429 before the 401
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
