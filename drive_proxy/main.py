"""
TING Review — Main FastAPI Application
=========================================
Replaces server.py. Includes:
  • /api/video/{id}      — Drive streaming proxy (original)
  • /api/team/...        — Team management API
  • /api/r/{token}/...   — Client API (no login)
  • /r/{token}           — Client review page
  • /api/health          — Health check

Run: uvicorn main:app --host 127.0.0.1 --port 8001
"""

import os
import re
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests as http

import db
from signing import verify_signed_url
from routes_team import router as team_router
from routes_client import router as client_router
from routes_agents import router as agents_router
from routes_cs import router as cs_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ting")

# ── Config ────────────────────────────────────────────────────────────────────
CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "/etc/ting-drive/service-account.json"
)
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", ",".join([
    "https://crm.tingil.co",
    "https://ting-media-finance.web.app",
    "http://localhost:7788",
    "http://localhost:5000",
    "http://localhost:8001",
])).split(",")

CHUNK_SIZE = 512 * 1024

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TING Review", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Range", "Content-Type", "Authorization", "X-Team-Token"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges", "Content-Type"],
    allow_credentials=True,
)

# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    db.init_db()
    log.info(f"DB initialised at {db.DB_PATH}")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(team_router)
app.include_router(client_router)
app.include_router(agents_router)
app.include_router(cs_router)

# ── Drive credential cache ─────────────────────────────────────────────────────
_creds = None

def get_drive_token() -> str:
    global _creds
    if _creds is None:
        if not os.path.exists(CREDENTIALS_FILE):
            raise RuntimeError(f"Service account key not found at {CREDENTIALS_FILE}")
        _creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
    if not _creds.valid:
        _creds.refresh(GoogleAuthRequest())
    return _creds.token


def drive_get(url: str, **kwargs):
    token = get_drive_token()
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(kwargs.pop("headers", {}))
    return http.get(url, headers=headers, **kwargs)


DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"
DRIVE_MEDIA_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"


# ── Video streaming ───────────────────────────────────────────────────────────

@app.get("/api/video/{file_id}")
async def stream_video(file_id: str, request: Request,
                       exp: str = None, sig: str = None):
    """
    Stream a Drive video. Requires HMAC signature (exp + sig params).
    Falls back to unsigned for internal/team use if no sig is present.
    """
    # Validate file_id format
    if not re.match(r'^[a-zA-Z0-9_\-]{10,}$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID")

    # Verify signature if provided
    if sig or exp:
        if not verify_signed_url(file_id, exp, sig):
            raise HTTPException(status_code=403, detail="Expired or invalid video link")

    # Fetch file metadata
    try:
        meta_resp = drive_get(
            DRIVE_FILES_URL.format(file_id=file_id),
            params={"fields": "name,mimeType,size,id"}
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if meta_resp.status_code in (404, 403):
        # SA doesn't have access — try public Drive download fallback
        # (works for files set to "anyone with link can view")
        log.info(f"SA access denied ({meta_resp.status_code}) for {file_id} — trying public fallback")
        return await _stream_public_drive(file_id, request)
    if meta_resp.status_code != 200:
        raise HTTPException(status_code=meta_resp.status_code, detail="Drive API error")

    meta      = meta_resp.json()
    mime_type = meta.get("mimeType", "video/mp4")
    file_size = int(meta.get("size", 0))
    file_name = meta.get("name", "video")

    log.info(f"Streaming: {file_name} ({file_size // 1024 // 1024} MB)")

    # Forward Range header
    media_url    = DRIVE_MEDIA_URL.format(file_id=file_id)
    extra_headers = {}
    range_header  = request.headers.get("Range")
    if range_header:
        extra_headers["Range"] = range_header

    drive_resp = drive_get(media_url, headers=extra_headers, stream=True)

    # Google large-file confirmation
    if drive_resp.status_code == 200 and "content-disposition" not in drive_resp.headers:
        confirm_token = _extract_confirm_token(drive_resp)
        if confirm_token:
            drive_resp.close()
            drive_resp = drive_get(
                media_url + f"&confirm={confirm_token}",
                headers=extra_headers, stream=True
            )

    if drive_resp.status_code not in (200, 206):
        raise HTTPException(status_code=drive_resp.status_code, detail="Drive stream error")

    resp_headers = {"Accept-Ranges": "bytes",
                    "Content-Disposition": f'inline; filename="{file_name}"'}
    for h in ("Content-Range", "Content-Length", "Content-Type"):
        if h in drive_resp.headers:
            resp_headers[h] = drive_resp.headers[h]
    if "Content-Type" not in resp_headers:
        resp_headers["Content-Type"] = mime_type
    if "Content-Length" not in resp_headers and file_size:
        resp_headers["Content-Length"] = str(file_size)

    def generate():
        try:
            for chunk in drive_resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    yield chunk
        finally:
            drive_resp.close()

    return StreamingResponse(
        generate(),
        status_code=drive_resp.status_code,
        headers=resp_headers,
        media_type=mime_type,
    )


@app.head("/api/video/{file_id}")
async def head_video(file_id: str):
    if not re.match(r'^[a-zA-Z0-9_\-]{10,}$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID")
    meta_resp = drive_get(
        DRIVE_FILES_URL.format(file_id=file_id),
        params={"fields": "name,mimeType,size"}
    )
    if meta_resp.status_code != 200:
        raise HTTPException(status_code=meta_resp.status_code)
    meta = meta_resp.json()
    return JSONResponse(status_code=200, headers={
        "Content-Type":   meta.get("mimeType", "video/mp4"),
        "Content-Length": str(meta.get("size", 0)),
        "Accept-Ranges":  "bytes",
    }, content={})


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    try:
        get_drive_token()
        return {"status": "ok", "drive": "connected", "db": db.DB_PATH}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_confirm_token(response) -> str | None:
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value
    return None


async def _stream_public_drive(file_id: str, request: Request):
    """
    Fallback: proxy a publicly-shared Drive file (anyone with link can view).
    Used when the Service Account doesn't have access to the file.
    """
    range_header = request.headers.get("Range")
    req_headers = {"User-Agent": "Mozilla/5.0 (compatible; TING-Review/1.0)"}
    if range_header:
        req_headers["Range"] = range_header

    # drive.usercontent.google.com is Google's newer, more reliable public download domain
    pub_url = (
        f"https://drive.usercontent.google.com/download"
        f"?id={file_id}&export=download&confirm=t&authuser=0"
    )

    try:
        resp = http.get(pub_url, stream=True, allow_redirects=True, timeout=30, headers=req_headers)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"שגיאת רשת: {e}")

    ct = resp.headers.get("Content-Type", "")

    # Google may return an HTML warning page for large files — extract confirm token
    if "text/html" in ct and resp.status_code == 200:
        html_bytes = b""
        for chunk in resp.iter_content(4096):
            html_bytes += chunk
            if len(html_bytes) >= 65536:
                break
        resp.close()

        m = re.search(rb'confirm=([0-9A-Za-z_\-]+)', html_bytes)
        if not m:
            raise HTTPException(
                status_code=404,
                detail="הקובץ לא נגיש — שתף אותו כ'כל מי שיש לו קישור'"
            )
        confirm = m.group(1).decode()
        retry_url = (
            f"https://drive.usercontent.google.com/download"
            f"?id={file_id}&export=download&confirm={confirm}"
        )
        try:
            resp = http.get(retry_url, stream=True, allow_redirects=True, timeout=30, headers=req_headers)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"שגיאת רשת: {e}")
        ct = resp.headers.get("Content-Type", "")

    if resp.status_code not in (200, 206):
        resp.close()
        raise HTTPException(
            status_code=404,
            detail="הקובץ לא נגיש — שתף אותו כ'כל מי שיש לו קישור'"
        )

    # Build response headers
    resp_headers = {"Accept-Ranges": "bytes"}
    for h in ("Content-Range", "Content-Length", "Content-Disposition", "Content-Type"):
        if h in resp.headers:
            resp_headers[h] = resp.headers[h]
    mime = resp_headers.get("Content-Type", "video/mp4")
    if "text/html" in mime:
        mime = "video/mp4"
        resp_headers["Content-Type"] = mime

    log.info(f"Public Drive fallback streaming: {file_id} ({ct})")

    def gen():
        try:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    yield chunk
        finally:
            resp.close()

    return StreamingResponse(
        gen(),
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=mime,
    )
