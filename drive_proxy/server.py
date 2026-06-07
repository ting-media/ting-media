"""
TING MEDIA — Drive Video Proxy Server
======================================
Streams Google Drive videos server-side via a Service Account.
End users (clients, editors, AMs) never see an OAuth prompt.

Usage: uvicorn server:app --host 127.0.0.1 --port 8001
"""

import os
import re
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests as http

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ting-proxy")

# ── Config ───────────────────────────────────────────────────────────────────
CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "/etc/ting-drive/service-account.json"
)
ALLOWED_ORIGINS = [
    "https://crm.tingil.co",
    "https://ting-media-finance.web.app",
    "http://localhost:7788",
    "http://localhost:5000",
]
CHUNK_SIZE = 512 * 1024  # 512 KB per chunk

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TING Drive Proxy", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Range", "Content-Type", "Authorization"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges", "Content-Type"],
)

# ── Service Account credential cache ─────────────────────────────────────────
_creds = None

def get_token() -> str:
    """Return a valid access token, refreshing if needed."""
    global _creds
    if _creds is None:
        if not os.path.exists(CREDENTIALS_FILE):
            raise RuntimeError(
                f"Service account key not found at {CREDENTIALS_FILE}. "
                "Run setup.sh first."
            )
        _creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
    if not _creds.valid:
        _creds.refresh(GoogleAuthRequest())
    return _creds.token


# ── Drive helpers ─────────────────────────────────────────────────────────────
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"
DRIVE_MEDIA_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

def drive_get(url: str, **kwargs):
    """GET request to Drive API with auto-auth."""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(kwargs.pop("headers", {}))
    return http.get(url, headers=headers, **kwargs)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Quick liveness check."""
    try:
        get_token()   # will raise if credentials missing
        return {"status": "ok", "drive": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.get("/api/video/{file_id}")
async def stream_video(file_id: str, request: Request):
    """
    Stream a Google Drive video to the browser.
    Supports HTTP Range requests (required for video seeking / timeline).
    """
    # Validate file_id format (alphanumeric + hyphens/underscores)
    if not re.match(r'^[a-zA-Z0-9_\-]{10,}$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID")

    # ── 1. Fetch file metadata ────────────────────────────────────────────────
    meta_resp = drive_get(
        DRIVE_FILES_URL.format(file_id=file_id),
        params={"fields": "name,mimeType,size,id"}
    )
    if meta_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="קובץ לא נמצא ב-Drive")
    if meta_resp.status_code == 403:
        raise HTTPException(
            status_code=403,
            detail="גישה נדחתה — ודא ששיתפת את הקובץ/תיקייה עם כתובת ה-Service Account"
        )
    if meta_resp.status_code != 200:
        raise HTTPException(status_code=meta_resp.status_code, detail="Drive API error")

    meta = meta_resp.json()
    mime_type = meta.get("mimeType", "video/mp4")
    file_size = int(meta.get("size", 0))
    file_name = meta.get("name", "video")

    log.info(f"Serving: {file_name} ({file_size // 1024 // 1024} MB)")

    # ── 2. Build Drive media request (pass Range through if present) ──────────
    media_url = DRIVE_MEDIA_URL.format(file_id=file_id)
    extra_headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        extra_headers["Range"] = range_header

    drive_resp = drive_get(media_url, headers=extra_headers, stream=True)

    # Handle Google's large-file confirmation redirect
    if drive_resp.status_code == 200 and "content-disposition" not in drive_resp.headers:
        # Check for virus-scan confirmation (affects files > ~25 MB via browser,
        # but NOT the API endpoint — kept here as safety net)
        confirm_token = _extract_confirm_token(drive_resp)
        if confirm_token:
            drive_resp.close()
            drive_resp = drive_get(
                media_url + f"&confirm={confirm_token}",
                headers=extra_headers,
                stream=True
            )

    if drive_resp.status_code not in (200, 206):
        raise HTTPException(status_code=drive_resp.status_code, detail="Drive stream error")

    # ── 3. Build response headers ─────────────────────────────────────────────
    resp_headers = {
        "Accept-Ranges":       "bytes",
        "Content-Disposition": f'inline; filename="{file_name}"',
    }
    for h in ("Content-Range", "Content-Length", "Content-Type"):
        if h in drive_resp.headers:
            resp_headers[h] = drive_resp.headers[h]
    if "Content-Type" not in resp_headers:
        resp_headers["Content-Type"] = mime_type
    if "Content-Length" not in resp_headers and file_size:
        resp_headers["Content-Length"] = str(file_size)

    # ── 4. Stream chunks to client ────────────────────────────────────────────
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
    """HEAD request — lets the browser know size/type before streaming."""
    if not re.match(r'^[a-zA-Z0-9_\-]{10,}$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID")

    meta_resp = drive_get(
        DRIVE_FILES_URL.format(file_id=file_id),
        params={"fields": "name,mimeType,size"}
    )
    if meta_resp.status_code != 200:
        raise HTTPException(status_code=meta_resp.status_code)

    meta = meta_resp.json()
    return JSONResponse(
        status_code=200,
        headers={
            "Content-Type":   meta.get("mimeType", "video/mp4"),
            "Content-Length": str(meta.get("size", 0)),
            "Accept-Ranges":  "bytes",
        },
        content={}
    )


# ── Internal helpers ──────────────────────────────────────────────────────────
def _extract_confirm_token(response) -> str | None:
    """Extract Google's virus-scan confirmation token if present."""
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value
    return None
