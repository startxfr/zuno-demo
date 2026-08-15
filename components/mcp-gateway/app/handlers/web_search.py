"""Demo-mode handler for the ``web_search`` MCP tool.

To make this call a real web search: replace the body below with a call to
an approved web search API (e.g. Bing Web Search or a similar provider)
using a key sourced from ``secret/zuno/providers/web-search`` (not yet
provisioned). Per MEMORY.md section 7, external web searches must never
leak internal context in the outbound query -- keep that constraint when
wiring the real API (only forward the user-visible query terms, never
retrieved internal document content).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


async def handle(
    arguments: Dict[str, Any], caller_sub: str, delegated_token: Optional[str] = None
) -> Dict[str, Any]:
    # auth_mode=service-identity (ADR-0208): this backend uses a shared
    # provider credential, never a per-user one - delegated_token is
    # always None here and intentionally unused.
    query = str(arguments.get("query", "")).strip()
    return {
        "demo_mode": True,
        "query": query,
        "results": [
            {
                "title": "OpenShift AI 3.5 Release Notes",
                "url": "https://docs.redhat.com/en/documentation/red_hat_openshift_ai/3.5",
                "snippet": "Official Red Hat documentation covering OpenShift AI 3.5 EA2 capabilities, including KServe and DataScienceCluster components.",
            },
            {
                "title": "NVIDIA GPU Operator on OpenShift",
                "url": "https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/",
                "snippet": "Installation and ClusterPolicy configuration guidance for the NVIDIA GPU Operator on Red Hat OpenShift.",
            },
        ],
    }
