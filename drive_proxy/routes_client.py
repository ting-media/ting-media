"""
TING Review — Client API Routes
==================================
Token-authenticated. No login required. Clients get a link.
"""

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import db
import signing

log = logging.getLogger("ting-client")

router = APIRouter(tags=["client"])

# ── SSE broker ───────────────────────────────────────────────────────────────
# Maps review_id → list of asyncio.Queue objects (one per connected client)
_sse_subscribers: dict[str, list[asyncio.Queue]] = {}


def _push_event(review_id: str, event: dict):
    """Push a JSON event to all SSE subscribers for this review."""
    if review_id not in _sse_subscribers:
        return
    payload = json.dumps(event)
    dead = []
    for q in _sse_subscribers[review_id]:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_subscribers[review_id].remove(q)


# ── Pydantic ──────────────────────────────────────────────────────────────────

class AddCommentBody(BaseModel):
    timecode:        float
    text:            str
    author_name:     str
    annotation_json: Optional[str] = None
    parent_id:       Optional[str] = None
    version_id:      Optional[str] = None

class ApproveBody(BaseModel):
    note:            Optional[str] = None
    approved_by_name: str = "לקוח"


# ── Token helpers ──────────────────────────────────────────────────────────────

def _get_token_or_403(token: str) -> dict:
    t = db.validate_token(token)
    if not t:
        raise HTTPException(status_code=403, detail="לינק לא תקף או פג תוקף")
    return t


# ── Client page ───────────────────────────────────────────────────────────────

@router.get("/r/{token}", response_class=HTMLResponse)
async def client_page(token: str, request: Request):
    """Serve the client review page."""
    _get_token_or_403(token)
    # Serve static review.html
    import os
    html_path = os.path.join(os.path.dirname(__file__), "static", "review.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="review.html not found")
    with open(html_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ── Review data ───────────────────────────────────────────────────────────────

@router.get("/api/r/{token}")
def get_review_data(token: str, request: Request):
    """
    Returns review metadata + signed video URL for the current version.
    This is the first call the client page makes.
    """
    t = _get_token_or_403(token)
    review = db.get_review(t["review_id"])
    if not review:
        raise HTTPException(status_code=404, detail="סקירה לא נמצאה")

    versions = db.list_versions(t["review_id"])
    current_version = db.get_current_version(t["review_id"])

    # Build signed video URL
    base = str(request.base_url).rstrip("/")
    signed_video_url = None
    if current_version and current_version.get("drive_file_id"):
        signed_video_url = signing.sign_video_url(
            current_version["drive_file_id"], base
        )

    return {
        "review": {
            "id":              review["id"],
            "title":           review["title"],
            "status":          review["status"],
            "current_version": review["current_version"],
            "current_round":   review["current_round"],
        },
        "versions": [
            {
                "id":             v["id"],
                "version_number": v["version_number"],
                "round":          v["round"],
                "file_name":      v["file_name"],
                "note":           v["note"],
                "uploaded_at":    v["uploaded_at"],
                "is_current":     v["version_number"] == review["current_version"],
            }
            for v in versions
        ],
        "video_url":        signed_video_url,
        "current_version":  current_version,
        "permissions":      t["permissions"],
        "client_name":      t["client_name"],
    }


# ── Comments ──────────────────────────────────────────────────────────────────

@router.get("/api/r/{token}/comments")
def get_comments(token: str, version_id: Optional[str] = None):
    t = _get_token_or_403(token)
    comments = db.list_comments(t["review_id"], version_id=version_id)
    return comments


@router.post("/api/r/{token}/comments", status_code=201)
def add_comment(token: str, body: AddCommentBody, request: Request):
    t = _get_token_or_403(token)

    if t["permissions"] not in ("comment", "approve"):
        raise HTTPException(status_code=403, detail="אין הרשאת הוספת הערות")

    review = db.get_review(t["review_id"])
    if not review:
        raise HTTPException(status_code=404)

    # Resolve version
    version_id = body.version_id
    if not version_id:
        cv = db.get_current_version(t["review_id"])
        version_id = cv["id"] if cv else None

    comment = db.add_comment(
        review_id=t["review_id"],
        timecode=body.timecode,
        text=body.text,
        author_name=body.author_name,
        author_type="client",
        version_id=version_id,
        round_num=review.get("current_round", 1),
        parent_id=body.parent_id,
        annotation_json=body.annotation_json,
    )

    # Push via SSE to everyone watching this review
    _push_event(t["review_id"], {"type": "new_comment", "comment": comment})

    return comment


# ── Approve ───────────────────────────────────────────────────────────────────

@router.post("/api/r/{token}/approve", status_code=201)
def approve(token: str, body: ApproveBody):
    t = _get_token_or_403(token)

    if t["permissions"] != "approve":
        raise HTTPException(status_code=403, detail="אין הרשאת אישור")

    cv = db.get_current_version(t["review_id"])
    if not cv:
        raise HTTPException(status_code=404, detail="אין גרסה לאשר")

    approval = db.add_approval(
        review_id=t["review_id"],
        version_id=cv["id"],
        approved_by_token=token,
        approved_by_name=body.approved_by_name or (t.get("client_name") or "לקוח"),
        note=body.note,
    )
    _push_event(t["review_id"], {"type": "approved", "approval": approval})
    return approval


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/api/r/{token}/stream")
async def sse_stream(token: str, request: Request):
    """
    Server-Sent Events — pushes new comments and approvals in real time.
    Client JS: const ev = new EventSource('/api/r/{token}/stream')
    """
    t = _get_token_or_403(token)
    review_id = t["review_id"]

    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_subscribers.setdefault(review_id, []).append(q)

    async def event_generator():
        try:
            # Send initial ping so browser knows connection is alive
            yield "event: ping\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive heartbeat every 25s
                    yield ": heartbeat\n\n"
        finally:
            if review_id in _sse_subscribers:
                try:
                    _sse_subscribers[review_id].remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering for SSE
        },
    )
