"""The two downstream calls of an A2A turn: the model (ai-gateway) and the tools (mcp-gateway).

Both carry the *caller's own* Keycloak token, so the model routing, the guardrails, the quota
ledger and the tool policy all see the real user, never this service (ADR-0563)."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app import signed_chain, transit_signer

logger = logging.getLogger("a2a_gateway.clients")

CLASSIFICATIONS = ("C1", "C2", "C3")


def raise_classification(floor: str, requested: str) -> str:
    """The stricter of two classifications (raise-only, ADR-0565); an unknown value counts as C1."""
    def rank(value: str) -> int:
        value = (value or "").upper()
        return CLASSIFICATIONS.index(value) if value in CLASSIFICATIONS else 0
    return CLASSIFICATIONS[max(rank(floor), rank(requested))]


class DownstreamError(RuntimeError):
    """A model or tool call failed; the message is safe to show the caller."""


def _signed_chain(audience: str, token: str, agent: str, task: str, extra: Dict[str, str]) -> Dict[str, str]:
    """ADR-0603 M14 (WP-225 lot C): the X-Zuno-Agent-Chain this gateway signs for one
    downstream call: the agent it runs, the task, the delegators the executor has
    already checked (verify_chain), bound to the caller's bearer and addressed to the
    receiving gateway (app/signed_chain.py). Empty unless AGENT_CHAIN_SIGNING_KEY_FILE
    names a usable key (the chart value agentChain.sign), so the default changes nothing.

    WP-247 lot 2: with AGENT_CHAIN_SIGNER=transit Vault signs instead (app/transit_signer.py); a Vault
    failure sends no chain, the same as an unreadable key file, and never falls back to a local key.
    This function blocks on Vault in that mode: call it through asyncio.to_thread."""
    try:
        use_transit = transit_signer.signer() == "transit"
    except transit_signer.TransitUnavailable as exc:
        logger.error("no agent chain signed for %s/%s: %s", agent, task, exc)
        return {}
    key = None if use_transit else signed_chain.private_key_from_env()
    if key is None and not use_transit:
        return {}
    try:
        hops = signed_chain.parse_hops(extra.get("X-Zuno-Delegated-By"))
        value = signed_chain.sign(
            private_key=key, signer=transit_signer.sign if use_transit else None,
            audience=audience, token=token, agent=agent, task=task, hops=hops,
        )
    except signed_chain.ChainSignatureError as exc:
        logger.warning("no agent chain signed for %s/%s: %s", agent, task, exc)
        return {}
    except transit_signer.TransitUnavailable as exc:
        logger.error("no agent chain signed for %s/%s, Vault cannot sign: %s", agent, task, exc)
        return {}
    return {signed_chain.HEADER: value}


def _downstream_headers(
    token: str, agent: str, task: str, classification: str, run_id: str, extra: Dict[str, str], audience: str = "",
) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Zuno-Agent": agent,
        "X-Zuno-Task": task,
        "X-Zuno-Data-Classification": classification,
        "X-Zuno-Run-Id": run_id,
    }
    headers.update({k: v for k, v in extra.items() if v})
    if audience:
        headers.update(_signed_chain(audience, token, agent, task, extra))
    return headers


class AiGatewayClient:
    def __init__(self, base_url: str, timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._base = base_url
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def chat(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        token: str,
        agent: str,
        task: str,
        classification: str,
        run_id: str,
        chain_headers: Dict[str, str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": "auto", "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        try:
            response = await self._client.post(
                f"{self._base}/v1/chat/completions",
                json=body,
                headers=await asyncio.to_thread(
                    _downstream_headers, token, agent, task, classification, run_id, chain_headers, "ai-gateway"),
            )
        except httpx.HTTPError as exc:
            logger.warning("ai-gateway unreachable: %s", exc)
            raise DownstreamError("The model gateway is unreachable.") from exc
        if response.status_code == 429:
            raise DownstreamError("The token budget of this user is exhausted for now (quota).")
        if response.status_code >= 400:
            logger.warning("ai-gateway answered %s: %s", response.status_code, response.text[:200])
            raise DownstreamError(f"The model gateway refused the request ({response.status_code}).")
        try:
            return response.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as exc:
            raise DownstreamError("The model gateway returned an unreadable answer.") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


class McpGatewayClient:
    """JSON-RPC over the mcp-gateway front door (`/mcp`): tools/list and tools/call."""

    def __init__(self, base_url: str, timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._url = f"{base_url}/mcp"
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._ids = itertools.count(1)

    async def _rpc(self, method: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        response = await self._client.post(
            self._url, json=payload, headers={**headers, "Accept": "application/json, text/event-stream"},
        )
        if response.status_code >= 400:
            raise DownstreamError(f"The tool gateway refused the request ({response.status_code}).")
        document = response.json()
        if "error" in document:
            raise DownstreamError(str(document["error"].get("message", "tool gateway error"))[:200])
        return document.get("result") or {}

    async def list_tools(self, *, token: str, agent: str, task: str, classification: str, run_id: str,
                         chain_headers: Dict[str, str]) -> List[Dict[str, Any]]:
        headers = await asyncio.to_thread(
            _downstream_headers, token, agent, task, classification, run_id, chain_headers, "mcp-gateway")
        result = await self._rpc("tools/list", {}, headers)
        return list(result.get("tools") or [])

    async def call_tool(self, name: str, arguments: Dict[str, Any], *, token: str, agent: str, task: str,
                        classification: str, run_id: str, chain_headers: Dict[str, str]) -> str:
        headers = await asyncio.to_thread(
            _downstream_headers, token, agent, task, classification, run_id, chain_headers, "mcp-gateway")
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments}, headers)
        text = "\n".join(
            str(part.get("text", "")) for part in (result.get("content") or []) if isinstance(part, dict)
        ).strip()
        if result.get("isError"):
            return f"The tool {name} failed: {text[:500]}"
        return text[:8000]

    async def aclose(self) -> None:
        await self._client.aclose()


def to_openai_tools(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": str(tool.get("description") or "")[:1000],
                "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
        if tool.get("name")
    ]


def parse_arguments(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
