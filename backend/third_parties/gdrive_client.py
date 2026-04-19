"""
Google Drive Client for Caption Export Integration

Uses the existing GCS service account credentials to authenticate with Google Drive.
The service account must have the Drive API enabled and must be granted access to
any folders it needs to read from or write to (share the folder with the SA email).
"""

import io
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

# MIME types we consider "images" in Drive
DRIVE_IMAGE_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _get_credentials():
    from google.oauth2 import service_account
    from backend.config import GlobalConfig

    creds_path = GlobalConfig.GDRIVE_CREDENTIALS_PATH
    if not Path(creds_path).exists():
        raise FileNotFoundError(
            f"Google Drive credentials not found at: {creds_path}. "
            "Make sure GDRIVE_CREDENTIALS_PATH is set in .env and the file exists."
        )

    return service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=SCOPES,
    )


def _get_service():
    from googleapiclient.discovery import build

    creds = _get_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_folder_id(url_or_id: str) -> str:
    """
    Extract folder ID from a Google Drive folder URL, or return as-is if it's
    already a bare folder ID.

    Handles URLs like:
      https://drive.google.com/drive/folders/FOLDER_ID
      https://drive.google.com/drive/folders/FOLDER_ID?usp=sharing
      https://drive.google.com/drive/u/0/folders/FOLDER_ID
    """
    url_or_id = url_or_id.strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # Fallback: treat the whole string as an ID (no slashes, looks like a Drive ID)
    if "/" not in url_or_id and len(url_or_id) > 10:
        return url_or_id
    raise ValueError(
        f"Could not extract a folder ID from: {url_or_id!r}. "
        "Paste the full Google Drive folder URL (e.g. https://drive.google.com/drive/folders/...)."
    )


def list_images_in_folder(folder_id: str) -> list[dict]:
    """
    List all image files directly inside a Google Drive folder.
    Returns a list of dicts with keys: id, name, mimeType, size.
    """
    service = _get_service()
    mime_query = " or ".join(f"mimeType='{m}'" for m in DRIVE_IMAGE_MIMETYPES)
    query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"

    files: list[dict] = []
    page_token: Optional[str] = None
    while True:
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                orderBy="name",
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"[gdrive] Found {len(files)} images in folder {folder_id}")
    return files


def download_file(file_id: str) -> bytes:
    """Download a file from Google Drive and return its raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def upload_file(filename: str, data: bytes, mime_type: str, folder_id: str) -> str:
    """
    Upload bytes as a file into a Google Drive folder.
    Returns the newly created file's Drive ID.
    """
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
    created = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, name")
        .execute()
    )
    logger.info(f"[gdrive] Uploaded {filename} → file ID {created['id']}")
    return created["id"]


def make_file_public(file_id: str) -> str:
    """
    Grant anyone-with-the-link read access to a Drive file.
    Returns the public shareable URL.
    """
    service = _get_service()
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    public_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    logger.info(f"[gdrive] Made {file_id} public → {public_url}")
    return public_url
