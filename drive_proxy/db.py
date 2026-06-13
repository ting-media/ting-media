"""
TING Review — SQLite Database Layer
====================================
Single-file DB, WAL mode, zero external servers.
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("TING_DB_PATH", "/opt/ting-review/ting_review.db")

# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    client_id    TEXT,
    task_id      TEXT,
    status       TEXT NOT NULL DEFAULT 'draft',
    current_version  INTEGER DEFAULT 0,
    current_round    INTEGER DEFAULT 1,
    created_by   TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
    id              TEXT PRIMARY KEY,
    review_id       TEXT NOT NULL,
    version_number  INTEGER NOT NULL,
    round           INTEGER NOT NULL DEFAULT 1,
    drive_file_id   TEXT NOT NULL,
    file_name       TEXT,
    duration        REAL,
    uploaded_by     TEXT,
    uploaded_at     TEXT NOT NULL,
    note            TEXT,
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comments (
    id              TEXT PRIMARY KEY,
    review_id       TEXT NOT NULL,
    version_id      TEXT,
    round           INTEGER DEFAULT 1,
    timecode        REAL NOT NULL,
    text            TEXT NOT NULL,
    author_name     TEXT NOT NULL,
    author_type     TEXT NOT NULL DEFAULT 'team',
    parent_id       TEXT,
    annotation_json TEXT,
    resolved        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_tokens (
    token           TEXT PRIMARY KEY,
    review_id       TEXT NOT NULL,
    client_name     TEXT,
    client_email    TEXT,
    permissions     TEXT NOT NULL DEFAULT 'comment',
    expires_at      TEXT,
    last_seen_at    TEXT,
    revoked         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id                  TEXT PRIMARY KEY,
    review_id           TEXT NOT NULL,
    version_id          TEXT,
    approved_by_token   TEXT,
    approved_by_name    TEXT,
    note                TEXT,
    approved_at         TEXT NOT NULL,
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_comments_review   ON comments(review_id, version_id);
CREATE INDEX IF NOT EXISTS idx_tokens_review     ON review_tokens(review_id);
CREATE INDEX IF NOT EXISTS idx_versions_review   ON versions(review_id);
"""


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def row_to_dict(row) -> dict:
    return dict(row) if row else None

def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


# ── Reviews ───────────────────────────────────────────────────────────────────

def create_review(title: str, created_by: str, client_id: str = None, task_id: str = None) -> dict:
    rid = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reviews (id, title, client_id, task_id, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (rid, title, client_id, task_id, created_by, now_iso())
        )
    return get_review(rid)


def get_review(review_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        return row_to_dict(row)


def list_reviews(created_by: str = None) -> list:
    with get_conn() as conn:
        if created_by:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE created_by=? ORDER BY created_at DESC", (created_by,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
        return rows_to_list(rows)


def update_review_status(review_id: str, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, review_id))


# ── Versions ──────────────────────────────────────────────────────────────────

def add_version(review_id: str, drive_file_id: str, uploaded_by: str,
                file_name: str = None, duration: float = None, note: str = None) -> dict:
    with get_conn() as conn:
        # Get current max version
        row = conn.execute(
            "SELECT MAX(version_number) as maxv FROM versions WHERE review_id=?", (review_id,)
        ).fetchone()
        next_v = (row["maxv"] or 0) + 1

        # Get current round from review
        rev = conn.execute("SELECT current_round FROM reviews WHERE id=?", (review_id,)).fetchone()
        current_round = rev["current_round"] if rev else 1

        vid = new_id()
        conn.execute(
            """INSERT INTO versions (id, review_id, version_number, round, drive_file_id,
               file_name, duration, uploaded_by, uploaded_at, note)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (vid, review_id, next_v, current_round, drive_file_id,
             file_name, duration, uploaded_by, now_iso(), note)
        )
        # Update review's current_version
        conn.execute(
            "UPDATE reviews SET current_version=?, status='in_review' WHERE id=?",
            (next_v, review_id)
        )
    return get_version(vid)


def get_version(version_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
        return row_to_dict(row)


def get_current_version(review_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT v.* FROM versions v
               JOIN reviews r ON r.id = v.review_id
               WHERE v.review_id=? AND v.version_number = r.current_version""",
            (review_id,)
        ).fetchone()
        return row_to_dict(row)


def list_versions(review_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM versions WHERE review_id=? ORDER BY version_number ASC", (review_id,)
        ).fetchall()
        return rows_to_list(rows)


# ── Comments ──────────────────────────────────────────────────────────────────

def add_comment(review_id: str, timecode: float, text: str, author_name: str,
                author_type: str = "client", version_id: str = None,
                round_num: int = 1, parent_id: str = None,
                annotation_json: str = None) -> dict:
    cid = new_id()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO comments (id, review_id, version_id, round, timecode, text,
               author_name, author_type, parent_id, annotation_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, review_id, version_id, round_num, timecode, text,
             author_name, author_type, parent_id, annotation_json, now_iso())
        )
    return get_comment(cid)


def get_comment(comment_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        return row_to_dict(row)


def list_comments(review_id: str, version_id: str = None, include_resolved: bool = True) -> list:
    with get_conn() as conn:
        if version_id:
            q = "SELECT * FROM comments WHERE review_id=? AND version_id=?"
            args = (review_id, version_id)
        else:
            q = "SELECT * FROM comments WHERE review_id=?"
            args = (review_id,)
        if not include_resolved:
            q += " AND resolved=0"
        q += " ORDER BY timecode ASC, created_at ASC"
        return rows_to_list(conn.execute(q, args).fetchall())


def resolve_comment(comment_id: str, resolved: bool = True):
    with get_conn() as conn:
        conn.execute("UPDATE comments SET resolved=? WHERE id=?", (1 if resolved else 0, comment_id))


def delete_comment(comment_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))


# ── Tokens ───────────────────────────────────────────────────────────────────

def create_token(review_id: str, client_name: str = None, client_email: str = None,
                 permissions: str = "comment", expires_at: str = None) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO review_tokens (token, review_id, client_name, client_email,
               permissions, expires_at, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (token, review_id, client_name, client_email, permissions, expires_at, now_iso())
        )
    return token


def validate_token(token: str) -> dict | None:
    """Returns token row if valid, None if invalid/expired/revoked."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM review_tokens WHERE token=? AND revoked=0", (token,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        # Check expiry
        if d.get("expires_at"):
            if datetime.fromisoformat(d["expires_at"]) < datetime.now(timezone.utc):
                return None
        # Update last_seen
        ts = now_iso()
        conn.execute(
            "UPDATE review_tokens SET last_seen_at=? WHERE token=?", (ts, token)
        )
        d["last_seen_at"] = ts   # reflect update in the returned dict
        return d


def revoke_token(token: str):
    with get_conn() as conn:
        conn.execute("UPDATE review_tokens SET revoked=1 WHERE token=?", (token,))


def list_tokens(review_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM review_tokens WHERE review_id=? ORDER BY created_at DESC", (review_id,)
        ).fetchall()
        return rows_to_list(rows)


# ── Approvals ─────────────────────────────────────────────────────────────────

def add_approval(review_id: str, version_id: str, approved_by_token: str,
                 approved_by_name: str, note: str = None) -> dict:
    aid = new_id()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO approvals (id, review_id, version_id, approved_by_token,
               approved_by_name, note, approved_at) VALUES (?,?,?,?,?,?,?)""",
            (aid, review_id, version_id, approved_by_token, approved_by_name, note, now_iso())
        )
        conn.execute("UPDATE reviews SET status='approved' WHERE id=?", (review_id,))
    return {"id": aid, "review_id": review_id, "version_id": version_id,
            "approved_by_name": approved_by_name, "note": note}
