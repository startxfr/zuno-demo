"""Demo-mode handler for the ``read_gmail`` MCP tool.

To make this call real Gmail: replace the body below with a call to the
Gmail API (``GET /gmail/v1/users/me/messages``) using the caller's
delegated OAuth2 token (ADR-0014). Per MEMORY.md section 8, tools that read
a user's mailbox must never be used to send mail as that user -- this
handler (and its real-API replacement) must stay read-only. No live Google
Workspace tenant is reachable from this environment.
"""

from __future__ import annotations

from typing import Any, Dict


async def handle(arguments: Dict[str, Any], caller_sub: str) -> Dict[str, Any]:
    query = str(arguments.get("query", "")).strip() or "in:inbox"
    return {
        "demo_mode": True,
        "query": query,
        "caller_sub": caller_sub,
        "messages": [
            {
                "id": "18f2a3c9d4e5f601",
                "from": "client.contact@example-customer.com",
                "subject": "RE: OpenShift AI POC - next steps",
                "snippet": "Thanks for the demo last week, our team would like to schedule a follow-up on GPU sizing...",
                "received_at": "2026-08-01T15:22:00Z",
            },
            {
                "id": "18f29b1a2c3d4e50",
                "from": "partner.se@redhat.com",
                "subject": "L4 GPU allocation confirmation",
                "snippet": "Confirming the two-node L4 allocation for the Zuno demo cluster is provisioned...",
                "received_at": "2026-07-29T09:05:00Z",
            },
        ],
    }
