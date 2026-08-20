"""Demo-mode handler for the ``send_technical_report_email`` MCP tool.

Per MEMORY.md section 5: agents must never send email externally or
impersonate a user's mailbox for outbound mail. Scheduled/triggered
reporting must use a technical SMTP identity and stay restricted to
internal recipients -- this handler enforces that constraint even in demo
mode (it rejects any recipient outside the internal domain allow-list
rather than pretending to send it).

To make this call a real mailbox: replace the "send" step below with an
SMTP call (see ansible/roles/smtp, owned by another track) using the
technical SMTP identity's credentials sourced from
``secret/zuno/smtp/technical`` -- never a user's own mailbox credential.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Domains considered "internal" for this demo. Override via the
# INTERNAL_EMAIL_DOMAINS env var (comma-separated) once a real internal
# domain is known for the target environment.
import os

_INTERNAL_DOMAINS = tuple(
    d.strip().lower()
    for d in os.getenv("INTERNAL_EMAIL_DOMAINS", "zuno.example.internal").split(",")
    if d.strip()
)


def _is_internal(recipient: str) -> bool:
    recipient = recipient.strip().lower()
    return "@" in recipient and recipient.split("@", 1)[1] in _INTERNAL_DOMAINS


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
) -> Dict[str, Any]:
    # auth_mode=service-identity (ADR-0208): the technical SMTP identity
    # is a shared credential, never a per-user one - delegated_token is
    # always None here and intentionally unused.
    recipients: List[str] = list(arguments.get("recipients", []) or [])
    subject = str(arguments.get("subject", "")).strip()
    body = str(arguments.get("body", "")).strip()

    rejected = [r for r in recipients if not _is_internal(r)]
    if rejected:
        return {
            "demo_mode": True,
            "sent": False,
            "reason": (
                "recipients outside the internal domain allow-list are rejected "
                f"(agents must not send mail externally): {rejected}"
            ),
        }

    return {
        "demo_mode": True,
        "sent": True,
        "via": "technical-smtp-identity",
        "recipients": recipients,
        "subject": subject,
        "body_preview": body[:200],
        "caller_sub": caller_sub,
    }
