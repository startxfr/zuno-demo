"""Handler for the ``web_search`` MCP tool while no web search provider is configured.

No web search API is provisioned on this platform (a key would live at
``secret/zuno/providers/web-search``). The handler used to return two fixed
"demo" results whatever the query (OpenShift AI 3.5 release notes, NVIDIA
GPU Operator). Agents took them for real search results: on a question
they did not match, Tekos re-queried about thirty times in three minutes and
could cite a page it never read (tekos stresstest scenario #11, 2026-10-25).

It now answers honestly: no results, and a message the model reads, telling
it to answer from the documents its retriever already returned. The call
still succeeds (HTTP 200): an error would surface as a 502 the agent
framework may retry.

To make this a real web search: call an approved web search API with the
key above. Per MEMORY.md section 7, external web searches must never leak
internal context in the outbound query -- only forward the user-visible
query terms, never retrieved internal document content.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

UNAVAILABLE_MESSAGE = (
    "No web search provider is configured on this platform, so no web results exist. "
    "Do not call this tool again for this question: answer from the documents already "
    "retrieved (internal documentation and the indexed Red Hat documentation), and cite "
    "their URLs."
)


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
    caller_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # auth_mode=service-identity (ADR-0208): this backend uses a shared
    # provider credential, never a per-user one - delegated_token is
    # always None here and intentionally unused.
    query = str(arguments.get("query", "")).strip()
    return {
        "available": False,
        "query": query,
        "results": [],
        "message": UNAVAILABLE_MESSAGE,
    }
