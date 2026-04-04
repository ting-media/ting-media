"""
Uploads carousel output folder to Google Drive.
Auth via Service Account JSON key.
Creates folder tree: root / YYYY-MM-DD / article-title /
"""

import logging
from datetime import datetime
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

MIME_MAP = {
    ".json": "application/json",
    ".docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _get_service():
    """Build and return an authenticated Drive service object."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    key_path = Config.google_service_account_path()
    if not key_path:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_KEY_PATH is not set")

    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service, name: str, parent_id: str) -> str:
    """Return existing Drive folder ID or create a new one."""
    safe_name = name.replace("'", "\\'")
    q = (
        f"name='{safe_name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents "
        f"and trashed=false"
    )
    results = service.files().list(q=q, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_folder(local_folder: Path, article_title: str) -> str | None:
    """
    Upload all files in local_folder to Google Drive.
    Skips raw_response.txt (debug only).

    Returns the Drive folder URL, or None if Drive is not configured / fails.
    """
    root_id = Config.google_drive_root_folder_id()
    if not root_id:
        logger.warning("GOOGLE_DRIVE_ROOT_FOLDER_ID not set — skipping upload")
        return None

    try:
        service = _get_service()
    except Exception as e:
        logger.error("Drive auth failed: %s", e)
        return None

    try:
        from googleapiclient.http import MediaFileUpload

        # Create date sub-folder
        date_str = datetime.today().strftime("%Y-%m-%d")
        date_folder_id = _get_or_create_folder(service, date_str, root_id)

        # Create article sub-folder (max 100 chars)
        article_folder_id = _get_or_create_folder(
            service, article_title[:100], date_folder_id
        )

        # Upload files
        uploaded = 0
        for file_path in sorted(local_folder.iterdir()):
            if file_path.name.startswith("."):
                continue
            if file_path.name == "raw_response.txt":
                continue  # skip debug file
            if not file_path.is_file():
                continue

            mime = MIME_MAP.get(file_path.suffix.lower(), "application/octet-stream")
            meta = {"name": file_path.name, "parents": [article_folder_id]}
            media = MediaFileUpload(str(file_path), mimetype=mime, resumable=False)
            service.files().create(
                body=meta, media_body=media, fields="id"
            ).execute()
            uploaded += 1
            logger.info("Uploaded: %s", file_path.name)

        folder_url = (
            f"https://drive.google.com/drive/folders/{article_folder_id}"
        )
        logger.info("Drive upload complete (%d files): %s", uploaded, folder_url)
        return folder_url

    except Exception as e:
        logger.exception("Drive upload failed: %s", e)
        return None
