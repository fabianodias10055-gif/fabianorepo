"""
Google Drive helper — lists project folders under the Locomotion Systems root.
Auth via service account JSON stored in GOOGLE_SERVICE_ACCOUNT_JSON env var.
"""

import json
import logging
import os
import time

logger = logging.getLogger("drive_helper")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
GDRIVE_ROOT_FOLDER_ID = os.getenv(
    "GDRIVE_ROOT_FOLDER_ID", "1lw5YZnCf6TKbiAn443xLIgOuzzjZx8I9"
)

_cache: list[dict] = []
_cache_ts: float = 0.0
_CACHE_TTL = 300  # seconds


def _get_service():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.warning("Drive auth failed: %s", exc)
        return None


def _list_children(svc, parent_id: str) -> list[dict]:
    res = (
        svc.files()
        .list(
            q=(
                f"'{parent_id}' in parents"
                " and mimeType='application/vnd.google-apps.folder'"
                " and trashed=false"
            ),
            fields="files(id,name,webViewLink)",
            pageSize=200,
            orderBy="name",
        )
        .execute()
    )
    return res.get("files", [])


def list_project_folders() -> list[dict]:
    """Return [{name, url}] for all folders up to 2 levels deep under the root.
    Each name is prefixed with parent path (e.g. 'Sliding System / Sliding System - Standard').
    Cached for 5 minutes."""
    global _cache, _cache_ts
    if _cache and time.time() - _cache_ts < _CACHE_TTL:
        return _cache
    svc = _get_service()
    if not svc:
        return _cache
    try:
        out: list[dict] = []
        level1 = _list_children(svc, GDRIVE_ROOT_FOLDER_ID)
        for f1 in level1:
            out.append({"name": f1["name"], "url": f1.get("webViewLink", "")})
            try:
                level2 = _list_children(svc, f1["id"])
                for f2 in level2:
                    out.append(
                        {
                            "name": f"{f1['name']} / {f2['name']}",
                            "url": f2.get("webViewLink", ""),
                        }
                    )
            except Exception as sub_exc:
                logger.warning("Drive subfolder list failed for %s: %s", f1["name"], sub_exc)
        _cache = out
        _cache_ts = time.time()
        logger.info("Drive: loaded %d project folders (2 levels)", len(_cache))
    except Exception as exc:
        logger.warning("Drive folder list failed: %s", exc)
    return _cache
