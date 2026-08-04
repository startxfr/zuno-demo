"""Demo-mode handler for the ``search_confluence`` MCP tool.

To make this call the real internal Confluence instance: replace the body
below with a call to the Confluence REST API
(``GET {CONFLUENCE_BASE_URL}/wiki/rest/api/content/search?cql=text~"{query}"``)
authenticated with a Confluence API token or OAuth2 app credential sourced
from an ExternalSecret at ``secret/zuno/providers/confluence`` (not yet
provisioned -- no real Confluence tenant is reachable from this
environment). Map each returned ``content`` item to
``{id, title, space, url, excerpt, last_modified}`` as below.
"""

from __future__ import annotations

from typing import Any, Dict


async def handle(arguments: Dict[str, Any], caller_sub: str) -> Dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    return {
        "demo_mode": True,
        "query": query,
        "results": [
            {
                "id": "123456789",
                "title": "OpenShift AI 3.5 EA2 - Model Serving Runbook",
                "space": "TECH",
                "url": "https://confluence.example.internal/wiki/spaces/TECH/pages/123456789",
                "excerpt": (
                    "Steps to deploy a KServe InferenceService with the vLLM "
                    "ServingRuntime on an L4-backed worker node, including "
                    "ClusterPolicy prerequisites and GPU scheduling notes."
                ),
                "last_modified": "2026-07-18T09:12:00Z",
            },
            {
                "id": "987654321",
                "title": "Keycloak Realm Federation Checklist",
                "space": "TECH",
                "url": "https://confluence.example.internal/wiki/spaces/TECH/pages/987654321",
                "excerpt": (
                    "Checklist for onboarding a new OIDC client and validating "
                    "Google Workspace federation against the zuno realm."
                ),
                "last_modified": "2026-06-30T14:45:00Z",
            },
        ],
    }
