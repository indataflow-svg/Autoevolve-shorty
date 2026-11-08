"""Hosted lead-form definitions.

Each form is a slug plus an ordered field list. The same definition drives the
public page at /f/{slug} and the mapping used when an external tool (Tally,
an indataflow form, any POSTing service) submits to the shared intake
endpoint. Submissions themselves are not stored here: they become leads plus
an inbound 'form' interaction through the existing sales store, so Replies
and every downstream action keep working unchanged.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("SALES_DB", "data/company.db"))

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}[a-z0-9]$|^[a-z0-9]$")

# Field types the hosted page knows how to render. Free-text keys outside the
# lead schema still work: they land in metadata.answers.
FIELD_TYPES = ("text", "email", "tel", "url", "textarea", "select", "checkbox", "hidden")

# Hosted-field key -> LeadIntake column. Everything else is an answer.
MAPPED_KEYS = {
    "email": "email",
    "full_name": "full_name",
    "name": "full_name",
    "job_title": "job_title",
    "title": "job_title",
    "company": "company",
    "company_domain": "company_domain",
    "domain": "company_domain",
    "phone": "phone",
    "country": "country",
    "message": "message",
    "consent": "consent",
}

DEFAULT_FORM = {
    "slug": "contact",
    "name": "Contact us",
    "description": "Tell us about your team and we will follow up with next steps.",
    "fields": [
        {"key": "full_name", "label": "Full name", "type": "text", "required": True},
        {"key": "email", "label": "Work email", "type": "email", "required": True},
        {"key": "company", "label": "Company", "type": "text", "required": False},
        {"key": "phone", "label": "Phone", "type": "tel", "required": False},
        {"key": "message", "label": "What are you looking for?", "type": "textarea", "required": False},
        {"key": "consent", "label": "You may contact me about this request.", "type": "checkbox", "required": False},
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"form_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_form_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS form_definitions (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                fields_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def seed_default_form() -> dict[str, Any]:
    """Explicitly create the optional operator contact form.

    Startup no longer creates it: a fresh database must not contain demo rows
    or an unowned public form.
    """
    init_form_db()
    existing = get_form(DEFAULT_FORM["slug"])
    if existing:
        return existing
    return create_form(
        DEFAULT_FORM["slug"],
        DEFAULT_FORM["name"],
        DEFAULT_FORM["fields"],
        description=DEFAULT_FORM["description"],
    )


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    form = dict(row)
    form["fields"] = json.loads(form.pop("fields_json") or "[]")
    form["active"] = bool(form["active"])
    return form


def list_forms() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM form_definitions ORDER BY created_at ASC"
        ).fetchall()
    return [form for row in rows if (form := _decode(row))]


def get_form(slug: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM form_definitions WHERE slug = ?", (slug.strip().lower(),)
        ).fetchone()
    return _decode(row)


def validate_fields(fields: Any) -> list[dict[str, Any]]:
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields must be a non-empty list")
    if len(fields) > 40:
        raise ValueError("a form cannot define more than 40 fields")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in fields:
        if not isinstance(raw, dict):
            raise ValueError("each field must be an object")
        key = str(raw.get("key") or "").strip().lower()
        label = str(raw.get("label") or "").strip()
        field_type = str(raw.get("type") or "text").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
            raise ValueError(f"invalid field key: {key!r}")
        if key in seen:
            raise ValueError(f"duplicate field key: {key}")
        seen.add(key)
        if not label or len(label) > 120:
            raise ValueError(f"field {key} needs a label of at most 120 characters")
        if field_type not in FIELD_TYPES:
            raise ValueError(f"field {key} has unsupported type {field_type!r}")
        field: dict[str, Any] = {"key": key, "label": label, "type": field_type, "required": bool(raw.get("required"))}
        if field_type == "select":
            options = [str(option).strip() for option in (raw.get("options") or []) if str(option).strip()]
            if not options:
                raise ValueError(f"select field {key} needs options")
            field["options"] = options[:30]
        cleaned.append(field)
    return cleaned


def create_form(slug: str, name: str, fields: Any, description: str | None = None) -> dict[str, Any]:
    slug = (slug or "").strip().lower()
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("slug must be lowercase letters, digits, and hyphens")
    if get_form(slug):
        raise ValueError(f"a form with slug '{slug}' already exists")
    name = (name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("name is required and must be at most 120 characters")
    cleaned = validate_fields(fields)
    timestamp = _now()
    form = {
        "id": _new_id(),
        "slug": slug,
        "name": name,
        "description": (description or "").strip()[:400] or None,
        "fields": cleaned,
        "active": True,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with connect() as connection:
        connection.execute(
            "INSERT INTO form_definitions (id, slug, name, description, fields_json, active, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (form["id"], slug, name, form["description"], json.dumps(cleaned), timestamp, timestamp),
        )
    return form


def update_form(
    slug: str,
    *,
    name: str | None = None,
    description: str | None = None,
    fields: Any = None,
    active: bool | None = None,
) -> dict[str, Any]:
    existing = get_form(slug)
    if not existing:
        raise ValueError("form not found")
    updates: dict[str, Any] = {"updated_at": _now()}
    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name or len(cleaned_name) > 120:
            raise ValueError("name must be at most 120 characters")
        updates["name"] = cleaned_name
    if description is not None:
        updates["description"] = description.strip()[:400] or None
    if fields is not None:
        updates["fields_json"] = json.dumps(validate_fields(fields))
    if active is not None:
        updates["active"] = 1 if active else 0
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with connect() as connection:
        connection.execute(
            f"UPDATE form_definitions SET {assignments} WHERE slug = ?",
            (*updates.values(), existing["slug"]),
        )
    refreshed = get_form(existing["slug"])
    assert refreshed
    return refreshed


def map_answers_to_lead(form: dict[str, Any] | None, answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a submission into a LeadIntake-shaped payload and the clean
    labeled answers shown in Replies. Known keys populate the lead record;
    every non-empty answer is also kept under its form label so the reply
    detail reads like the form the visitor filled in. Forms define their own
    keys; an external submission with no matching form still maps the
    well-known keys and keeps the rest."""
    lead_payload: dict[str, Any] = {}
    clean_answers: dict[str, Any] = {}
    known_labels = {
        str(field.get("key", "")).strip().lower(): str(field.get("label") or field.get("key") or "")
        for field in ((form or {}).get("fields") or [])
    }
    for raw_key, value in answers.items():
        key = str(raw_key).strip().lower()
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        elif isinstance(value, bool):
            if not value:
                continue
        elif value is None:
            continue
        label = known_labels.get(key) or raw_key.replace("_", " ").strip().capitalize()
        clean_answers[label] = value
        column = MAPPED_KEYS.get(key)
        if column and column not in lead_payload:
            lead_payload[column] = value
    return lead_payload, clean_answers
