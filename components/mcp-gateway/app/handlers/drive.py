"""Demo-mode handler for the ``list_drive_files`` MCP tool.

To make this call real Google Drive: replace the body below with a call to
the Drive v3 API (``GET /drive/v3/files``) using the *caller's* delegated
OAuth2 token (ADR-0014 -- per-user delegated OAuth, not domain-wide service
account impersonation) so the results respect the user's own effective
Drive permissions. The delegated token would be resolved from the user's
Keycloak-linked Google session, not from a service credential stored in
Vault. No live Google Workspace tenant is reachable from this environment.
"""

from __future__ import annotations

from typing import Any, Dict


async def handle(arguments: Dict[str, Any], caller_sub: str) -> Dict[str, Any]:
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
