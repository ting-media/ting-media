"""
TING Customer Success — Unified client-communication hub
==========================================================
Ingests messages from WhatsApp (bridge), email and call transcripts,
links them to CRM clients, and runs an AI crew that proposes tasks
(pending human approval) so nothing a client asked for falls through.

Endpoints (X-Team-Token unless noted):
  POST /api/cs/ingest                    — channel event (bridge/pollers)
  POST /api/cs/webhooks/timeos?token=    — TIME OS transcript webhook
  GET  /api/cs/suggestions               — list (default pending)
  POST /api/cs/suggestions/{id}/approve  — mark approved {task_id}
  POST /api/cs/suggestions/{id}/dismiss  — dismiss
  GET  /api/cs/threads/unmapped          — conversations not linked to a client
  GET  /api/cs/mappings                  — current thread→client links
  POST /api/cs/mappings                  — link thread to client
  GET  /api/cs/timeline?client_id=       — unified message feed for a client
  GET  /api/cs/wa/status | /wa/qr | /wa/groups — WhatsApp bridge proxy
  GET  /api/cs/stats                     — counters for the dashboard
"""

import os
import re
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

import db
from routes_agents import claude, _extract_json, now_iso, MODEL_RESEARCH

log = logging.getLogger("ting-cs")

router = APIRouter(prefix="/api/cs", tags=["customer-success"])

TEAM_SECRET   = os.environ.get("TING_TEAM_SECRET", "team-secret-change-me")
WA_BRIDGE_URL = os.environ.get("WA_BRIDGE_URL", "http://127.0.0.1:3002")
MODEL_TRIAGE  = os.environ.get("CS_TRIAGE_MODEL", "claude-haiku-4-5-20251001")
MODEL_CS      = os.environ.get("CS_MODEL", "claude-sonnet-4-6")
DEBOUNCE_SEC  = int(os.environ.get("CS_DEBOUNCE_SEC", "90"))


def require_team(x_team_token: Optional[str]):
    if x_team_token != TEAM_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Schema ────────────────────────────────────────────────────────────────────

CS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cs_messages (
    id          TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,              -- whatsapp | email | call
    thread_id   TEXT NOT NULL,              -- group jid / phone jid / email address / call id
    thread_name TEXT,
    client_id   TEXT,                       -- CRM client id (null until mapped)
    client_name TEXT,
    sender_id   TEXT,
    sender_name TEXT,
    direction   TEXT DEFAULT 'in',          -- in | out
    text        TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cs_msg_thread ON cs_messages(thread_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_cs_msg_client ON cs_messages(client_id, sent_at);

CREATE TABLE IF NOT EXISTS cs_mappings (
    thread_id   TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    thread_name TEXT,
    client_id   TEXT NOT NULL,
    client_name TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cs_tasks_snapshot (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    client_name TEXT,
    stage       INTEGER,
    due_date    TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS cs_clients_snapshot (
    id    TEXT PRIMARY KEY,
    name  TEXT
);

CREATE TABLE IF NOT EXISTS cs_client_brains (
    client_id    TEXT PRIMARY KEY,
    client_name  TEXT,
    summary      TEXT,
    contacts     TEXT,        -- JSON [{name, role, notes}]
    msg_count    INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'idle',   -- idle | learning
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS cs_suggestions (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL DEFAULT 'task',   -- task | alert
    client_id   TEXT,
    client_name TEXT,
    thread_id   TEXT,
    channel     TEXT,
    title       TEXT NOT NULL,
    details     TEXT,
    urgency     TEXT DEFAULT 'medium',          -- high | medium | low
    evidence    TEXT,                           -- JSON array of quoted messages
    status      TEXT NOT NULL DEFAULT 'pending',-- pending | approved | dismissed
    task_id     TEXT,
    created_at  TEXT NOT NULL,
    decided_at  TEXT
);
"""

def init_cs_db():
    with db.get_conn() as conn:
        conn.executescript(CS_SCHEMA)
        # migrations — add columns for task-update suggestions
        for col in ("target_task_id TEXT", "target_task_title TEXT"):
            try:
                conn.execute(f"ALTER TABLE cs_suggestions ADD COLUMN {col}")
            except Exception:
                pass
        # thread_type: 'client' (dedicated client chat) | 'internal' (multi-client hub)
        try:
            conn.execute("ALTER TABLE cs_mappings ADD COLUMN thread_type TEXT DEFAULT 'client'")
        except Exception:
            pass

init_cs_db()


# ── Ingest ────────────────────────────────────────────────────────────────────

class IngestBody(BaseModel):
    channel: str                       # whatsapp | email | call
    thread_id: str
    thread_name: Optional[str] = None
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    direction: Optional[str] = "in"
    text: str
    sent_at: Optional[str] = None      # ISO; defaults to now


_pending_analysis: dict = {}           # thread_id -> asyncio.Task (debounce)


@router.post("/ingest", status_code=201)
async def ingest(body: IngestBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    text = (body.text or "").strip()
    if not text:
        return {"ok": True, "skipped": "empty"}
    mapping = _get_mapping(body.thread_id)
    msg_id = uuid.uuid4().hex[:14]
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO cs_messages(id,channel,thread_id,thread_name,client_id,client_name,"
            "sender_id,sender_name,direction,text,sent_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (msg_id, body.channel, body.thread_id, body.thread_name,
             mapping["client_id"] if mapping else None,
             mapping["client_name"] if mapping else None,
             body.sender_id, body.sender_name, body.direction or "in",
             text[:8000], body.sent_at or now_iso(), now_iso()))
    # Only analyse inbound messages on threads linked to a client
    if mapping and (body.direction or "in") == "in":
        _schedule_analysis(body.thread_id)
    return {"ok": True, "id": msg_id, "mapped": bool(mapping)}


class TasksSnapshotBody(BaseModel):
    tasks: list


@router.post("/tasks-snapshot")
def tasks_snapshot(body: TasksSnapshotBody, x_team_token: Optional[str] = Header(None)):
    """CRM pushes its open tasks so the agent can match conversations to existing work."""
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM cs_tasks_snapshot")
        for t in body.tasks[:500]:
            conn.execute(
                "INSERT OR REPLACE INTO cs_tasks_snapshot(id,title,client_name,stage,due_date,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (str(t.get("id")), (t.get("title") or "").strip()[:200], (t.get("client") or "").strip()[:120],
                 int(t.get("stage") or 1), t.get("dueDate") or "", now_iso()))
    return {"ok": True, "count": len(body.tasks)}


def _open_tasks_for(client_name: str):
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, stage, due_date FROM cs_tasks_snapshot WHERE TRIM(client_name)=TRIM(?) LIMIT 30",
            (client_name or "",)).fetchall()
    return [dict(r) for r in rows]


def _all_open_tasks(limit: int = 80):
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, client_name, stage, due_date FROM cs_tasks_snapshot LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def _client_roster():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM cs_clients_snapshot ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def _match_client(name: str, roster: list):
    """Resolve an agent-provided client name to a roster id, tolerant to spacing."""
    if not name:
        return None, None
    n = name.strip()
    for c in roster:
        if (c["name"] or "").strip() == n:
            return c["id"], c["name"]
    # loose contains match
    for c in roster:
        cn = (c["name"] or "").strip()
        if cn and (cn in n or n in cn):
            return c["id"], c["name"]
    return None, name


class ClientsSnapshotBody(BaseModel):
    clients: list


@router.post("/clients-snapshot")
def clients_snapshot(body: ClientsSnapshotBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM cs_clients_snapshot")
        for c in body.clients[:300]:
            conn.execute("INSERT OR REPLACE INTO cs_clients_snapshot(id,name) VALUES(?,?)",
                         (str(c.get("id")), (c.get("name") or "").strip()[:120]))
    return {"ok": True, "count": len(body.clients)}


@router.post("/webhooks/timeos", status_code=201)
async def timeos_webhook(payload: dict, token: str = Query(None)):
    """Generic transcript webhook. Configure TIME OS to POST here with ?token=<team secret>."""
    if token != TEAM_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Accept flexible payloads — pull the obvious fields
    text = payload.get("transcript") or payload.get("text") or payload.get("summary") or ""
    title = payload.get("title") or payload.get("meeting_title") or "שיחת וידאו"
    call_id = str(payload.get("id") or payload.get("call_id") or uuid.uuid4().hex[:8])
    body = IngestBody(channel="call", thread_id=f"call:{call_id}", thread_name=title,
                      sender_name=payload.get("participants") and ", ".join(map(str, payload["participants"])) or "שיחה",
                      text=f"[תמלול שיחה: {title}]\n{text}"[:8000])
    return await ingest(body, x_team_token=TEAM_SECRET)


# ── Mapping ───────────────────────────────────────────────────────────────────

def _get_mapping(thread_id: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM cs_mappings WHERE thread_id=?", (thread_id,)).fetchone()
        return dict(row) if row else None


class MapBody(BaseModel):
    thread_id: str
    channel: str
    thread_name: Optional[str] = None
    client_id: str
    client_name: str
    thread_type: Optional[str] = "client"   # client | internal


@router.post("/mappings", status_code=201)
def add_mapping(body: MapBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO cs_mappings(thread_id,channel,thread_name,client_id,client_name,created_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET "
            "client_id=excluded.client_id, client_name=excluded.client_name, thread_name=excluded.thread_name",
            (body.thread_id, body.channel, body.thread_name, body.client_id, body.client_name, now_iso()))
        # retro-link existing messages
        conn.execute("UPDATE cs_messages SET client_id=?, client_name=? WHERE thread_id=?",
                     (body.client_id, body.client_name, body.thread_id))
    return {"ok": True}


@router.delete("/mappings/{thread_id:path}")
def delete_mapping(thread_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM cs_mappings WHERE thread_id=?", (thread_id,))
    return {"ok": True}


@router.get("/mappings")
def list_mappings(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM cs_mappings ORDER BY client_name").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            stat = conn.execute(
                "SELECT COUNT(*) c, MAX(sent_at) last FROM cs_messages WHERE thread_id=?",
                (d["thread_id"],)).fetchone()
            d["msg_count"] = stat["c"]
            d["last_at"] = stat["last"]
            out.append(d)
    return out


@router.post("/threads/{thread_id:path}/analyze")
async def analyze_now(thread_id: str, x_team_token: Optional[str] = Header(None)):
    """Trigger analysis immediately on a thread's stored history (the 'נתח עכשיו' button)."""
    require_team(x_team_token)
    if not _get_mapping(thread_id):
        raise HTTPException(status_code=400, detail="השיחה לא משויכת ללקוח")
    asyncio.create_task(analyze_thread(thread_id, force=True))
    return {"ok": True}


@router.get("/threads/unmapped")
def unmapped_threads(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT m.thread_id, m.channel, MAX(m.thread_name) thread_name,
                   COUNT(*) msg_count, MAX(m.sent_at) last_at,
                   (SELECT text FROM cs_messages WHERE thread_id=m.thread_id ORDER BY sent_at DESC LIMIT 1) snippet
            FROM cs_messages m
            WHERE m.client_id IS NULL
            GROUP BY m.thread_id, m.channel
            ORDER BY last_at DESC LIMIT 50
        """).fetchall()
    return [dict(r) for r in rows]


# ── Timeline & stats ──────────────────────────────────────────────────────────

@router.get("/timeline")
def timeline(client_id: str, limit: int = 80, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, channel, thread_id, thread_name, sender_name, direction, text, sent_at "
            "FROM cs_messages WHERE client_id=? ORDER BY sent_at DESC LIMIT ?",
            (client_id, min(limit, 300))).fetchall()
    return [dict(r) for r in rows]


@router.get("/stats")
def stats(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        msgs = conn.execute("SELECT COUNT(*) c FROM cs_messages").fetchone()["c"]
        pend = conn.execute("SELECT COUNT(*) c FROM cs_suggestions WHERE status='pending'").fetchone()["c"]
        maps = conn.execute("SELECT COUNT(*) c FROM cs_mappings").fetchone()["c"]
        unmapped = conn.execute("SELECT COUNT(DISTINCT thread_id) c FROM cs_messages WHERE client_id IS NULL").fetchone()["c"]
        today = datetime.now(timezone.utc).date().isoformat()
        today_msgs = conn.execute("SELECT COUNT(*) c FROM cs_messages WHERE created_at LIKE ?", (today+"%",)).fetchone()["c"]
    return {"messages": msgs, "today_messages": today_msgs, "pending_suggestions": pend,
            "mapped_threads": maps, "unmapped_threads": unmapped}


# ── Suggestions ───────────────────────────────────────────────────────────────

@router.get("/suggestions")
def list_suggestions(status: str = "pending", limit: int = 50,
                     x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cs_suggestions WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, min(limit, 200))).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try: d["evidence"] = json.loads(d.get("evidence") or "[]")
        except Exception: d["evidence"] = []
        out.append(d)
    return out


class ApproveBody(BaseModel):
    task_id: Optional[str] = None


@router.post("/suggestions/{sid}/approve")
def approve_suggestion(sid: str, body: ApproveBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("UPDATE cs_suggestions SET status='approved', task_id=?, decided_at=? WHERE id=?",
                     (body.task_id, now_iso(), sid))
    return {"ok": True}


@router.post("/suggestions/{sid}/dismiss")
def dismiss_suggestion(sid: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("UPDATE cs_suggestions SET status='dismissed', decided_at=? WHERE id=?",
                     (now_iso(), sid))
    return {"ok": True}


# ── AI crew ───────────────────────────────────────────────────────────────────

TRIAGE_SYSTEM = (
    "אתה סוכן טריאז' במחלקת שירות לקוחות של חברת הפקות וידאו ישראלית. "
    "אתה מקבל קטע שיחה עם לקוח ועונה רק ב-JSON תקין."
)

CS_SYSTEM = (
    "אתה מנהל קאסטמר סאקסס בחברת הפקות וידאו (TING MEDIA). "
    "תפקידך לוודא ששום בקשה של לקוח לא נופלת בין הכיסאות. "
    "אתה מנתח שיחות ומציע משימות מעשיות לצוות. עברית בלבד, JSON תקין בלבד."
)


def _schedule_analysis(thread_id: str):
    """Debounce: analyse a thread DEBOUNCE_SEC after its last message."""
    old = _pending_analysis.get(thread_id)
    if old and not old.done():
        old.cancel()
    _pending_analysis[thread_id] = asyncio.create_task(_analyze_after_delay(thread_id))


async def _analyze_after_delay(thread_id: str):
    try:
        await asyncio.sleep(DEBOUNCE_SEC)
        await analyze_thread(thread_id)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception(f"cs analysis failed for {thread_id}")


async def analyze_thread(thread_id: str, force: bool = False):
    mapping = _get_mapping(thread_id)
    if not mapping:
        return
    thread_type = (mapping.get("thread_type") or "client")
    with db.get_conn() as conn:
        msgs = conn.execute(
            "SELECT sender_name, direction, text, sent_at FROM cs_messages "
            "WHERE thread_id=? ORDER BY sent_at DESC LIMIT 30", (thread_id,)).fetchall()
        pending = conn.execute(
            "SELECT title FROM cs_suggestions WHERE thread_id=? AND status='pending'",
            (thread_id,)).fetchall()
    if not msgs:
        return
    convo = "\n".join(
        f"[{m['sent_at'][:16]}] {'→ אנחנו' if m['direction']=='out' else (m['sender_name'] or 'לקוח')}: {m['text'][:400]}"
        for m in reversed([dict(m) for m in msgs]))
    pending_titles = [p["title"] for p in pending]
    stage_names = {1:'בריף',2:'כתיבה',3:'אישור תסריט',4:'קביעת צילום',5:'צילום',6:'עריכה',7:'אישור סופרוויזר',8:'אישור לקוח',9:'סגירה'}

    # Stage 1 — fast triage: is there anything actionable at all?
    # (skipped on manual "analyze now" — there the user explicitly wants a full pass)
    ctx = ("שיחה פנימית/מנהלתית של הצוות (עשויה לגעת בכמה לקוחות)"
           if thread_type == "internal"
           else f'שיחה עם הלקוח "{mapping["client_name"]}"')
    if not force:
        triage_raw = await claude(MODEL_TRIAGE, TRIAGE_SYSTEM, (
            f"{ctx} (ערוץ: {mapping['channel']}):\n\n{convo}\n\n"
            "האם בהודעות האחרונות יש בקשה, תלונה, שאלה פתוחה או התחייבות שדורשת פעולה מהצוות שלנו? "
            'החזר: {"actionable": true/false, "reason": "משפט אחד"}'
        ), max_tokens=300)
        try:
            triage = _extract_json(triage_raw)
        except Exception:
            return
        if not triage.get("actionable"):
            return

    roster = _client_roster()
    new = 0

    if thread_type == "internal":
        # Multi-client hub: the agent attributes each finding to a client BY CONTENT.
        roster_names = [c["name"] for c in roster] or ["(לא הוגדרו לקוחות)"]
        all_tasks = _all_open_tasks()
        tasks_block = "\n".join(
            f"- [{t['id']}] לקוח: {t['client_name']} · \"{t['title']}\" · שלב: {stage_names.get(t['stage'], t['stage'])}"
            for t in all_tasks) or "(אין משימות פתוחות)"
        cs_raw = await claude(MODEL_CS, CS_SYSTEM, (
            f"זו שיחה פנימית/מנהלתית של צוות TING MEDIA (לא שיחה של לקוח יחיד). "
            f"שיחה אחת כזו עשויה לגעת בכמה לקוחות שונים, ולכן לכל ממצא עליך לזהות לאיזה לקוח הוא שייך.\n\n"
            f"רשימת הלקוחות שלנו (השתמש בשם המדויק מהרשימה):\n{json.dumps(roster_names, ensure_ascii=False)}\n\n"
            f"השיחה:\n{convo}\n\n"
            f"משימות פתוחות (כל הלקוחות):\n{tasks_block}\n\n"
            f"הצעות שכבר ממתינות (אל תכפיל): {json.dumps(pending_titles, ensure_ascii=False)}\n\n"
            "לכל ממצא שמצריך פעולה: זהה את הלקוח מהרשימה לפי התוכן. "
            "אם הממצא נוגע למשימה קיימת — action=\"update\" עם task_id מהרשימה. אחרת action=\"new\". "
            "אם הממצא הוא משימה פנימית שאינה קשורה ללקוח ספציפי (כמו משכורות) — client=\"פנימי\". "
            "עד 4 הצעות, רק מה שבאמת נדרש. לכל הצעה: client (שם מהרשימה או 'פנימי'), action, task_id (רק בעדכון), "
            "כותרת קצרה, פירוט, דחיפות (high/medium/low), וציטוט 1-2 הודעות כראיה.\n"
            'החזר: {"suggestions":[{"client":"","action":"new|update","task_id":"","title":"","details":"","urgency":"medium","evidence":["ציטוט"]}]}'
        ), max_tokens=2500)
        try:
            result = _extract_json(cs_raw)
        except Exception:
            return
        tasks_by_id = {t["id"]: t for t in all_tasks}
        for s in (result.get("suggestions") or [])[:4]:
            title = (s.get("title") or "").strip()
            if not title or title in pending_titles:
                continue
            raw_client = (s.get("client") or "").strip()
            if raw_client in ("פנימי", "internal", "—", ""):
                cid, cname = None, ("פנימי" if raw_client else None)
            else:
                cid, cname = _match_client(raw_client, roster)
            action = (s.get("action") or "new").strip()
            target = tasks_by_id.get(str(s.get("task_id") or "").strip())
            kind = "update" if (action == "update" and target) else "task"
            with db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO cs_suggestions(id,kind,client_id,client_name,thread_id,channel,"
                    "title,details,urgency,evidence,status,created_at,target_task_id,target_task_title) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], kind, cid, cname,
                     thread_id, mapping["channel"], title[:200], (s.get("details") or "")[:2000],
                     s.get("urgency") or "medium",
                     json.dumps((s.get("evidence") or [])[:3], ensure_ascii=False),
                     "pending", now_iso(),
                     target["id"] if kind == "update" else None,
                     target["title"] if kind == "update" else None))
            new += 1
        if new:
            log.info(f"cs: {new} internal-hub suggestions ({thread_id})")
        return

    # ── Dedicated client chat: everything belongs to the mapped client ──
    open_tasks = _open_tasks_for(mapping["client_name"])
    tasks_block = "\n".join(
        f"- [{t['id']}] \"{t['title']}\" · שלב: {stage_names.get(t['stage'], t['stage'])}"
        + (f" · יעד: {t['due_date']}" if t.get('due_date') else "")
        for t in open_tasks) or "(אין משימות פתוחות על הלקוח הזה)"

    cs_raw = await claude(MODEL_CS, CS_SYSTEM, (
        f"לקוח: {mapping['client_name']} · ערוץ: {mapping['channel']} · שיחה: {mapping.get('thread_name') or thread_id}\n\n"
        f"{_brain_context(mapping['client_id'])}"
        f"השיחה האחרונה:\n{convo}\n\n"
        f"משימות פתוחות שכבר עובדים עליהן אצל הלקוח הזה:\n{tasks_block}\n\n"
        f"הצעות שכבר ממתינות לאישור (אל תכפיל אותן): {json.dumps(pending_titles, ensure_ascii=False)}\n\n"
        "החלט לכל ממצא בשיחה:\n"
        "• אם הוא נוגע למשימה קיימת מהרשימה (עדכון סטטוס, תיקון, שינוי דרישה, דדליין, אישור של הלקוח) — "
        "הצע עדכון עם action=\"update\" ו-task_id המדויק מהרשימה.\n"
        "• אם זו בקשה חדשה שאין לה משימה — הצע action=\"new\".\n"
        "עד 2 הצעות, רק אם באמת נדרש. לכל הצעה: כותרת קצרה, פירוט מעשי, "
        "דחיפות (high/medium/low), וציטוט 1-2 הודעות כראיה.\n"
        'החזר: {"suggestions":[{"action":"new|update","task_id":"רק בעדכון","title":"","details":"","urgency":"medium","evidence":["ציטוט"]}]} '
        'או {"suggestions":[]} אם אין צורך.'
    ), max_tokens=1500)
    try:
        result = _extract_json(cs_raw)
    except Exception:
        return
    tasks_by_id = {t["id"]: t for t in open_tasks}
    for s in (result.get("suggestions") or [])[:2]:
        title = (s.get("title") or "").strip()
        if not title or title in pending_titles:
            continue
        action = (s.get("action") or "new").strip()
        target = tasks_by_id.get(str(s.get("task_id") or "").strip())
        kind = "update" if (action == "update" and target) else "task"
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO cs_suggestions(id,kind,client_id,client_name,thread_id,channel,"
                "title,details,urgency,evidence,status,created_at,target_task_id,target_task_title) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], kind, mapping["client_id"], mapping["client_name"],
                 thread_id, mapping["channel"], title[:200], (s.get("details") or "")[:2000],
                 s.get("urgency") or "medium",
                 json.dumps((s.get("evidence") or [])[:3], ensure_ascii=False),
                 "pending", now_iso(),
                 target["id"] if kind == "update" else None,
                 target["title"] if kind == "update" else None))
        new += 1
    if new:
        log.info(f"cs: {new} suggestions for {mapping['client_name']} ({thread_id})")


# ── Client brains ─────────────────────────────────────────────────────────────
# A per-client "small brain": a learned context summary + a contact roster
# (who speaks for the client, and their role). Built by scanning the client's
# conversations. Fed back into analysis so suggestions are context-aware.

BRAIN_SYSTEM = (
    "אתה אנליסט קשרי-לקוח בחברת הפקות וידאו (TING MEDIA). אתה קורא את כל השיח עם לקוח "
    "ובונה 'תיק מודיעין' תמציתי: מי האנשים אצל הלקוח ומה תפקידם, ומה ההקשר והסטטוס. "
    "עברית בלבד, JSON תקין בלבד."
)


def get_brain(client_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM cs_client_brains WHERE client_id=?", (client_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try: d["contacts"] = json.loads(d.get("contacts") or "[]")
    except Exception: d["contacts"] = []
    return d


def _brain_context(client_id):
    """Short context string to inject into analysis prompts."""
    b = get_brain(client_id)
    if not b or not b.get("summary"):
        return ""
    contacts = "; ".join(f"{c.get('name')} ({c.get('role')})" for c in (b.get("contacts") or [])[:8])
    return (f"\n\n🧠 מה שאנחנו כבר יודעים על הלקוח:\n{b['summary']}\n"
            + (f"אנשי קשר ידועים: {contacts}\n" if contacts else ""))


async def learn_client_brain(client_id: str, client_name: str):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO cs_client_brains(client_id,client_name,status,updated_at) VALUES(?,?,'learning',?) "
            "ON CONFLICT(client_id) DO UPDATE SET status='learning', client_name=excluded.client_name",
            (client_id, client_name, now_iso()))
        msgs = conn.execute(
            "SELECT sender_name, direction, text, sent_at, thread_name FROM cs_messages "
            "WHERE client_id=? ORDER BY sent_at DESC LIMIT 250", (client_id,)).fetchall()
    msgs = list(reversed([dict(m) for m in msgs]))
    if not msgs:
        with db.get_conn() as conn:
            conn.execute("UPDATE cs_client_brains SET status='idle', summary=?, updated_at=? WHERE client_id=?",
                         ("עדיין אין מספיק שיחות כדי ללמוד את הלקוח הזה.", now_iso(), client_id))
        return
    convo = "\n".join(
        f"[{m['sent_at'][:16]}] {'→ אנחנו' if m['direction']=='out' else (m['sender_name'] or 'לקוח')}: {m['text'][:300]}"
        for m in msgs)
    open_tasks = _open_tasks_for(client_name)
    tasks_line = ", ".join(t["title"] for t in open_tasks) or "—"
    try:
        raw = await claude(MODEL_CS, BRAIN_SYSTEM, (
            f"לקוח: {client_name}\n"
            f"משימות פתוחות כרגע: {tasks_line}\n\n"
            f"כל השיח שנקלט עם הלקוח (כרונולוגי):\n{convo}\n\n"
            "בנה תיק לקוח:\n"
            "1) summary — סיכום עד 180 מילים: על מה הלקוח, מי מקבל ההחלטות, נושאים חוזרים, טון, "
            "מצב נוכחי, ודברים שחשוב לזכור (רגישויות, העדפות).\n"
            "2) contacts — מערך של האנשים שזיהית בשיח, לכל אחד: name, role (תפקיד משוער: מנהל/ת שיווק, "
            "רפרנט/ית, עוזר/ת, בעלים וכו'), notes (משפט על מה הוא אחראי / איך לעבוד איתו).\n"
            'החזר JSON: {"summary":"","contacts":[{"name":"","role":"","notes":""}]}'
        ), max_tokens=2000)
        data = _extract_json(raw)
    except Exception as e:
        log.exception("learn_client_brain failed")
        with db.get_conn() as conn:
            conn.execute("UPDATE cs_client_brains SET status='idle', updated_at=? WHERE client_id=?",
                         (now_iso(), client_id))
        return
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE cs_client_brains SET summary=?, contacts=?, msg_count=?, status='idle', updated_at=? WHERE client_id=?",
            ((data.get("summary") or "")[:4000],
             json.dumps((data.get("contacts") or [])[:20], ensure_ascii=False),
             len(msgs), now_iso(), client_id))
    log.info(f"brain learned for {client_name}: {len(data.get('contacts') or [])} contacts, {len(msgs)} msgs")


@router.get("/brains")
def list_brains(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM cs_client_brains ORDER BY updated_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try: d["contacts"] = json.loads(d.get("contacts") or "[]")
        except Exception: d["contacts"] = []
        out.append(d)
    return out


@router.get("/brain/{client_id}")
def get_brain_ep(client_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    b = get_brain(client_id)
    # include linked WhatsApp threads + message count for the client card
    with db.get_conn() as conn:
        threads = conn.execute(
            "SELECT thread_id, thread_name, thread_type FROM cs_mappings WHERE client_id=?",
            (client_id,)).fetchall()
        cnt = conn.execute("SELECT COUNT(*) c FROM cs_messages WHERE client_id=?", (client_id,)).fetchone()["c"]
    return {"brain": b, "threads": [dict(t) for t in threads], "message_count": cnt}


class LearnBody(BaseModel):
    client_name: str


@router.post("/brain/{client_id}/learn")
async def learn_brain_ep(client_id: str, body: LearnBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    asyncio.create_task(learn_client_brain(client_id, body.client_name))
    return {"ok": True}


class BrainPatchBody(BaseModel):
    summary: Optional[str] = None
    contacts: Optional[list] = None


@router.patch("/brain/{client_id}")
def patch_brain(client_id: str, body: BrainPatchBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    fields, vals = [], []
    if body.summary is not None:
        fields.append("summary=?"); vals.append(body.summary[:4000])
    if body.contacts is not None:
        fields.append("contacts=?"); vals.append(json.dumps(body.contacts[:20], ensure_ascii=False))
    if not fields:
        return {"ok": True}
    fields.append("updated_at=?"); vals.append(now_iso())
    vals.append(client_id)
    with db.get_conn() as conn:
        conn.execute(f"UPDATE cs_client_brains SET {', '.join(fields)} WHERE client_id=?", vals)
    return {"ok": True}


# ── WhatsApp bridge proxy ─────────────────────────────────────────────────────

async def _bridge_get(path: str):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(WA_BRIDGE_URL + path)
        return r.json()
    except Exception as e:
        return {"status": "offline", "error": str(e)}


@router.get("/wa/status")
async def wa_status(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    return await _bridge_get("/status")


@router.get("/wa/qr")
async def wa_qr(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    return await _bridge_get("/qr")


@router.get("/wa/groups")
async def wa_groups(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    return await _bridge_get("/groups")


@router.get("/wa/chats")
async def wa_chats(q: str = "", type: str = "all", limit: int = 500,
                   x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    from urllib.parse import quote
    return await _bridge_get(f"/chats?q={quote(q)}&type={type}&limit={limit}")
