"""
TING Agents — Copywriter Department API
=========================================
Multi-step AI pipeline: research -> write -> review.
Style is learned from the user's own scripts (synced from a Google Drive
folder shared with the service account, or pasted manually).

Endpoints (all require X-Team-Token):
  POST   /api/agents/copywriter/jobs        — create job {brief, link?, count?, video_type?, duration?}
  GET    /api/agents/copywriter/jobs        — list recent jobs
  GET    /api/agents/copywriter/jobs/{id}   — job status + result
  GET    /api/agents/style/docs             — list style docs
  POST   /api/agents/style/docs             — add style doc manually {title, content}
  DELETE /api/agents/style/docs/{id}        — remove style doc
  POST   /api/agents/style/sync-drive       — pull all Google Docs from a Drive folder {folder_id}
  GET    /api/agents/style/profile          — current distilled style profile
  POST   /api/agents/style/profile/rebuild  — re-distill style profile from docs
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
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import db

log = logging.getLogger("ting-agents")

router = APIRouter(prefix="/api/agents", tags=["agents"])

TEAM_SECRET       = os.environ.get("TING_TEAM_SECRET", "team-secret-change-me")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
MODEL_RESEARCH    = os.environ.get("AGENTS_RESEARCH_MODEL", "claude-sonnet-4-6")
MODEL_WRITER      = os.environ.get("AGENTS_WRITER_MODEL",   "claude-opus-4-8")
MODEL_CRITIC      = os.environ.get("AGENTS_CRITIC_MODEL",   "claude-sonnet-4-6")
DAILY_LIMIT       = int(os.environ.get("AGENTS_DAILY_LIMIT", "40"))


def require_team(x_team_token: Optional[str]):
    if x_team_token != TEAM_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Schema ────────────────────────────────────────────────────────────────────

AGENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL DEFAULT 'copywriter',
    brief       TEXT NOT NULL,
    link        TEXT,
    params_json TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    TEXT,
    result_json TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_styledocs (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    content       TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'manual',
    drive_file_id TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

def init_agents_db():
    with db.get_conn() as conn:
        conn.executescript(AGENTS_SCHEMA)
        # mark jobs interrupted by a restart
        conn.execute(
            "UPDATE agent_jobs SET status='error', error='הופסק בהפעלה מחדש של השרת', updated_at=? "
            "WHERE status NOT IN ('done','error')", (now_iso(),))

init_agents_db()


def _update_job(job_id, **fields):
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in fields)
    with db.get_conn() as conn:
        conn.execute(f"UPDATE agent_jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def _get_job(job_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM agent_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def _meta_get(key, default=None):
    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM agent_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def _meta_set(key, value):
    with db.get_conn() as conn:
        conn.execute("INSERT INTO agent_meta(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ── Claude helper ─────────────────────────────────────────────────────────────

async def claude(model: str, system: str, user: str, max_tokens: int = 8000) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured on server")
    async with httpx.AsyncClient(timeout=600) as client:
        r = await client.post(ANTHROPIC_URL, headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        })
    if r.status_code != 200:
        raise RuntimeError(f"Claude API {r.status_code}: {r.text[:300]}")
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _extract_json(text: str):
    """Lenient JSON extraction — handles ```json fences and surrounding prose."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = m.group(1) if m else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(candidate[start:end + 1])


# ── Link fetching ─────────────────────────────────────────────────────────────

TAG_RE = re.compile(r"<(script|style)[\s\S]*?</\1>|<[^>]+>", re.I)

async def fetch_link_text(url: str, limit: int = 12000) -> str:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TING-Agents/1.0)"
        }) as client:
            r = await client.get(url)
        text = TAG_RE.sub(" ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]
    except Exception as e:
        return f"(לא הצלחתי למשוך את הקישור: {e})"


# ── Style context ─────────────────────────────────────────────────────────────

DEFAULT_STYLE = """סגנון כתיבה לתסריטי וידאו שיווקיים בעברית:
- פתיחה ב-HOOK חזק ב-3 השניות הראשונות — שאלה מסקרנת, הצהרה מפתיעה או כאב של הקהל.
- שפה מדוברת וטבעית (דוגרי), משפטים קצרים, בלי מילים גבוהות.
- מבנה: הוק → בעיה/הקשר → פתרון/ערך → הוכחה → קריאה לפעולה.
- כתיבה לדיבור מול מצלמה: קצב, הפסקות, הוראות בימוי בסוגריים מרובעים.
- קריאה לפעולה ממוקדת אחת בסוף."""


def get_style_context(max_exemplars: int = 4, max_chars: int = 2000):
    profile = _meta_get("style_profile") or DEFAULT_STYLE
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT title, content FROM agent_styledocs ORDER BY RANDOM() LIMIT ?",
            (max_exemplars,)).fetchall()
    exemplars = "\n\n".join(
        f"### דוגמה: {r['title']}\n{r['content'][:max_chars]}" for r in rows)
    return profile, exemplars


# ── Pipeline ──────────────────────────────────────────────────────────────────

RESEARCH_SYSTEM = (
    "אתה חוקר תוכן במחלקת קריאייטיב של חברת הפקות וידאו ישראלית. "
    "תפקידך לנתח בריף וחומר גלם ולהפיק תובנות לכתיבת תסריטים. ענה בעברית בלבד."
)

WRITER_SYSTEM = (
    "אתה הקופירייטר הראשי של TING MEDIA — חברת הפקות וידאו ישראלית. "
    "אתה כותב תסריטי וידאו בעברית מדוברת וטבעית, בסגנון האישי של עמית (המנהל). "
    "אתה תמיד מחזיר JSON תקין בלבד, בלי טקסט נוסף."
)

CRITIC_SYSTEM = (
    "אתה עורך קריאייטיב בכיר. אתה מקבל תסריטים ומשפר אותם: הוק חד יותר, "
    "קיצור משפטים, הסרת קלישאות, חיזוק הקריאה לפעולה. שמור על הסגנון והמבנה. "
    "החזר JSON תקין בלבד באותו פורמט שקיבלת."
)


async def run_copywriter_job(job_id: str):
    job = _get_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    count      = min(int(params.get("count", 1) or 1), 5)
    video_type = params.get("video_type") or "סרטון שיווקי"
    duration   = params.get("duration") or "30-60 שניות"
    try:
        # ── Stage 1: research ────────────────────────────────────────────────
        _update_job(job_id, status="research", progress="🔎 חוקר את הנושא...")
        link_text = ""
        if job.get("link"):
            link_text = await fetch_link_text(job["link"])
        research_input = (
            f"בריף מהמנהל:\n{job['brief']}\n\n"
            + (f"תוכן שנמשך מהקישור ({job['link']}):\n{link_text}\n\n" if link_text else "")
            + f"סוג סרטון: {video_type} · אורך יעד: {duration}\n\n"
            "הפק: 1) תקציר העובדות החשובות 2) קהל יעד וכאבים 3) 5 זוויות/הוקים אפשריים "
            "4) טון מומלץ 5) מה חובה להגיד ומה אסור לפספס. תמציתי וענייני."
        )
        research = await claude(MODEL_RESEARCH, RESEARCH_SYSTEM, research_input, max_tokens=3000)

        # ── Stage 2: write ───────────────────────────────────────────────────
        _update_job(job_id, status="writing", progress="✍️ כותב טיוטות תסריט...")
        profile, exemplars = get_style_context()
        writer_input = (
            f"## פרופיל הסגנון שלנו\n{profile}\n\n"
            + (f"## דוגמאות מתסריטים אמיתיים שלנו (חקה את הסגנון, לא את התוכן)\n{exemplars}\n\n" if exemplars else "")
            + f"## בריף\n{job['brief']}\n\n## מחקר\n{research}\n\n"
            f"## משימה\nכתוב {count} גרסאות תסריט ({video_type}, {duration}). "
            "כל תסריט: כותרת, הוק (3 שניות ראשונות), גוף מלא מוכן להקלטה עם הוראות בימוי "
            "בסוגריים מרובעים, וקריאה לפעולה.\n"
            'החזר JSON בפורמט: {"scripts":[{"title":"","hook":"","body":"","cta":""}]}'
        )
        draft_raw = await claude(MODEL_WRITER, WRITER_SYSTEM, writer_input, max_tokens=12000)
        drafts = _extract_json(draft_raw)

        # ── Stage 3: review ──────────────────────────────────────────────────
        _update_job(job_id, status="review", progress="🧐 סבב שיפור ועריכה...")
        critic_input = (
            f"הבריף: {job['brief']}\n\nהתסריטים לשיפור:\n```json\n"
            + json.dumps(drafts, ensure_ascii=False)
            + "\n```\nשפר כל תסריט ושמור על אותו פורמט JSON בדיוק."
        )
        try:
            final_raw = await claude(MODEL_CRITIC, CRITIC_SYSTEM, critic_input, max_tokens=12000)
            final = _extract_json(final_raw)
            if not final.get("scripts"):
                final = drafts
        except Exception:
            final = drafts  # critic failure shouldn't lose the drafts

        result = {"research": research, "scripts": final.get("scripts", []), "model": MODEL_WRITER}
        _update_job(job_id, status="done", progress="✅ מוכן",
                    result_json=json.dumps(result, ensure_ascii=False))
        log.info(f"copywriter job {job_id} done ({len(result['scripts'])} scripts)")
    except Exception as e:
        log.exception(f"copywriter job {job_id} failed")
        _update_job(job_id, status="error", error=str(e)[:500], progress="❌ שגיאה")


# ── Job endpoints ─────────────────────────────────────────────────────────────

class CreateJobBody(BaseModel):
    brief: str
    link: Optional[str] = None
    count: Optional[int] = 1
    video_type: Optional[str] = None
    duration: Optional[str] = None


@router.post("/copywriter/jobs", status_code=201)
async def create_job(body: CreateJobBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    if not body.brief or len(body.brief.strip()) < 5:
        raise HTTPException(status_code=400, detail="בריף קצר מדי")
    today = datetime.now(timezone.utc).date().isoformat()
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM agent_jobs WHERE created_at LIKE ?",
                         (today + "%",)).fetchone()["c"]
    if n >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="חריגה ממכסת המשימות היומית")
    job_id = uuid.uuid4().hex[:12]
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_jobs(id,kind,brief,link,params_json,status,progress,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, "copywriter", body.brief.strip(), (body.link or "").strip() or None,
             json.dumps({"count": body.count, "video_type": body.video_type,
                         "duration": body.duration}, ensure_ascii=False),
             "queued", "⏳ בתור...", now_iso(), now_iso()))
    asyncio.create_task(run_copywriter_job(job_id))
    return {"id": job_id, "status": "queued"}


@router.get("/copywriter/jobs")
def list_jobs(limit: int = 25, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, brief, link, status, progress, error, created_at, updated_at "
            "FROM agent_jobs WHERE kind='copywriter' ORDER BY created_at DESC LIMIT ?",
            (min(limit, 100),)).fetchall()
    return [dict(r) for r in rows]


@router.get("/copywriter/jobs/{job_id}")
def get_job(job_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("result_json"):
        job["result"] = json.loads(job["result_json"])
    job.pop("result_json", None)
    return job


# ── Style endpoints ───────────────────────────────────────────────────────────

class StyleDocBody(BaseModel):
    title: str
    content: str


@router.get("/style/docs")
def list_style_docs(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, source, drive_file_id, LENGTH(content) chars, created_at "
            "FROM agent_styledocs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/style/docs", status_code=201)
def add_style_doc(body: StyleDocBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    doc_id = uuid.uuid4().hex[:12]
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_styledocs(id,title,content,source,created_at) VALUES(?,?,?,?,?)",
            (doc_id, body.title.strip(), body.content.strip(), "manual", now_iso()))
    return {"id": doc_id}


@router.delete("/style/docs/{doc_id}")
def delete_style_doc(doc_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM agent_styledocs WHERE id=?", (doc_id,))
    return {"ok": True}


class SyncDriveBody(BaseModel):
    folder_id: str


@router.post("/style/sync-drive")
async def sync_drive(body: SyncDriveBody, x_team_token: Optional[str] = Header(None)):
    """Pull every Google Doc in the folder (must be shared with the service account)."""
    require_team(x_team_token)
    from main import get_drive_token  # deferred import to avoid circularity
    token = get_drive_token()
    headers = {"Authorization": f"Bearer {token}"}
    imported, skipped = 0, 0
    async with httpx.AsyncClient(timeout=60) as client:
        page_token = None
        files = []
        while True:
            params = {
                "q": f"'{body.folder_id}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
                "fields": "nextPageToken, files(id,name)",
                "pageSize": 100,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            r = await client.get("https://www.googleapis.com/drive/v3/files",
                                 headers=headers, params=params)
            if r.status_code != 200:
                raise HTTPException(status_code=502,
                                    detail=f"Drive list error {r.status_code}: {r.text[:200]}")
            data = r.json()
            files += data.get("files", [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        if not files:
            raise HTTPException(status_code=404,
                                detail="לא נמצאו מסמכי Google Docs בתיקייה — ודא ששיתפת אותה עם חשבון השירות")
        for f in files:
            with db.get_conn() as conn:
                exists = conn.execute("SELECT 1 FROM agent_styledocs WHERE drive_file_id=?",
                                      (f["id"],)).fetchone()
            if exists:
                skipped += 1
                continue
            er = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{f['id']}/export",
                headers=headers, params={"mimeType": "text/plain"})
            if er.status_code != 200:
                skipped += 1
                continue
            content = er.text.strip()
            if len(content) < 100:
                skipped += 1
                continue
            with db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO agent_styledocs(id,title,content,source,drive_file_id,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], f["name"], content[:20000], "drive", f["id"], now_iso()))
            imported += 1
    # rebuild the style profile in the background if we got new material
    if imported:
        asyncio.create_task(_rebuild_profile())
    return {"imported": imported, "skipped": skipped, "total_in_folder": len(files)}


async def _rebuild_profile():
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT title, content FROM agent_styledocs ORDER BY RANDOM() LIMIT 12").fetchall()
        if not rows:
            return
        sample = "\n\n---\n\n".join(f"### {r['title']}\n{r['content'][:2500]}" for r in rows)
        prompt = (
            "לפניך מדגם מתסריטים שכתב עמית, הבעלים של חברת הפקות וידאו. "
            "נתח אותם והפק 'פרופיל סגנון' תמציתי (עד 400 מילים) שקופירייטר אחר יוכל "
            "להשתמש בו כדי לכתוב בדיוק באותו סגנון: מבנה אופייני, אורך משפטים, סלנג והעדפות "
            "לשוניות, סוגי הוקים, איך נראית קריאה לפעולה, הוראות בימוי, ומה הוא אף פעם לא עושה.\n\n"
            + sample
        )
        profile = await claude(MODEL_RESEARCH, RESEARCH_SYSTEM, prompt, max_tokens=2000)
        _meta_set("style_profile", profile)
        _meta_set("style_profile_updated", now_iso())
        log.info("style profile rebuilt")
    except Exception:
        log.exception("style profile rebuild failed")


@router.get("/style/profile")
def get_profile(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    return {
        "profile": _meta_get("style_profile") or DEFAULT_STYLE,
        "is_default": _meta_get("style_profile") is None,
        "updated": _meta_get("style_profile_updated"),
    }


@router.post("/style/profile/rebuild")
async def rebuild_profile(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    await _rebuild_profile()
    return {"ok": True}
