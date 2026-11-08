"""Thin bridge to the G3 publishing CLI.

Only the pieces the manual-post flow needs: run the configured ``company-core-g3``
binary with the G3 environment and parse its last JSON object. Campaign/media
engines (G1/G2) are intentionally not part of this module.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def _environment(path: Path | None) -> dict[str, str]:
    environment = dict(os.environ)
    if path and path.is_file():
        for key, value in dotenv_values(path).items():
            if value is not None:
                environment[key] = value
    return environment


def _command_environment(command: list[str], env_file: Path | None) -> dict[str, str]:
    environment = _environment(env_file)
    executable_dir = str(Path(command[0]).expanduser().resolve().parent)
    inherited_path = environment.get("PATH", "")
    environment["PATH"] = executable_dir + (os.pathsep + inherited_path if inherited_path else "")
    return environment


def run(
    command: list[str],
    *,
    cwd: Path,
    env_file: Path | None,
    timeout: int,
    log_path: Path,
) -> str:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_command_environment(command, env_file),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(
            f"COMMAND: {command!r}\nTIMEOUT: {timeout}s\nSTDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}\n",
            encoding="utf-8",
        )
        raise RuntimeError(f"command timed out after {timeout}s: {command[0]}") from exc
    log_path.write_text(
        f"COMMAND: {command!r}\nEXIT: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n",
        encoding="utf-8",
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "unknown command failure").strip()
        raise RuntimeError(f"{command[0]} exited {result.returncode}: {detail[-1500:]}")
    return result.stdout


def last_json(text: str) -> dict:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append((consumed, value))
    if not candidates:
        raise RuntimeError("command did not return a JSON object")
    return max(candidates, key=lambda item: item[0])[1]
