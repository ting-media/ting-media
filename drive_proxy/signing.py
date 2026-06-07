"""
TING Review — Signed Video URL
================================
HMAC-based short-lived URLs so file_id is never a permanent public handle.
"""

import hmac
import hashlib
import time
import os

SIGNING_SECRET = os.environ.get("TING_SIGNING_SECRET", "change-me-in-production-please")
VIDEO_URL_TTL  = int(os.environ.get("TING_VIDEO_URL_TTL", "3600"))  # 1 hour default


def sign_video_url(file_id: str, base_url: str) -> str:
    """
    Build a signed URL:
      /api/video/{file_id}?exp={unix_ts}&sig={hmac}
    """
    exp = int(time.time()) + VIDEO_URL_TTL
    msg = f"{file_id}:{exp}"
    sig = hmac.new(SIGNING_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{base_url}/api/video/{file_id}?exp={exp}&sig={sig}"


def verify_signed_url(file_id: str, exp: str, sig: str) -> bool:
    """Return True if signature is valid and not expired."""
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        return False
    if time.time() > exp_int:
        return False
    msg = f"{file_id}:{exp_int}"
    expected = hmac.new(SIGNING_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, sig)
