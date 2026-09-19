import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "company.db"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS buffer_orgs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                env_prefix TEXT NOT NULL,
                organization_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS buffer_org_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                channel_id TEXT,
                profile_url TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(org_id, platform),
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER,
                agent TEXT NOT NULL,
                task_type TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'queued',
                input TEXT,
                output TEXT,
                error TEXT,
                requires_approval INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS org_capabilities (
                org_id INTEGER NOT NULL,
                capability TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (org_id, capability),
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );
            """
        )
        _migrate_project_to_org(conn)
        _migrate_org_domain(conn)


def _migrate_project_to_org(conn: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "projects" not in tables:
        return

    projects = [dict(r) for r in conn.execute("SELECT * FROM projects").fetchall()]
    if not projects:
        conn.execute("DROP TABLE IF EXISTS projects")
        return

    tasks_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "org_id" not in tasks_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN org_id INTEGER")
        tasks_cols.add("org_id")

    for p in projects:
        slug = p["slug"]
        prefix = "BUFFER_" if slug == "company-core" else f"BUFFER_{slug.upper().replace('-', '_')}_"
        org_id = conn.execute(
            "SELECT id FROM buffer_orgs WHERE slug = ?", (slug,)
        ).fetchone()
        if org_id:
            continue
        cursor = conn.execute(
            "INSERT INTO buffer_orgs (name, slug, env_prefix, organization_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (p["name"], slug, prefix, "", p["created_at"], p["updated_at"]),
        )
        new_org_id = cursor.lastrowid
        if "project_id" in tasks_cols:
            conn.execute(
                "UPDATE tasks SET org_id = ? WHERE project_id = ?",
                (new_org_id, p["id"]),
            )

    conn.execute("DROP TABLE IF EXISTS projects")


def _migrate_org_domain(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(buffer_orgs)").fetchall()}
    if "domain" not in cols:
        conn.execute("ALTER TABLE buffer_orgs ADD COLUMN domain TEXT NOT NULL DEFAULT ''")


VALID_CAPABILITIES = (
    "sales_prospecting",
    "ai_drafts",
    "marketing_campaigns",
    "buffer_publishing",
    "inbound_intake",
    "coding",
    "monitoring",
)


def set_org_capabilities(org_id: int, capabilities: dict[str, bool]) -> dict[str, bool]:
    timestamp = now_iso()
    with connect() as conn:
        for capability, enabled in capabilities.items():
            if capability not in VALID_CAPABILITIES:
                raise ValueError(f"unknown capability: {capability}")
            conn.execute(
                "INSERT INTO org_capabilities (org_id, capability, enabled, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(org_id, capability) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at",
                (org_id, capability, 1 if enabled else 0, timestamp),
            )
    return get_org_capabilities(org_id)


def get_org_capabilities(org_id: int) -> dict[str, bool]:
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT capability, enabled FROM org_capabilities WHERE org_id = ?", (org_id,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {row[0]: bool(row[1]) for row in rows}


def get_setup_step() -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'setup_step'").fetchone()
        return str(row[0]) if row else "not_started"


def set_setup_step(step: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('setup_step', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (step,),
        )


def _seed_orgs_from_env() -> None:
    from core.state import list_orgs, create_org, create_org_account, get_org_by_slug

    existing = {org["env_prefix"]: org for org in list_orgs()}
    created = set()

    def _backfill_accounts(org_id: int, prefix: str) -> None:
        existing_accts = {a["platform"]: a for a in get_org_accounts(org_id)}
        if "instagram" not in existing_accts:
            ch = os.environ.get(f"{prefix}INSTAGRAM_CHANNEL_ID", "").strip() or None
            if ch:
                create_org_account(org_id, "instagram", channel_id=ch)
        if "x" not in existing_accts:
            ch = os.environ.get(f"{prefix}X_CHANNEL_ID", "").strip() or None
            if ch:
                create_org_account(org_id, "x", channel_id=ch)
        if "linkedin" not in existing_accts:
            ch = os.environ.get(f"{prefix}LINKEDIN_CHANNEL_ID", "").strip() or None
            url = os.environ.get(f"{prefix}LINKEDIN_PROFILE_URL", "").strip() or None
            if ch or url:
                create_org_account(org_id, "linkedin", channel_id=ch, profile_url=url)

    if os.environ.get("BUFFER_API_KEY", "").strip() and "BUFFER_" not in existing:
        org = create_org("Company Core", "company-core", env_prefix="BUFFER_")
        create_org_account(org["id"], "instagram", channel_id=os.environ.get("BUFFER_INSTAGRAM_CHANNEL_ID", "").strip() or None)
        create_org_account(org["id"], "x", channel_id=os.environ.get("BUFFER_X_CHANNEL_ID", "").strip() or None)
        linkedin_ch = os.environ.get("BUFFER_LINKEDIN_CHANNEL_ID", "").strip() or None
        linkedin_url = os.environ.get("BUFFER_LINKEDIN_PROFILE_URL", "").strip() or None
        if linkedin_ch or linkedin_url:
            create_org_account(org["id"], "linkedin", channel_id=linkedin_ch, profile_url=linkedin_url)
        created.add("BUFFER_")
    elif "BUFFER_" in existing:
        _backfill_accounts(existing["BUFFER_"]["id"], "BUFFER_")

    for key, value in list(os.environ.items()):
        if not key.startswith("BUFFER_") or not key.endswith("_API_KEY") or not value.strip():
            continue
        middle = key[len("BUFFER_"):-len("_API_KEY")]
        if not middle or middle == "API":
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,30}", middle):
            continue
        prefix = f"BUFFER_{middle}_"
        if prefix in existing or prefix in created:
            if prefix in existing:
                _backfill_accounts(existing[prefix]["id"], prefix)
            continue
        slug = middle.lower().replace("_", "-")
        name = middle.replace("_", " ").title()
        org = create_org(name, slug, env_prefix=prefix)
        create_org_account(org["id"], "instagram", channel_id=os.environ.get(f"{prefix}INSTAGRAM_CHANNEL_ID", "").strip() or None)
        create_org_account(org["id"], "x", channel_id=os.environ.get(f"{prefix}X_CHANNEL_ID", "").strip() or None)
        linkedin_ch = os.environ.get(f"{prefix}LINKEDIN_CHANNEL_ID", "").strip() or None
        linkedin_url = os.environ.get(f"{prefix}LINKEDIN_PROFILE_URL", "").strip() or None
        if linkedin_ch or linkedin_url:
            create_org_account(org["id"], "linkedin", channel_id=linkedin_ch, profile_url=linkedin_url)
        created.add(prefix)


# ---------------------------------------------------------------------------
# Buffer orgs
# ---------------------------------------------------------------------------

def create_org(
    name: str,
    slug: str,
    env_prefix: str = "BUFFER_",
    organization_id: str = "",
    domain: str = "",
) -> dict:
    timestamp = now_iso()
    with connect() as conn:
        _migrate_org_domain(conn)
        existing = conn.execute(
            "SELECT * FROM buffer_orgs WHERE slug = ?", (slug,)
        ).fetchone()
        if existing:
            row = dict(existing)
            if domain and not row.get("domain"):
                conn.execute(
                    "UPDATE buffer_orgs SET domain = ?, updated_at = ? WHERE id = ?",
                    (domain, timestamp, row["id"]),
                )
                row["domain"] = domain
            return row
        cursor = conn.execute(
            "INSERT INTO buffer_orgs (name, slug, env_prefix, organization_id, domain, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, slug, env_prefix, organization_id, domain, timestamp, timestamp),
        )
        row = conn.execute(
            "SELECT * FROM buffer_orgs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_org(org_id: int) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM buffer_orgs WHERE id = ?", (org_id,)).fetchone()
        return dict(row) if row else None


def get_org_by_slug(slug: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM buffer_orgs WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None


def list_orgs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM buffer_orgs ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]


def set_active_org(org_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('active_org_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(org_id),),
        )


def get_active_org() -> Optional[dict]:
    with connect() as conn:
        setting = conn.execute(
            "SELECT value FROM settings WHERE key = 'active_org_id'"
        ).fetchone()
        if not setting:
            legacy = conn.execute(
                "SELECT value FROM settings WHERE key = 'active_project_id'"
            ).fetchone()
            if legacy:
                setting = legacy
        if not setting:
            return None
        org = conn.execute(
            "SELECT * FROM buffer_orgs WHERE id = ?", (int(setting["value"]),)
        ).fetchone()
        return dict(org) if org else None


def load_org_key(org_id: int) -> str:
    org = get_org(org_id)
    if not org:
        raise ValueError(f"org {org_id} not found")
    prefix = org["env_prefix"]
    api_key = os.environ.get(f"{prefix}API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            f"Buffer API key not configured for org {org['slug']}: "
            f"set {prefix}API_KEY in engines/g3/config/g3.env"
        )
    return api_key


# ---------------------------------------------------------------------------
# Buffer org accounts
# ---------------------------------------------------------------------------

def create_org_account(
    org_id: int,
    platform: str,
    channel_id: str | None = None,
    profile_url: str | None = None,
) -> dict:
    timestamp = now_iso()
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM buffer_org_accounts WHERE org_id = ? AND platform = ?",
            (org_id, platform),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE buffer_org_accounts SET channel_id = ?, profile_url = ? WHERE id = ?",
                (channel_id, profile_url, existing["id"]),
            )
            row = conn.execute(
                "SELECT * FROM buffer_org_accounts WHERE id = ?", (existing["id"],)
            ).fetchone()
            return dict(row)
        cursor = conn.execute(
            "INSERT INTO buffer_org_accounts (org_id, platform, channel_id, profile_url, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, platform, channel_id, profile_url, timestamp),
        )
        row = conn.execute(
            "SELECT * FROM buffer_org_accounts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_org_accounts(org_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM buffer_org_accounts WHERE org_id = ? ORDER BY platform",
            (org_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_org_account(org_id: int, platform: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM buffer_org_accounts WHERE org_id = ? AND platform = ?",
            (org_id, platform),
        ).fetchone()
        return dict(row) if row else None


def linkedin_profile_for_org(org_id: int) -> Optional[str]:
    account = get_org_account(org_id, "linkedin")
    if account and account.get("profile_url"):
        return account["profile_url"]
    return None


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def create_task(
    *,
    org_id: Optional[int],
    agent: str,
    task_type: str,
    input_text: str,
    priority: str = "normal",
    requires_approval: bool = False,
) -> dict:
    timestamp = now_iso()

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                org_id,
                agent,
                task_type,
                priority,
                status,
                input,
                requires_approval,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                org_id,
                agent,
                task_type,
                priority,
                input_text,
                int(requires_approval),
                timestamp,
                timestamp,
            ),
        )

        task_id = cursor.lastrowid

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

        return dict(row)


def update_task_status(
    task_id: int,
    status: str,
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), task_id),
        )


def complete_task(
    task_id: int,
    output: str,
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', output = ?, error = NULL, updated_at = ? WHERE id = ?",
            (output, now_iso(), task_id),
        )


def fail_task(
    task_id: int,
    error: str,
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (error, now_iso(), task_id),
        )


def get_recent_tasks(
    limit: int = 20,
) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                tasks.*,
                buffer_orgs.name AS org_name,
                buffer_orgs.slug AS org_slug
            FROM tasks
            LEFT JOIN buffer_orgs
                ON buffer_orgs.id = tasks.org_id
            ORDER BY tasks.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


# Backwards compat aliases for code that hasn't been migrated yet
create_project = lambda name, slug, **kw: create_org(name, slug, **kw)
get_project = get_org
get_project_by_slug = get_org_by_slug
list_projects = list_orgs
set_active_project = set_active_org
get_active_project = get_active_org
