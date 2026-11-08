from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).parent.parent
WORKSPACE_ROOT = Path(os.getenv("COMPANY_CORE_WORKSPACE_ROOT", ROOT)).expanduser().resolve()


def _path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class MarketingConfig:
    """The only engine the app still calls: G3 (Buffer/R2 publishing)."""

    g3_root: Path
    g3_bin: Path
    g3_env_file: Path | None
    stage_timeout: int

    @classmethod
    def load(cls) -> "MarketingConfig":
        g3_root = _path("MARKETING_G3_ROOT", str(WORKSPACE_ROOT / "engines/g3"))
        return cls(
            g3_root=g3_root,
            g3_bin=_path("MARKETING_G3_BIN", str(g3_root / ".venv/bin/company-core-g3")),
            g3_env_file=_optional_path("MARKETING_G3_ENV_FILE", g3_root / "config/g3.env"),
            stage_timeout=int(os.getenv("MARKETING_STAGE_TIMEOUT", "900")),
        )

    def diagnostics(self) -> dict:
        path = self.g3_bin
        return {
            "g3_bin": {
                "ok": path.is_file() and os.access(path, os.X_OK),
                "path": str(path),
                "executable": os.access(path, os.X_OK) if path.exists() else None,
            }
        }


def _optional_path(name: str, default: Path) -> Path | None:
    raw = os.getenv(name)
    if raw is not None and not raw.strip():
        return None
    return Path(raw).expanduser().resolve() if raw else default.resolve()
