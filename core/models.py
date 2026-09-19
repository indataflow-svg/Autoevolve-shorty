import os

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

OMNIROUTE_BASE_URL = (
    os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").strip()
    or "http://127.0.0.1:20128/v1"
)

# NOTE: the dashboard must import without provider keys. An empty
# OMNIROUTE_API_KEY historically crashed startup (openai.OpenAIError:
# Missing credentials) because pydantic-ai builds its client eagerly at
# Agent-creation time. Fall back to a non-empty placeholder so import,
# /health, /docs, and non-AI pages work keyless; AI calls fail later
# with a clear error only when actually invoked.
OMNIROUTE_API_KEY = (os.getenv("OMNIROUTE_API_KEY", "") or "").strip() or "not-configured"


def is_model_configured() -> bool:
    """True when the user supplied a real model-router key."""
    raw = (os.getenv("OMNIROUTE_API_KEY", "") or "").strip()
    return bool(raw and raw != "not-configured")


def require_model_configured() -> None:
    """Raise a user-friendly error when an AI action needs a key."""
    if not is_model_configured():
        raise RuntimeError(
            "Model router is not configured. Set OMNIROUTE_API_KEY (and "
            "CODING_API_KEY for coding) in .env, then restart. "
            "See docs/keys.md and docs/model-routing.md."
        )

ROUTES = {
    "fast": os.getenv("MODEL_FAST", "auto/best-fast"),
    "reasoning": os.getenv("MODEL_REASONING", "auto/best-reasoning"),
    "free": os.getenv("MODEL_FREE", "auto/best-free"),
    "coding": os.getenv("MODEL_CODING", "auto/best-coding"),
    "vision": os.getenv("MODEL_VISION", "auto/best-vision"),
}


def cloud_model(route: str = "free") -> OpenAIChatModel:
    model_name = ROUTES[route]

    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(
            base_url=OMNIROUTE_BASE_URL,
            api_key=OMNIROUTE_API_KEY,
        ),
    )
