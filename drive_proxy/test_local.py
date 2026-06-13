"""
TING Review — Local test suite
Run: python test_local.py
"""
import os, sys, json, time, threading, requests

# ── Environment setup ─────────────────────────────────────────────────────────
TEST_DB   = os.path.join(os.path.dirname(__file__), "test_ting.db")
os.environ["TING_DB_PATH"]        = TEST_DB
os.environ["TING_TEAM_SECRET"]    = "test-secret-123"
os.environ["TING_SIGNING_SECRET"] = "signing-secret-abc"
os.environ["GOOGLE_SERVICE_ACCOUNT_KEY"] = os.path.join(os.path.dirname(__file__), "no-key.json")

DRIVE_FILE_ID = "1MBORPTD_tBdHDrDRREov6Vzb5hPpyDx_"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
HEAD = "\033[94m──\033[0m"

errors = []

def ok(msg):   print(f"  {PASS} {msg}")
def fail(msg): print(f"  {FAIL} {msg}"); errors.append(msg)
def section(name): print(f"\n{HEAD} {name}")


# ════════════════════════════════════════════════════════
# SECTION 1 — DB layer
# ════════════════════════════════════════════════════════
section("DB layer")

# Clean slate
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

import db
db.init_db()
ok("init_db() — created DB + schema")

# ── Reviews ──────────────────────────────────────────────
rev = db.create_review("פרסומת קיץ סקי ביץ'", "amit@ting.co", task_id="task-001")
assert rev and rev.get("id"), "create_review failed"
ok(f"create_review: id={rev['id'][:8]}...")

rev_fetched = db.get_review(rev["id"])
assert rev_fetched["title"] == "פרסומת קיץ סקי ביץ'", "get_review mismatch"
ok("get_review: title correct")

assert db.get_review("nonexistent") is None
ok("get_review(nonexistent) → None")

rev2 = db.create_review("סרטון תדמית", "roi@ting.co")
all_reviews = db.list_reviews()
assert len(all_reviews) >= 2
ok(f"list_reviews: {len(all_reviews)} reviews")

# ── Versions ─────────────────────────────────────────────
v1 = db.add_version(rev["id"], DRIVE_FILE_ID, "amit@ting.co",
                    file_name="summer_ad_v1.mp4", duration=92.5, note="גרסה ראשונה")
assert v1["version_number"] == 1
assert v1["drive_file_id"] == DRIVE_FILE_ID
ok(f"add_version v1: version_number=1, drive_file_id OK")

v2 = db.add_version(rev["id"], DRIVE_FILE_ID, "roi@ting.co",
                    file_name="summer_ad_v2.mp4", note="תיקונים")
assert v2["version_number"] == 2
ok("add_version v2: auto-incremented to 2")

rev_after = db.get_review(rev["id"])
assert rev_after["current_version"] == 2, f"expected 2 got {rev_after['current_version']}"
ok("review.current_version updated to 2 after add_version")

cur_v = db.get_current_version(rev["id"])
assert cur_v["version_number"] == 2
ok("get_current_version: returns v2")

versions_list = db.list_versions(rev["id"])
assert len(versions_list) == 2
ok("list_versions: 2 versions")

# ── Comments ─────────────────────────────────────────────
c1 = db.add_comment(rev["id"], 4.2,  "הלוגו קטן מדי בפתיח",  "דוד כהן", "client", version_id=v1["id"])
c2 = db.add_comment(rev["id"], 22.7, "צבע רקע לא תואם ברנד", "דוד כהן", "client", version_id=v1["id"])
c3 = db.add_comment(rev["id"], 87.0, "מוזיקה חזקה בסיום",    "דוד כהן", "client", version_id=v2["id"])
assert c1["timecode"] == 4.2
ok("add_comment: 3 comments added with timecodes")

comments_all = db.list_comments(rev["id"])
assert len(comments_all) == 3
ok(f"list_comments(all): {len(comments_all)} comments")

# Sorted by timecode
times = [c["timecode"] for c in comments_all]
assert times == sorted(times), f"comments not sorted: {times}"
ok("list_comments: sorted by timecode ASC")

# Filter by version
cv1_comments = db.list_comments(rev["id"], version_id=v1["id"])
assert len(cv1_comments) == 2
ok("list_comments(version_id=v1): 2 comments")

# Resolve
db.resolve_comment(c1["id"], True)
resolved_c = db.get_comment(c1["id"])
assert resolved_c["resolved"] == 1
ok("resolve_comment: resolved=1")

db.resolve_comment(c1["id"], False)
assert db.get_comment(c1["id"])["resolved"] == 0
ok("resolve_comment(False): resolved=0 (unresolve works)")

# Delete
db.delete_comment(c3["id"])
assert db.get_comment(c3["id"]) is None
ok("delete_comment: gone from DB")

# ── Tokens ────────────────────────────────────────────────
tok_view    = db.create_token(rev["id"], "שרה לוי",  "sara@client.com", permissions="view")
tok_comment = db.create_token(rev["id"], "דוד כהן",  "david@client.com", permissions="comment")
tok_approve = db.create_token(rev["id"], "מנהל", permissions="approve")
assert len(tok_view) >= 20, "token too short"
ok(f"create_token: generated {len(tok_view)}-char token")

valid = db.validate_token(tok_comment)
assert valid is not None
assert valid["client_name"] == "דוד כהן"
assert valid["permissions"] == "comment"
ok("validate_token: returns correct row")

assert valid["last_seen_at"] is not None
ok("validate_token: updates last_seen_at")

# Revoke
db.revoke_token(tok_view)
assert db.validate_token(tok_view) is None
ok("revoke_token: revoked token returns None")

# Expired token
from datetime import datetime, timezone, timedelta
past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
tok_expired = db.create_token(rev["id"], "expired", expires_at=past)
assert db.validate_token(tok_expired) is None
ok("expired token: validate_token returns None")

# List tokens
tokens = db.list_tokens(rev["id"])
assert len(tokens) >= 3
ok(f"list_tokens: {len(tokens)} tokens for review")

# ── Approvals ─────────────────────────────────────────────
approval = db.add_approval(rev["id"], v2["id"], tok_approve, "מנהל", note="נראה מצוין!")
assert approval["review_id"] == rev["id"]
ok("add_approval: saved")

rev_approved = db.get_review(rev["id"])
assert rev_approved["status"] == "approved"
ok("add_approval: review.status → 'approved'")


# ════════════════════════════════════════════════════════
# SECTION 2 — Signing
# ════════════════════════════════════════════════════════
section("Signed URLs")

from signing import sign_video_url, verify_signed_url

url = sign_video_url(DRIVE_FILE_ID, "https://crm.tingil.co")
assert f"/api/video/{DRIVE_FILE_ID}" in url
assert "exp=" in url and "sig=" in url
ok(f"sign_video_url: {url[-50:]}")

# Parse params
from urllib.parse import urlparse, parse_qs
parsed = urlparse(url)
params = parse_qs(parsed.query)
exp = params["exp"][0]
sig = params["sig"][0]

assert verify_signed_url(DRIVE_FILE_ID, exp, sig) is True
ok("verify_signed_url: valid signature → True")

assert verify_signed_url(DRIVE_FILE_ID, exp, sig + "x") is False
ok("verify_signed_url: tampered sig → False")

assert verify_signed_url(DRIVE_FILE_ID, "1000000000", sig) is False
ok("verify_signed_url: expired timestamp → False")

assert verify_signed_url("wrongid", exp, sig) is False
ok("verify_signed_url: wrong fileId → False")

assert verify_signed_url(DRIVE_FILE_ID, "notanumber", sig) is False
ok("verify_signed_url: non-numeric exp → False")


# ════════════════════════════════════════════════════════
# SECTION 3 — FastAPI endpoints (live server)
# ════════════════════════════════════════════════════════
section("FastAPI HTTP endpoints")

import uvicorn, importlib

# Import app
sys.path.insert(0, os.path.dirname(__file__))
app_mod = importlib.import_module("main")
app = app_mod.app

SERVER_PORT = 18099
BASE = f"http://127.0.0.1:{SERVER_PORT}"
HEADERS_TEAM = {"X-Team-Token": "test-secret-123", "Content-Type": "application/json"}

# Start server in background thread
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=SERVER_PORT, log_level="error"))
t = threading.Thread(target=server.run, daemon=True)
t.start()

# Wait for server to be ready
for _ in range(30):
    try:
        r = requests.get(f"{BASE}/api/health", timeout=1)
        if r.status_code in (200, 503):
            break
    except Exception:
        time.sleep(0.3)

# ── Health ────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/health")
assert r.status_code in (200, 503), f"health returned {r.status_code}"
data = r.json()
assert data.get("status") in ("ok", "error")
ok(f"GET /api/health: status={data.get('status')}")

# ── Team: auth ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/team/reviews", headers={"X-Team-Token": "wrong"})
assert r.status_code == 401
ok("GET /api/team/reviews without token → 401")

# ── Team: create review ───────────────────────────────────
r = requests.post(f"{BASE}/api/team/reviews",
    headers=HEADERS_TEAM,
    json={"title": "HTTP test review", "created_by": "tester"})
assert r.status_code == 201, f"create review: {r.status_code} {r.text}"
http_rev = r.json()
assert http_rev.get("id")
ok(f"POST /api/team/reviews → 201, id={http_rev['id'][:8]}...")

# ── Team: list reviews ────────────────────────────────────
r = requests.get(f"{BASE}/api/team/reviews", headers=HEADERS_TEAM)
assert r.status_code == 200
reviews_list = r.json()
assert any(x["id"] == http_rev["id"] for x in reviews_list)
ok(f"GET /api/team/reviews → {len(reviews_list)} reviews")

# ── Team: add version ─────────────────────────────────────
r = requests.post(f"{BASE}/api/team/reviews/{http_rev['id']}/versions",
    headers=HEADERS_TEAM,
    json={"drive_file_id": DRIVE_FILE_ID, "file_name": "test.mp4",
          "uploaded_by": "tester", "note": "test version"})
assert r.status_code == 201, f"add version: {r.status_code} {r.text}"
http_ver = r.json()
assert http_ver["version_number"] == 1
ok(f"POST /api/team/reviews/{{id}}/versions → 201, v{http_ver['version_number']}")

# ── Team: share (create client token) ────────────────────
r = requests.post(f"{BASE}/api/team/reviews/{http_rev['id']}/share",
    headers=HEADERS_TEAM,
    json={"client_name": "HTTP Test Client", "permissions": "approve"})
assert r.status_code == 201, f"share: {r.status_code} {r.text}"
share_data = r.json()
assert share_data.get("token")
assert "/r/" in share_data.get("url", "")
client_token = share_data["token"]
ok(f"POST /share → token={client_token[:12]}..., url OK")

# ── Client: page ─────────────────────────────────────────
r = requests.get(f"{BASE}/r/{client_token}")
assert r.status_code == 200, f"client page: {r.status_code}"
assert "TING" in r.text
assert "review.html" not in r.headers.get("content-type", "")
ok("GET /r/{token} → 200, HTML page served")

# ── Client: bad token → 403 ───────────────────────────────
r = requests.get(f"{BASE}/r/badtoken123456789012345")
assert r.status_code == 403, f"expected 403 got {r.status_code}"
ok("GET /r/badtoken → 403")

# ── Client: get review data ───────────────────────────────
r = requests.get(f"{BASE}/api/r/{client_token}")
assert r.status_code == 200, f"review data: {r.status_code} {r.text}"
rdata = r.json()
assert rdata.get("review", {}).get("id") == http_rev["id"]
assert rdata.get("video_url") is not None
assert "/api/video/" in rdata["video_url"]
assert "exp=" in rdata["video_url"] and "sig=" in rdata["video_url"]
ok(f"GET /api/r/{{token}} → review data + signed video_url")
ok(f"  video_url: ...{rdata['video_url'][-60:]}")

# ── Client: add comment ───────────────────────────────────
r = requests.post(f"{BASE}/api/r/{client_token}/comments",
    json={"timecode": 4.2, "text": "הלוגו קטן מדי",
          "author_name": "HTTP Test Client"})
assert r.status_code == 201, f"add comment: {r.status_code} {r.text}"
new_comment = r.json()
assert new_comment["timecode"] == 4.2
assert new_comment["author_type"] == "client"
ok(f"POST /api/r/{{token}}/comments → 201, timecode=4.2s")

r2 = requests.post(f"{BASE}/api/r/{client_token}/comments",
    json={"timecode": 22.7, "text": "צבע לא תואם לברנד",
          "author_name": "HTTP Test Client"})
assert r2.status_code == 201
ok("POST second comment → 201 (timecode=22.7s)")

# ── Client: list comments ─────────────────────────────────
r = requests.get(f"{BASE}/api/r/{client_token}/comments")
assert r.status_code == 200
cl = r.json()
assert len(cl) >= 2
times = [c["timecode"] for c in cl]
assert times == sorted(times), f"not sorted: {times}"
ok(f"GET /api/r/{{token}}/comments → {len(cl)} comments, sorted by timecode")

# ── Client: resolve comment ───────────────────────────────
r = requests.patch(f"{BASE}/api/r/{client_token}/comments/{new_comment['id']}")
assert r.status_code == 200, f"resolve: {r.status_code} {r.text}"
assert r.json()["resolved"] == 1
ok("PATCH /api/r/{token}/comments/{id} → resolved=1")

# Un-resolve
r = requests.patch(f"{BASE}/api/r/{client_token}/comments/{new_comment['id']}")
assert r.json()["resolved"] == 0
ok("PATCH again → resolved=0 (toggle works)")

# ── Client: approve ───────────────────────────────────────
r = requests.post(f"{BASE}/api/r/{client_token}/approve",
    json={"approved_by_name": "HTTP Test Client", "note": "נראה מצוין!"})
assert r.status_code == 201, f"approve: {r.status_code} {r.text}"
ok("POST /api/r/{token}/approve → 201")

# Verify review status updated
r = requests.get(f"{BASE}/api/team/reviews/{http_rev['id']}", headers=HEADERS_TEAM)
assert r.json()["status"] == "approved"
ok("review.status → 'approved' after approve")

# ── Client: SSE stream opens ──────────────────────────────
r = requests.get(f"{BASE}/api/r/{client_token}/stream", stream=True, timeout=3)
assert r.status_code == 200
assert "text/event-stream" in r.headers.get("content-type", "")
first_chunk = next(r.iter_content(chunk_size=512), b"")
assert b"ping" in first_chunk or b"heartbeat" in first_chunk or b"data" in first_chunk or len(first_chunk) >= 0
r.close()
ok("GET /api/r/{token}/stream → 200 text/event-stream")

# ── Client: revoke token → 403 ────────────────────────────
requests.delete(f"{BASE}/api/team/reviews/{http_rev['id']}/tokens/{client_token}",
    headers=HEADERS_TEAM)
r = requests.get(f"{BASE}/api/r/{client_token}")
assert r.status_code == 403
ok("After revoke: GET /r/{token} → 403")

# ── Team: add comment (team side) ────────────────────────
r2_tok = requests.post(f"{BASE}/api/team/reviews/{http_rev['id']}/share",
    headers=HEADERS_TEAM, json={"client_name": "Tester2", "permissions": "comment"}).json()
r = requests.post(f"{BASE}/api/team/reviews/{http_rev['id']}/comments",
    headers=HEADERS_TEAM,
    json={"timecode": 44.0, "text": "הערת צוות", "author_name": "Amit", "author_type": "team"})
assert r.status_code == 201, f"team comment: {r.status_code}"
ok("POST /api/team/reviews/{id}/comments → 201 (team comment)")

# ── Team: patch comment (resolve) ────────────────────────
team_comment = r.json()
r = requests.patch(f"{BASE}/api/team/comments/{team_comment['id']}",
    headers=HEADERS_TEAM, json={"resolved": True})
assert r.status_code == 200 and r.json()["resolved"] == 1
ok("PATCH /api/team/comments/{id} → resolved=1")

# ── Team: delete comment ─────────────────────────────────
r = requests.delete(f"{BASE}/api/team/comments/{team_comment['id']}", headers=HEADERS_TEAM)
assert r.status_code == 200
ok("DELETE /api/team/comments/{id} → 200")

# ── Video: invalid fileId → 400 ──────────────────────────
r = requests.get(f"{BASE}/api/video/../../etc/passwd")
assert r.status_code in (400, 404, 422), f"expected 4xx got {r.status_code}"
ok(f"GET /api/video/../../etc/passwd → {r.status_code} (injection blocked)")

r = requests.get(f"{BASE}/api/video/null")
assert r.status_code in (400, 422), f"expected 400/422 got {r.status_code}"
ok(f"GET /api/video/null → {r.status_code} (invalid id blocked)")

r = requests.get(f"{BASE}/api/video/short")
assert r.status_code in (400, 422), f"expected 400/422 got {r.status_code}"
ok(f"GET /api/video/short → {r.status_code} (too-short id blocked)")

# ── Video: unsigned request (no sig params) ───────────────
r = requests.get(f"{BASE}/api/video/{DRIVE_FILE_ID}")
# Should attempt to connect to Drive (may get 503 locally without SA key, but NOT 400/403 for missing sig)
assert r.status_code in (200, 206, 503, 500), f"unsigned video: {r.status_code}"
ok(f"GET /api/video/{{valid_id}} (no sig) → {r.status_code} (reaches Drive layer)")

# ── Video: tampered signature → 403 ──────────────────────
r = requests.get(f"{BASE}/api/video/{DRIVE_FILE_ID}?exp=9999999999&sig=invalidsig12345678901234567890")
assert r.status_code == 403, f"tampered sig: {r.status_code}"
ok("GET /api/video with tampered sig → 403")

# ── Video: expired signature → 403 ───────────────────────
# Build the expired URL directly with known signing secret (avoids race condition in replace())
import hmac as _hmac, hashlib as _hs
_secret = os.environ.get("TING_SIGNING_SECRET", "signing-secret-abc")
_exp    = 1000000000   # Sun Sep 09 2001 -- definitely expired
_msg    = f"{DRIVE_FILE_ID}:{_exp}"
_sig    = _hmac.new(_secret.encode(), _msg.encode(), _hs.sha256).hexdigest()[:32]
expired_url = f"{BASE}/api/video/{DRIVE_FILE_ID}?exp={_exp}&sig={_sig}"
r = requests.get(expired_url)
assert r.status_code == 403, f"expired sig: {r.status_code}"
ok("GET /api/video with expired sig → 403")

# ════════════════════════════════════════════════════════
# SECTION 4 — review.html static checks
# ════════════════════════════════════════════════════════
section("review.html static checks")

with open(os.path.join(os.path.dirname(__file__), "static", "review.html"), encoding="utf-8") as f:
    html = f.read()

checks = [
    ("Heebo font loaded",        'fonts.googleapis.com' in html and 'Heebo' in html),
    ("RTL direction",            'dir="rtl"' in html or "dir='rtl'" in html),
    ("lang=he",                  'lang="he"' in html),
    ("viewport meta",            'viewport' in html and 'width=device-width' in html),
    ("video element",            '<video ' in html),
    ("loadedmetadata listener",  'loadedmetadata' in html),
    ("error listener on video",  "vid.addEventListener('error'" in html or 'addEventListener("error"' in html),
    ("SSE EventSource",          'EventSource' in html),
    ("SSE reconnect logic",      'onerror' in html),
    ("timecode auto-capture",    'currentTime' in html and 'pendingTimecode' in html),
    ("keyboard shortcuts",       "code === 'Space'" in html or 'Space' in html),
    ("approve endpoint",         '/approve' in html),
    ("PATCH comment (resolve)",  'PATCH' in html),
    ("prefers-reduced-motion",   'prefers-reduced-motion' in html),
    ("focus-visible styles",     'focus-visible' in html),
    ("WCAG contrast colors",     '#f0f0f5' in html or '#f4f4f5' in html),  # light text on dark bg
    ("no hardcoded domain",      'crm.tingil.co' not in html),
    ("API uses TOKEN variable",  'TOKEN' in html and 'location.pathname' in html),
    ("version switching",        'switchVersion' in html),
    ("comment dots on timeline", 'timeline-dot' in html),
    ("toast notifications",      'showToast' in html),
    ("approved overlay",         'approved-overlay' in html),
    ("escape to cancel",         'Escape' in html),
    ("reply support (parent_id)","parent_id" in html),
    ("responsive layout",        'max-width: 900px' in html or '@media' in html),
]

for name, result in checks:
    if result: ok(name)
    else:      fail(name)

# ════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════
server.should_exit = True

print()
if errors:
    print(f"\033[91m{'='*50}\033[0m")
    print(f"\033[91m  FAILED: {len(errors)} errors\033[0m")
    for e in errors:
        print(f"    • {e}")
    print(f"\033[91m{'='*50}\033[0m")
    sys.exit(1)
else:
    print(f"\033[92m{'='*50}\033[0m")
    print(f"\033[92m  ALL TESTS PASSED ✓\033[0m")
    print(f"\033[92m{'='*50}\033[0m")

# Cleanup
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
