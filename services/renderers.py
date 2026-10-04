"""Renderer abstraction for the video pipeline (control-plane side).

Conceptually::

    Renderer
    ├── HunyuanRenderer  (submits to the private MI300X worker over HTTP)
    ├── FFmpegRenderer   (not built yet - local assembly lives in G2/marketing)
    └── future renderers

``HunyuanRenderer`` does NOT implement Hunyuan itself. It submits a RenderJob
payload to the private GPU worker (``POST {RENDER_WORKER_URL}/render``) and
returns the produced MP4 bytes. The worker owns its validated Hunyuan
environment (``HUNYUAN_PYTHON=/root/video-lab/.venv/bin/python``); nothing
here may modify, reinstall, or second-guess it.

Phase-1 flow is synchronous-by-default with async fallback (control-plane
push)::

    claim job -> health/capacity -> POST /render -> save MP4 -> ffprobe QA
    -> complete_job | fail_job

When the worker answers a submit with a pending status instead of bytes,
the client polls ``GET /render/{job_id}`` and then streams
``GET /render/{job_id}/download`` to disk. All terminal writes go through
the existing ``video_render_jobs`` lifecycle, so the phase-2 worker-pull
queue needs no status-model changes: only the caller of ``submit`` moves.
Worker authentication is a Bearer token (``RENDER_WORKER_API_TOKEN``) sent
on every protected request; ``/health`` stays unauthenticated for
monitoring. The token never appears in errors or logs. Retry policy reuses the two existing layers and
invents none:

- transport: a bounded pre-submit retry loop (connection errors only, nothing
  reached the worker yet) - the same shape as the provider clients in
  ``services/hunter.py`` et al.
- job level: ``fail_job(retryable=...)`` + ``attempts/max_attempts``. A POST
  that may have reached the worker is NEVER re-sent automatically; the job
  returns to ``pending`` and an operator resubmits explicitly.

Configuration (``.env`` / ``.env.example``; no defaults containing addresses)::

    RENDER_WORKER_URL=http://100.126.189.74:8000   # Tailscale-only private address
    RENDER_WORKER_TIMEOUT_SECONDS=1800             # sync render budget
    RENDER_OUTPUT_DIR=data/renders                 # MP4 landing zone (gitignored)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]

DEFAULT_RENDER_TIMEOUT_SECONDS = 1800
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
HEALTH_TIMEOUT_SECONDS = 10
PRE_SUBMIT_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL_SECONDS = 15

ASYNC_STATUSES = {"queued", "running", "accepted", "pending", "leased"}
TERMINAL_WORKER_STATUSES = {"completed", "failed"}


class RenderWorkerError(Exception):
    """A failed render submit. ``retryable`` decides the job's fate."""

    def __init__(self, kind: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class RenderQAError(Exception):
    """A worker output that failed local validation."""


def render_worker_url() -> str:
    url = (os.getenv("RENDER_WORKER_URL", "") or "").strip().rstrip("/")
    if not url:
        raise RenderWorkerError(
            "not_configured",
            "RENDER_WORKER_URL is not set (Tailscale worker address, e.g. "
            "http://100.126.189.74:8000). See docs/video-pipeline.md.",
            retryable=False,
        )
    return url


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def render_timeout_seconds() -> int:
    return _env_int("RENDER_WORKER_TIMEOUT_SECONDS", DEFAULT_RENDER_TIMEOUT_SECONDS)


def poll_interval_seconds() -> int:
    return _env_int("RENDER_WORKER_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)


def worker_api_token() -> str:
    """Bearer token for protected worker endpoints (empty = not configured).

    The token lives only in ``.env`` (never in source). It is sent as an
    ``Authorization`` header and is never included in errors or logs.
    """
    return (os.getenv("RENDER_WORKER_API_TOKEN", "") or "").strip()


def render_output_dir() -> Path:
    configured = (os.getenv("RENDER_OUTPUT_DIR", "") or "").strip()
    directory = Path(configured) if configured else (REPO / "data" / "renders")
    if not directory.is_absolute():
        directory = REPO / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def aspect_ratio_for(width: int | None, height: int | None) -> str:
    """Canonical 'W:H' ratio for the worker payload (it defaults to 16:9)."""
    if not width or not height:
        return "9:16"  # AutoEvolve's default portrait format
    divisor = math.gcd(int(width), int(height)) or 1
    return f"{int(width) // divisor}:{int(height) // divisor}"


class Renderer(ABC):
    """Minimal renderer interface. Submitters only; no local GPU work."""

    name: str

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Lightweight liveness probe. Raises RenderWorkerError when down."""

    @abstractmethod
    def check_capacity(self) -> dict[str, Any]:
        """Worker availability snapshot. Raises RenderWorkerError when down."""

    @abstractmethod
    def submit_render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit one render payload.

        Returns ``{"output_bytes": ..., "output_name": ...}`` when the
        worker answers synchronously, or ``{"worker_job_id": ...,
        "status": ...}`` when it queues the job for status polling.
        """

    @abstractmethod
    def get_render_status(self, worker_job_id: str) -> dict[str, Any]:
        """Poll ``GET /render/{job_id}``. Raises RenderWorkerError."""

    @abstractmethod
    def download_render(
        self,
        worker_job_id: str,
        dest_path: str | Path,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Stream ``GET /render/{job_id}/download`` to disk (no full RAM load)."""


def _safe_job_id(worker_job_id: str) -> str:
    """Reject anything that is not a plain job identifier (path traversal)."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", worker_job_id or ""):
        raise RenderWorkerError(
            "validation", f"unsafe worker job id: {worker_job_id!r}", retryable=False
        )
    return worker_job_id


def _worker_job_id(body: dict[str, Any]) -> str | None:
    """First usable worker job identifier in a response body, if any."""
    for key in ("job_id", "worker_job_id", "id"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _auth_headers() -> dict[str, str]:
    token = worker_api_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


class HunyuanRenderer(Renderer):
    """Submits RenderJob payloads to the private MI300X worker's POST /render."""

    name = "hunyuan"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = (base_url or render_worker_url()).rstrip("/")
        self.timeout_seconds = timeout_seconds or render_timeout_seconds()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                self.timeout_seconds,
                connect=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            ),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HunyuanRenderer":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- probes (safe to retry: idempotent GETs) ---------------------------

    def _get(self, path: str, *, authenticated: bool = False) -> dict[str, Any]:
        headers = _auth_headers() if authenticated else None
        last_error: Exception | None = None
        for attempt in range(PRE_SUBMIT_ATTEMPTS):
            try:
                response = self._client.get(
                    path, headers=headers, timeout=httpx.Timeout(HEALTH_TIMEOUT_SECONDS)
                )
                if response.status_code == 401:
                    raise RenderWorkerError(
                        "unauthorized",
                        f"worker {path} requires RENDER_WORKER_API_TOKEN",
                        retryable=False,
                    )
                if response.status_code == 404:
                    raise RenderWorkerError(
                        "not_found", f"worker has no {path}", retryable=False
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = exc
                time.sleep(1)
            except httpx.HTTPStatusError as exc:
                raise RenderWorkerError(
                    f"http_{exc.response.status_code}",
                    f"worker {path} returned {exc.response.status_code}",
                    retryable=exc.response.status_code >= 500,
                ) from exc
            except ValueError as exc:
                raise RenderWorkerError(
                    "malformed", f"worker {path} returned non-JSON", retryable=False
                ) from exc
        raise RenderWorkerError(
            "unreachable",
            f"worker {path} unreachable after {PRE_SUBMIT_ATTEMPTS} attempts "
            f"(Tailscale down?): {last_error}",
            retryable=True,
        ) from last_error

    def check_health(self) -> dict[str, Any]:
        # /health stays unauthenticated so monitoring can probe liveness.
        return self._get("/health")

    def check_capacity(self) -> dict[str, Any]:
        return self._get("/capacity", authenticated=True)

    # -- submit (single attempt: a POST may have started GPU work) ---------

    def submit_render(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not str(payload.get("prompt") or "").strip():
            raise RenderWorkerError(
                "validation", "render payload has no prompt", retryable=False
            )
        try:
            response = self._client.post("/render", json=payload, headers=_auth_headers())
        except httpx.ConnectError as exc:
            raise RenderWorkerError(
                "unreachable", f"worker unreachable (Tailscale down?): {exc}", retryable=True
            ) from exc
        except httpx.TimeoutException as exc:
            # The render may still be running on the worker; never re-POST
            # blindly. The job returns to pending for an explicit resubmit.
            raise RenderWorkerError(
                "timeout",
                f"worker render timed out after {self.timeout_seconds}s; "
                f"the job may still be running on the worker: {exc}",
                retryable=True,
            ) from exc
        if response.status_code == 401:
            raise RenderWorkerError(
                "unauthorized",
                "worker rejected the credentials: set RENDER_WORKER_API_TOKEN",
                retryable=False,
            )
        if response.status_code == 422:
            raise RenderWorkerError(
                "validation", f"worker rejected the payload: {response.text[:500]}",
                retryable=False,
            )
        if response.status_code >= 500:
            raise RenderWorkerError(
                f"http_{response.status_code}",
                f"worker failed with {response.status_code}: {response.text[:500]}",
                retryable=True,
            )
        if response.status_code >= 400:
            raise RenderWorkerError(
                f"http_{response.status_code}",
                f"worker returned {response.status_code}: {response.text[:500]}",
                retryable=False,
            )
        return self._extract_output(response, payload)

    def _extract_output(
        self, response: httpx.Response, payload: dict[str, Any]
    ) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        output_name = str(payload.get("output_name") or "render.mp4")
        if content_type.startswith("video/") or (
            "application/octet-stream" in content_type and response.content
        ):
            if not response.content:
                raise RenderWorkerError(
                    "malformed", "worker returned an empty video body", retryable=False
                )
            return {"output_bytes": response.content, "output_name": output_name}
        try:
            body = response.json()
        except ValueError as exc:
            raise RenderWorkerError(
                "malformed",
                f"worker returned non-JSON, non-video ({content_type}): "
                f"{response.text[:300]}",
                retryable=False,
            ) from exc
        if not isinstance(body, dict):
            raise RenderWorkerError(
                "malformed", f"worker returned an unexpected body: {str(body)[:300]}",
                retryable=False,
            )
        if str(body.get("status") or "").lower() == "failed":
            raise RenderWorkerError(
                "worker_failed",
                f"worker reported failure: {json.dumps(body)[:500]}",
                retryable=True,
            )
        for key in ("output_url", "download_url", "url", "output_path"):
            location = body.get(key)
            if isinstance(location, str) and location.startswith(("http://", "https://")):
                # Fetched by the caller (streamed to disk); never loaded here.
                return {
                    "output_url": location,
                    "output_name": output_name,
                    "worker_job_id": _worker_job_id(body),
                }
        if isinstance(body.get("output_bytes"), str) and body["output_bytes"]:
            import base64

            try:
                return {
                    "output_bytes": base64.b64decode(body["output_bytes"]),
                    "output_name": output_name,
                }
            except ValueError as exc:
                raise RenderWorkerError(
                    "malformed", "worker output_bytes is not valid base64", retryable=False
                ) from exc
        worker_job_id = _worker_job_id(body)
        status = str(body.get("status") or "").lower()
        if worker_job_id and (status in ASYNC_STATUSES or not status):
            # Asynchronous worker: poll GET /render/{job_id}, then download.
            return {"worker_job_id": worker_job_id, "status": status or "submitted"}
        if str(body.get("status") or "").lower() == "completed":
            # The render SUCCEEDED on the worker, but only a worker-local
            # path came back and no download endpoint exists. Resubmitting
            # would re-render the same shot, so this is terminal: the
            # operator recovers the file (see docs/video-pipeline.md) and
            # completes the job with its metadata. All recovery details are
            # preserved in the job's error row.
            raise RenderWorkerError(
                "output_unavailable",
                "worker completed the render but returned only a worker-local path "
                f"(output_path={body.get('output_path')!r}, "
                f"size_bytes={body.get('size_bytes')!r}); no download endpoint "
                "exists yet - recover the file manually, then complete the job",
                retryable=False,
            )
        raise RenderWorkerError(
            "malformed",
            f"worker 200 carried no downloadable output: {json.dumps(body)[:300]}",
            retryable=False,
        )

    def get_render_status(self, worker_job_id: str) -> dict[str, Any]:
        """Poll the authenticated ``GET /render/{job_id}`` status endpoint."""
        job_id = _safe_job_id(worker_job_id)
        try:
            response = self._client.get(
                f"/render/{job_id}",
                headers=_auth_headers(),
                timeout=httpx.Timeout(HEALTH_TIMEOUT_SECONDS),
            )
        except httpx.ConnectError as exc:
            raise RenderWorkerError(
                "unreachable", f"worker unreachable (Tailscale down?): {exc}", retryable=True
            ) from exc
        except httpx.TimeoutException as exc:
            raise RenderWorkerError(
                "timeout", f"worker status timed out: {exc}", retryable=True
            ) from exc
        if response.status_code == 401:
            raise RenderWorkerError(
                "unauthorized",
                "worker status requires RENDER_WORKER_API_TOKEN",
                retryable=False,
            )
        if response.status_code == 404:
            raise RenderWorkerError(
                "not_found", f"worker has no job {job_id}", retryable=False
            )
        if response.status_code >= 500:
            raise RenderWorkerError(
                f"http_{response.status_code}",
                f"worker status failed with {response.status_code}: {response.text[:300]}",
                retryable=True,
            )
        if response.status_code >= 400:
            raise RenderWorkerError(
                f"http_{response.status_code}",
                f"worker status returned {response.status_code}: {response.text[:300]}",
                retryable=False,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RenderWorkerError(
                "malformed", "worker status returned non-JSON", retryable=False
            ) from exc
        if not isinstance(body, dict):
            raise RenderWorkerError(
                "malformed", "worker status returned an unexpected body", retryable=False
            )
        return body

    def download_render(
        self,
        worker_job_id: str,
        dest_path: str | Path,
        *,
        expected_sha256: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Stream ``GET /render/{job_id}/download`` to disk without RAM load."""
        job_id = _safe_job_id(worker_job_id)
        return self._stream_get(
            f"/render/{job_id}/download",
            dest_path,
            expected_sha256=expected_sha256,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
        )

    def download_url(
        self,
        url: str,
        dest_path: str | Path,
        *,
        expected_sha256: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Stream an absolute http(s) output URL to disk (same guards)."""
        if not url.startswith(("http://", "https://")):
            raise RenderWorkerError(
                "validation", f"refusing non-HTTP output URL: {url[:80]}", retryable=False
            )
        return self._stream_get(
            url,
            dest_path,
            expected_sha256=expected_sha256,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
        )

    def _stream_get(
        self,
        url_or_path: str,
        dest_path: str | Path,
        *,
        expected_sha256: str | None = None,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        budget = httpx.Timeout(timeout_seconds, connect=DEFAULT_CONNECT_TIMEOUT_SECONDS)
        try:
            stream = self._client.stream(
                "GET", url_or_path, headers=_auth_headers(), timeout=budget
            )
        except httpx.ConnectError as exc:
            raise RenderWorkerError(
                "unreachable", f"could not reach worker output: {exc}", retryable=True
            ) from exc
        except httpx.TimeoutException as exc:
            raise RenderWorkerError(
                "timeout", f"output download timed out: {exc}", retryable=True
            ) from exc
        try:
            with stream as response:
                if response.status_code == 401:
                    raise RenderWorkerError(
                        "unauthorized",
                        "output download requires RENDER_WORKER_API_TOKEN",
                        retryable=False,
                    )
                if response.status_code == 404:
                    raise RenderWorkerError(
                        "not_found", "worker output not found", retryable=False
                    )
                if response.status_code >= 400:
                    raise RenderWorkerError(
                        f"http_{response.status_code}",
                        f"output download failed with {response.status_code}",
                        retryable=response.status_code >= 500,
                    )
                content_type = response.headers.get("content-type", "")
                if content_type.startswith("application/json"):
                    raise self._json_download_error(response)
                expected_length = int(response.headers.get("content-length") or 0)
                digest = hashlib.sha256()
                received = 0
                with open(dest, "wb") as handle:
                    for chunk in response.iter_bytes(65536):
                        handle.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
        except httpx.HTTPError as exc:
            dest.unlink(missing_ok=True)
            raise RenderWorkerError(
                "incomplete_download", f"output download interrupted: {exc}", retryable=True
            ) from exc
        if expected_length and received != expected_length:
            dest.unlink(missing_ok=True)
            raise RenderWorkerError(
                "incomplete_download",
                f"output truncated: got {received} of {expected_length} bytes",
                retryable=True,
            )
        if received == 0:
            dest.unlink(missing_ok=True)
            raise RenderWorkerError("empty_output", "worker output was empty", retryable=True)
        sha256 = digest.hexdigest()
        if expected_sha256 and sha256 != expected_sha256.lower():
            dest.unlink(missing_ok=True)
            raise RenderWorkerError(
                "checksum_mismatch",
                f"downloaded sha256 {sha256} != worker {expected_sha256}",
                retryable=True,
            )
        return {"path": str(dest), "size_bytes": received, "sha256": sha256}

    @staticmethod
    def _json_download_error(response: httpx.Response) -> RenderWorkerError:
        try:
            body = response.json()
        except ValueError:
            body = response.read().decode("utf-8", "replace")[:300]
        if isinstance(body, dict) and str(body.get("status") or "").lower() == "failed":
            return RenderWorkerError(
                "worker_failed",
                f"worker reported failure: {json.dumps(body)[:300]}",
                retryable=True,
            )
        return RenderWorkerError(
            "malformed", f"download returned JSON, not video: {str(body)[:300]}",
            retryable=False,
        )


def get_renderer(name: str, **kwargs: Any) -> Renderer:
    """Return the submitter for a renderer tag. Only hunyuan has a worker."""
    if name == HunyuanRenderer.name:
        return HunyuanRenderer(**kwargs)
    raise RenderWorkerError(
        "no_submitter",
        f"renderer {name!r} has no worker submitter yet "
        "(asset/motion/ffmpeg shots are not dispatched in phase 1)",
        retryable=False,
    )


# ---------------------------------------------------------------------------
# Worker-output QA (ffprobe decode check + sha256, cf. marketing_worker/g2)
# ---------------------------------------------------------------------------


def _run_ffprobe(args: list[str]) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise RenderQAError("ffprobe is not installed (see scripts/doctor.py)")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", *args],
            text=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderQAError(f"ffprobe timed out: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "ffprobe failed").strip()
        raise RenderQAError(f"invalid MP4 (ffprobe failed): {detail[-500:]}")
    try:
        return json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise RenderQAError("ffprobe returned non-JSON") from exc


def qa_render_output(
    path: str | Path,
    *,
    expected_frames: int | None = None,
    expected_fps: int | None = None,
) -> dict[str, Any]:
    """Validate a worker MP4. Raises RenderQAError with a useful reason."""
    file_path = Path(path)
    if not file_path.is_file():
        raise RenderQAError(f"missing output file: {file_path}")
    size = file_path.stat().st_size
    if size <= 0:
        raise RenderQAError(f"output file is empty: {file_path}")
    streams = _run_ffprobe([
        "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=codec_name,width,height,nb_read_frames,avg_frame_rate",
        "-of", "json", str(file_path),
    ])
    video = (streams.get("streams") or [{}])[0]
    if not video.get("codec_name"):
        raise RenderQAError(f"no video stream found: {file_path}")
    frames = int(video.get("nb_read_frames") or 0)
    if expected_frames and frames and frames != expected_frames:
        raise RenderQAError(
            f"frame count {frames} != expected {expected_frames}: {file_path}"
        )
    duration_s: float | None = None
    if expected_fps:
        rate = str(video.get("avg_frame_rate") or "")
        if "/" in rate:
            numerator, _, denominator = rate.partition("/")
            fps = float(numerator) / float(denominator or 1)
            if fps and abs(fps - expected_fps) > 0.5:
                raise RenderQAError(
                    f"fps {fps:.2f} != expected {expected_fps}: {file_path}"
                )
    details: dict[str, Any] = {
        "codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "frames": frames or None,
        "file_size_bytes": size,
    }
    if expected_frames and not frames:
        container = _run_ffprobe([
            "-show_entries", "format=duration", "-of", "json", str(file_path)
        ])
        try:
            duration_s = float((container.get("format") or {}).get("duration") or 0)
        except ValueError as exc:
            raise RenderQAError(f"unreadable duration: {file_path}") from exc
        if duration_s <= 0:
            raise RenderQAError(f"non-positive duration: {file_path}")
        if expected_fps and abs(duration_s - expected_frames / expected_fps) > 0.6:
            raise RenderQAError(
                f"duration {duration_s:.2f}s != expected "
                f"{expected_frames / expected_fps:.2f}s: {file_path}"
            )
        details["duration_seconds"] = duration_s
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    details["sha256"] = digest.hexdigest()
    return details


# ---------------------------------------------------------------------------
# Dispatch: claim -> health/capacity -> submit -> save -> QA -> complete/fail
# ---------------------------------------------------------------------------

CONTROL_PLANE_WORKER_ID = "control-plane"


def worker_status() -> dict[str, Any]:
    """Failure-tolerant health/capacity snapshot (never raises)."""
    try:
        url = render_worker_url()
    except RenderWorkerError as exc:
        return {"configured": False, "error": str(exc)}
    try:
        with HunyuanRenderer(base_url=url) as renderer:
            return {
                "configured": True,
                "url": url,
                "health": renderer.check_health(),
                "capacity": renderer.check_capacity(),
            }
    except RenderWorkerError as exc:
        return {"configured": True, "url": url, "error": f"{exc.kind}: {exc}"}


def submit_hunyuan_job(job_id: str, *, timeout_seconds: int | None = None) -> dict[str, Any]:
    """Submit one queued hunyuan job to the MI300X worker.

    Claims the job (one attempt), checks health/capacity, POSTs the payload,
    then follows whichever shape the worker answers with: synchronous bytes
    (or a download URL) are saved directly; a queued/running worker job is
    polled via ``GET /render/{job_id}`` and streamed via
    ``GET /render/{job_id}/download``. Either way the MP4 lands under the
    render output dir, passes ffprobe QA, and the job is recorded
    ``completed`` (with output metadata incl. the worker job id and render
    completion time) or ``failed`` (retryable when the failure might be
    transient). Raises RenderWorkerError on failure AFTER the job row has
    been updated, so callers see both the exception and the persisted
    state. Only ``pending`` jobs can be submitted.
    """
    from core import video_store

    job = video_store.get_job(job_id)
    if not job:
        raise ValueError(f"render job not found: {job_id}")
    timeout = timeout_seconds or render_timeout_seconds()
    # Resolve configuration BEFORE claiming: usage/config errors (missing
    # RENDER_WORKER_URL, no submitter for this renderer) must never consume
    # an attempt or touch the job row.
    renderer = get_renderer(job["renderer"], timeout_seconds=timeout)
    if not isinstance(renderer, HunyuanRenderer):
        raise ValueError(f"renderer {job['renderer']!r} cannot be submitted to the MI300X worker")
    video_store.claim_job(job_id, CONTROL_PLANE_WORKER_ID, lease_seconds=timeout + 300)
    output_name = Path(job["output_path"]).name or f"{job_id}.mp4"
    payload = {
        "job_id": job["id"],
        "renderer": "hunyuan",
        "prompt": job["prompt"],
        "negative_prompt": job.get("negative_prompt") or "",
        "resolution": job.get("resolution") or "480p",
        "aspect_ratio": aspect_ratio_for(job.get("width"), job.get("height")),
        "frames": job.get("frames") or 81,
        "fps": job.get("fps") or 24,
        "steps": job.get("steps") or 20,
        "seed": job.get("seed") if job.get("seed") is not None else 42,
        "dtype": job.get("dtype") or "bf16",
        "output_name": output_name,
    }
    deadline = time.monotonic() + timeout
    worker_job_id: str | None = None
    worker_status_body: dict[str, Any] | None = None
    try:
        with renderer:
            health = renderer.check_health()
            capacity = renderer.check_capacity()
            if str(capacity.get("status") or "").lower() not in {"", "available", "idle", "healthy"}:
                raise RenderWorkerError(
                    "worker_busy",
                    f"worker reports status {capacity.get('status')!r}; not submitting",
                    retryable=True,
                )
            submitted = renderer.submit_render(payload)
            saved = render_output_dir() / f"{job_id}.mp4"
            if "output_bytes" in submitted:
                saved.write_bytes(submitted["output_bytes"])
            elif "output_url" in submitted:
                renderer.download_url(submitted["output_url"], saved)
            else:
                worker_job_id = submitted["worker_job_id"]
                worker_status_body = _poll_until_done(renderer, worker_job_id, deadline)
                checksum = worker_status_body.get("sha256") or worker_status_body.get("checksum")
                renderer.download_render(
                    worker_job_id,
                    saved,
                    expected_sha256=str(checksum) if checksum else None,
                    timeout_seconds=max(10, int(deadline - time.monotonic())),
                )
            qa = qa_render_output(saved, expected_frames=job.get("frames"), expected_fps=job.get("fps"))
    except RenderQAError as exc:
        video_store.fail_job(
            job_id, CONTROL_PLANE_WORKER_ID, code="qa_failed", message=str(exc), retryable=True
        )
        raise RenderWorkerError("qa_failed", str(exc), retryable=True) from exc
    except RenderWorkerError as exc:
        video_store.fail_job(
            job_id, CONTROL_PLANE_WORKER_ID,
            code=exc.kind, message=str(exc), retryable=exc.retryable,
        )
        raise
    details = dict(qa)
    completed = video_store.complete_job(
        job_id,
        CONTROL_PLANE_WORKER_ID,
        result={
            "outputPath": str(saved),
            "durationSeconds": details.get("duration_seconds"),
            "frames": details.get("frames") or job.get("frames"),
            "fileSizeBytes": details.get("file_size_bytes"),
            "metadata": {
                "sha256": details.get("sha256"),
                "codec": details.get("codec"),
                "width": details.get("width"),
                "height": details.get("height"),
                "output_name": output_name,
                "worker_job_id": worker_job_id,
                "worker_health": health,
                "worker_capacity": capacity,
                "worker_status": worker_status_body,
            },
        },
    )
    return completed


def _poll_until_done(
    renderer: HunyuanRenderer, worker_job_id: str, deadline: float
) -> dict[str, Any]:
    """Poll the worker status endpoint until the job completes or fails."""
    interval = poll_interval_seconds()
    while True:
        if time.monotonic() >= deadline:
            raise RenderWorkerError(
                "timeout",
                f"worker job {worker_job_id} did not complete within budget",
                retryable=True,
            )
        body = renderer.get_render_status(worker_job_id)
        status = str(body.get("status") or "").lower()
        if status == "completed":
            return body
        if status == "failed":
            raise RenderWorkerError(
                "worker_failed",
                f"worker job {worker_job_id} failed: {json.dumps(body)[:500]}",
                retryable=True,
            )
        if status and status not in ASYNC_STATUSES:
            raise RenderWorkerError(
                "malformed",
                f"worker job {worker_job_id} has unknown status {status!r}",
                retryable=False,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            continue  # deadline check at the top raises timeout
        time.sleep(min(interval, remaining))
