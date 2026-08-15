"""Demo-mode handlers for the Google Drive capabilities (ADR-0208
delegated-user auth): ``drive.document.search`` (``handle``, the original
read-only capability), plus ``drive.document.create``/``.update`` (ADR-0326
WP-31, Arkos's delegated Drive/Docs write) added as their own functions
rather than a new standalone MCP server - app/downstream.py dispatches
purely by a binding's `handler` name to a single-purpose function, so each
operation gets its own name/function pair here
(platform/bindings/tools/tool-bindings.yaml's `handler: drive_create` /
`drive_update`) instead of one function branching internally.

To make any of these call real Google Drive: replace the bodies below with
calls to the Drive v3 API (``GET``/``POST``/``PATCH /drive/v3/files``)
using ``delegated_token`` (the *caller's* delegated OAuth2 token,
ADR-0014/ADR-0208 -- per-user delegated OAuth, never domain-wide
service-account impersonation) so every operation respects the user's own
effective Drive permissions. app/main.py's invoke_tool already refuses to
call any of these handlers at all when no delegated token is available
(auth_mode=delegated-user, app/delegation.py) - by the time a handler
runs, delegated_token is guaranteed non-empty. No live Google Workspace
tenant is reachable from this environment, so every body below ignores it
and returns synthetic data.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional


async def handle(
    arguments: Dict[str, Any], caller_sub: str, delegated_token: Optional[str] = None
) -> Dict[str, Any]:
    folder = str(arguments.get("folder", "")).strip() or "My Drive"
    return {
        "demo_mode": True,
        "folder": folder,
        "caller_sub": caller_sub,
        "files": [
            {
                "id": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
                "name": "Zuno DAT - Reference Architecture v3.docx",
                "mime_type": "application/vnd.google-apps.document",
                "modified_time": "2026-07-22T11:03:00Z",
                "url": "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view",
            },
            {
                "id": "2ZyXwVuTsRqPoNmLkJiHgFeDcBa",
                "name": "OpenShift AI 3.5 Sizing Worksheet.xlsx",
                "mime_type": "application/vnd.google-apps.spreadsheet",
                "modified_time": "2026-07-15T08:41:00Z",
                "url": "https://drive.google.com/file/d/2ZyXwVuTsRqPoNmLkJiHgFeDcBa/view",
            },
        ],
    }


async def handle_create(
    arguments: Dict[str, Any], caller_sub: str, delegated_token: Optional[str] = None
) -> Dict[str, Any]:
    title = str(arguments.get("title", "")).strip() or "Untitled document"
    content = str(arguments.get("content", ""))
    doc_id = uuid.uuid4().hex
    return {
        "demo_mode": True,
        "caller_sub": caller_sub,
        "id": doc_id,
        "title": title,
        "mime_type": "application/vnd.google-apps.document",
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
        "content_length": len(content),
    }


async def handle_update(
    arguments: Dict[str, Any], caller_sub: str, delegated_token: Optional[str] = None
) -> Dict[str, Any]:
    document_id = str(arguments.get("document_id", "")).strip()
    if not document_id:
        return {"demo_mode": True, "updated": False, "reason": "document_id is required"}
    content = str(arguments.get("content", ""))
    return {
        "demo_mode": True,
        "caller_sub": caller_sub,
        "id": document_id,
        "updated": True,
        "url": f"https://docs.google.com/document/d/{document_id}/edit",
        "content_length": len(content),
    }
