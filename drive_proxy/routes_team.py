"""
TING Review — Team API Routes
================================
All endpoints require session auth (X-Team-Token header).
"""

import os
import logging
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional
import db

log = logging.getLogger("ting-team")

router = APIRouter(prefix="/api/team", tags=["team"])

TEAM_SECRET = os.environ.get("TING_TEAM_SECRET", "team-secret-change-me")


# ── Auth ──────────────────────────────────────────────────────────────────────

def require_team(x_team_token: Optional[str] = Header(None)):
    if x_team_token != TEAM_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ── Pydantic ──────────────────────────────────────────────────────────────────

class CreateReviewBody(BaseModel):
    title: str
    client_id: Optional[str] = None
    task_id:   Optional[str] = None
    created_by: str = "team"

class AddVersionBody(BaseModel):
    drive_file_id: str
    file_name:     Optional[str] = None
    duration:      Optional[float] = None
    note:          Optional[str] = None
    uploaded_by:   str = "team"

class ShareBody(BaseModel):
    client_name:  Optional[str] = None
    client_email: Optional[str] = None
    permissions:  str = "comment"
    expires_at:   Optional[str] = None   # ISO8601 or null

class PatchCommentBody(BaseModel):
    resolved: Optional[bool] = None

class AddTeamCommentBody(BaseModel):
    timecode:        float
    text:            str
    author_name:     str = "צוות"
    author_type:     str = "team"
    parent_id:       Optional[str] = None
    annotation_json: Optional[str] = None
    version_id:      Optional[str] = None


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/reviews")
def list_reviews(x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    reviews = db.list_reviews()
    # Enrich each review with latest version info
    result = []
    for r in reviews:
        versions = db.list_versions(r["id"])
        tokens = db.list_tokens(r["id"])
        r["versions"] = versions
        r["token_count"] = len([t for t in tokens if not t["revoked"]])
        result.append(r)
    return result


@router.post("/reviews", status_code=201)
def create_review(body: CreateReviewBody, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    review = db.create_review(
        title=body.title,
        created_by=body.created_by,
        client_id=body.client_id,
        task_id=body.task_id,
    )
    return review


@router.get("/reviews/{review_id}")
def get_review(review_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    review = db.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    review["versions"] = db.list_versions(review_id)
    review["tokens"]   = db.list_tokens(review_id)
    review["comments"] = db.list_comments(review_id)
    return review


@router.post("/reviews/{review_id}/versions", status_code=201)
def add_version(review_id: str, body: AddVersionBody,
                x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    review = db.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    version = db.add_version(
        review_id=review_id,
        drive_file_id=body.drive_file_id,
        uploaded_by=body.uploaded_by,
        file_name=body.file_name,
        duration=body.duration,
        note=body.note,
    )
    return version


@router.post("/reviews/{review_id}/share", status_code=201)
def share_review(review_id: str, body: ShareBody, request: Request,
                 x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    review = db.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    token = db.create_token(
        review_id=review_id,
        client_name=body.client_name,
        client_email=body.client_email,
        permissions=body.permissions,
        expires_at=body.expires_at,
    )
    base = str(request.base_url).rstrip("/")
    return {
        "token": token,
        "url": f"{base}/r/{token}",
        "review_id": review_id,
        "client_name": body.client_name,
    }


@router.delete("/reviews/{review_id}/tokens/{token}")
def revoke_token(review_id: str, token: str,
                 x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    db.revoke_token(token)
    return {"ok": True}


# ── Comments (team management) ────────────────────────────────────────────────

@router.get("/reviews/{review_id}/comments")
def get_comments(review_id: str, version_id: Optional[str] = None,
                 x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    return db.list_comments(review_id, version_id=version_id)


@router.post("/reviews/{review_id}/comments", status_code=201)
def add_team_comment(review_id: str, body: AddTeamCommentBody,
                     x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    review = db.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    # Resolve current version if not specified
    version_id = body.version_id
    if not version_id:
        cv = db.get_current_version(review_id)
        version_id = cv["id"] if cv else None
    return db.add_comment(
        review_id=review_id,
        timecode=body.timecode,
        text=body.text,
        author_name=body.author_name,
        author_type=body.author_type,
        version_id=version_id,
        round_num=review.get("current_round", 1),
        parent_id=body.parent_id,
        annotation_json=body.annotation_json,
    )


@router.patch("/comments/{comment_id}")
def patch_comment(comment_id: str, body: PatchCommentBody,
                  x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    if body.resolved is not None:
        db.resolve_comment(comment_id, body.resolved)
    return db.get_comment(comment_id)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, x_team_token: Optional[str] = Header(None)):
    require_team(x_team_token)
    db.delete_comment(comment_id)
    return {"ok": True}
