"""
TING Review — One-time migration: Firestore → SQLite
=======================================================
Run ONCE on the VPS after installing the new system:
  cd /opt/ting-review && python migrate_firestore.py

Reads:
  Firestore: videoReviews + videoComments
Writes:
  SQLite: reviews + versions + comments

Safe to re-run — uses INSERT OR IGNORE.
"""

import os, sys, json, logging
from datetime import timezone, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("migrate")

# ── Firebase Admin SDK ────────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials, firestore as fs_admin
except ImportError:
    sys.exit("Install firebase-admin first: pip install firebase-admin")

CRED_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "/etc/ting-drive/service-account.json")
if not os.path.exists(CRED_PATH):
    sys.exit(f"Service account key not found at {CRED_PATH}")

cred = credentials.Certificate(CRED_PATH)
firebase_admin.initialize_app(cred)
store = fs_admin.client()

# ── Local DB ──────────────────────────────────────────────────────────────────
import db
db.init_db()

import sqlite3
conn = sqlite3.connect(db.DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")

# ── Helpers ───────────────────────────────────────────────────────────────────

def ts_to_iso(ts):
    """Convert Firestore Timestamp or Python datetime to ISO string."""
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if hasattr(ts, 'isoformat'):
        return ts.isoformat()
    if hasattr(ts, 'seconds'):          # Firestore Timestamp
        return datetime.fromtimestamp(ts.seconds, tz=timezone.utc).isoformat()
    return str(ts)

# ── Migrate reviews ───────────────────────────────────────────────────────────
log.info("Fetching videoReviews from Firestore...")
reviews_ref = store.collection("videoReviews").stream()
review_count = 0
version_count = 0

for doc in reviews_ref:
    d = doc.to_dict()
    rid = doc.id

    # Insert review
    try:
        conn.execute("""
            INSERT OR IGNORE INTO reviews
              (id, title, client_id, task_id, status, current_version, current_round, created_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            rid,
            d.get("title", "סקירה ללא שם"),
            d.get("clientId") or d.get("client_id"),
            d.get("taskId")   or d.get("task_id"),
            d.get("status", "in_review"),
            d.get("currentVersion", 1),
            d.get("currentRound", 1),
            d.get("userId") or d.get("created_by", "migrated"),
            ts_to_iso(d.get("createdAt")),
        ))
        review_count += 1
    except Exception as e:
        log.warning(f"Review {rid} failed: {e}")
        continue

    # Migrate versions array
    versions = d.get("versions") or []
    if not versions:
        # Legacy: single version from top-level fields
        drive_id = d.get("driveFileId")
        if drive_id:
            versions = [{
                "v": 1,
                "driveFileId": drive_id,
                "fileName": d.get("fileName"),
                "uploadedBy": d.get("userId", "migrated"),
                "uploadedAt": ts_to_iso(d.get("createdAt")),
                "note": "מיגרציה מ-Firestore",
            }]

    for v in versions:
        vid = f"{rid}_v{v.get('v', 1)}"
        try:
            conn.execute("""
                INSERT OR IGNORE INTO versions
                  (id, review_id, version_number, round, drive_file_id, file_name, uploaded_by, uploaded_at, note)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                vid, rid,
                v.get("v", 1),
                v.get("round", 1),
                v.get("driveFileId", ""),
                v.get("fileName"),
                v.get("uploadedBy", "migrated"),
                ts_to_iso(v.get("uploadedAt")),
                v.get("note"),
            ))
            version_count += 1
        except Exception as e:
            log.warning(f"Version {vid} failed: {e}")

conn.commit()
log.info(f"✅ Reviews migrated: {review_count}, Versions: {version_count}")

# ── Migrate comments ──────────────────────────────────────────────────────────
log.info("Fetching videoComments from Firestore...")
comments_ref = store.collection("videoComments").stream()
comment_count = 0

for doc in comments_ref:
    d = doc.to_dict()
    cid = doc.id
    review_id = d.get("reviewId")
    if not review_id:
        continue

    # Map version: try to find version id from review versions
    version_id = None
    ver_num = d.get("version", 1)
    row = conn.execute(
        "SELECT id FROM versions WHERE review_id=? AND version_number=?", (review_id, ver_num)
    ).fetchone()
    if row:
        version_id = row["id"]

    ann = d.get("annotation")
    ann_json = json.dumps(ann) if ann else None

    try:
        conn.execute("""
            INSERT OR IGNORE INTO comments
              (id, review_id, version_id, round, timecode, text,
               author_name, author_type, annotation_json, resolved, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cid, review_id, version_id,
            d.get("round", 1),
            d.get("time", 0),         # Firestore used 'time', we use 'timecode'
            d.get("text", ""),
            d.get("authorName") or d.get("author_name", "משתמש"),
            d.get("source", "team"),
            ann_json,
            1 if d.get("resolved") else 0,
            ts_to_iso(d.get("createdAt")),
        ))
        comment_count += 1
    except Exception as e:
        log.warning(f"Comment {cid} failed: {e}")

conn.commit()
conn.close()

log.info(f"✅ Comments migrated: {comment_count}")
log.info("Migration complete!")
