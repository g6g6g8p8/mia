from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS owner (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    email TEXT,
    timezone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    identity TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0,
    blocked_until TEXT
);

CREATE TABLE IF NOT EXISTS areas (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT 'slate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, name)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id) ON DELETE CASCADE,
    area_id TEXT REFERENCES areas(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    due_date TEXT,
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'done')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS tasks_owner_status_idx
ON tasks(owner_id, status, due_date, priority);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    owner_id INTEGER REFERENCES owner(id) ON DELETE SET NULL,
    event TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id),
    request_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    answer TEXT,
    proposal_json TEXT,
    usage_json TEXT,
    task_id TEXT REFERENCES tasks(id),
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, request_key)
);

CREATE TABLE IF NOT EXISTS onboarding (
    owner_id INTEGER PRIMARY KEY REFERENCES owner(id),
    goal TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id),
    area_id TEXT NOT NULL REFERENCES areas(id),
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS personal_context (
    owner_id INTEGER PRIMARY KEY REFERENCES owner(id),
    text TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_items (
    id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owner(id),
    area_id TEXT NOT NULL REFERENCES areas(id),
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_id,area_id,hash)
);
CREATE TABLE IF NOT EXISTS document_imports (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    PRIMARY KEY(document_id,import_id,path)
);
CREATE TABLE IF NOT EXISTS chunks (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    searchable TEXT NOT NULL,
    PRIMARY KEY(document_id,ordinal)
);
"""


def data_dir() -> Path:
    path = Path(os.environ.get("MIA_DATA_DIR", "./data")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "mia.db"


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(database_path(), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def initialize() -> None:
    with connect() as db:
        db.executescript(SCHEMA)
        document_columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
        if 'active' not in document_columns:
            db.execute("ALTER TABLE documents ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        onboarding_columns = {row[1] for row in db.execute("PRAGMA table_info(onboarding)")}
        if 'goal_revision' not in onboarding_columns:
            db.execute('ALTER TABLE onboarding ADD COLUMN goal_revision INTEGER NOT NULL DEFAULT 0')
        if 'step' not in onboarding_columns:
            db.execute("ALTER TABLE onboarding ADD COLUMN step INTEGER NOT NULL DEFAULT 0")
        columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
        for name in ('personalization_base_json','personalization_result_json'):
            if name not in columns:
                db.execute(f'ALTER TABLE runs ADD COLUMN {name} TEXT')
        if 'organization_result_json' not in columns:
            db.execute('ALTER TABLE runs ADD COLUMN organization_result_json TEXT')
        for name, declaration in {"reserved_micro": "INTEGER NOT NULL DEFAULT 0", "charged_micro": "INTEGER NOT NULL DEFAULT 0", "cost_status": "TEXT NOT NULL DEFAULT 'unknown'", "pricing_json": "TEXT"}.items():
            if name not in columns:
                db.execute(f"ALTER TABLE runs ADD COLUMN {name} {declaration}")
        db.execute("UPDATE runs SET state='failed', error='Execução interrompida. Não reenviada automaticamente.' WHERE state='running'")


@contextmanager
def transaction(immediate: bool = False) -> Iterator[sqlite3.Connection]:
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

