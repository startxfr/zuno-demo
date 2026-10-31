#!/usr/bin/env python3
"""WP-177: which Kuadrant token counters move for one real chat?

The Kuadrant wasm shim completes only the first two token limits of a route
(by sorted limit name), so on the local-model routes only the maas-controller's
per-subscription limits count and the gateway-level `standard-group` and
`standard-user` limits do not (docs/roadmap/evidence/wp-157-inventory.md,
follow-up of 2026-10-25). This probe makes that visible and repeatable: it
reads Limitador's counters for one route scope, sends ONE short persona chat
through the ai-gateway, reads them again, and prints which limit family moved
(`subscription`, `group`, `user`) and by how many tokens.

Read-only on the cluster apart from that one chat. Exit 0 when the moved set
equals `--expect` (default: `subscription`, today's truth), 1 when it differs
(with an "IMPROVED" line when more families moved, the sign of an upstream fix
or a policy change), 2 when the probe could not run.

Environment: AI_GATEWAY_URL, KEYCLOAK_URL, DEMO_PERSONA_PASSWORD,
EVAL_CLIENT_SECRET, LIMITADOR_URL (e.g. a port-forward to the Limitador pod's
8080), PROBE_SCOPE (default zuno-ai-run/qwen36-27b-instruct-kserve-route),
PROBE_PERSONA (default eval-consultant-01), PROBE_MODEL (default local-maas).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from typing import Dict, List, Set, Tuple

import httpx

FAMILIES = ("subscription", "group", "user")


def family(limit_name: str) -> str:
    if limit_name.startswith("standard-user"):
        return "user"
    if limit_name.startswith("standard-group"):
        return "group"
    if limit_name.startswith("models-as-a-service-"):
        return "subscription"
    return "other"


def _key(counter: Dict) -> Tuple[str, str]:
    return counter["limit"]["name"], json.dumps(counter.get("set_variables") or {}, sort_keys=True)


def consumed(counters: List[Dict]) -> Dict[Tuple[str, str], int]:
    """Tokens consumed so far per counter: max_value - remaining."""
    return {_key(c): int(c["limit"]["max_value"]) - int(c["remaining"]) for c in counters}


def moved_families(before: List[Dict], after: List[Dict]) -> Dict[str, int]:
    """Tokens added per family between two reads (a counter new in `after` counts from 0)."""
    b, a = consumed(before), consumed(after)
    out: Dict[str, int] = {}
    for key, value in a.items():
        delta = value - b.get(key, 0)
        if delta > 0:
            fam = family(key[0])
            out[fam] = out.get(fam, 0) + delta
    return out


def judge(moved: Dict[str, int], expect: Set[str]) -> Tuple[int, str]:
    got = {f for f in moved if f in FAMILIES}
    detail = ", ".join(f"{f}=+{moved[f]}" for f in sorted(moved)) or "nothing moved"
    if got == expect:
        return 0, f"OK: moved {sorted(got)} as expected ({detail})"
    if got > expect:
        return 1, f"IMPROVED: more than expected moved {sorted(got)} vs {sorted(expect)} ({detail}); update the expectation and the ADR-0570 wording"
    return 1, f"DIFFERS: moved {sorted(got)} vs expected {sorted(expect)} ({detail})"


def read_counters(client: httpx.Client, limitador: str, scope: str) -> List[Dict]:
    resp = client.get(f"{limitador.rstrip('/')}/counters/{urllib.parse.quote(scope, safe='')}")
    resp.raise_for_status()
    return resp.json()


def persona_token(client: httpx.Client, keycloak: str, secret: str, persona: str, password: str) -> str:
    resp = client.post(
        f"{keycloak.rstrip('/')}/realms/zuno/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "zuno-evaluations", "client_secret": secret,
              "username": persona, "password": password},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--expect", default="subscription", help="comma list of families expected to move (default: subscription)")
    ap.add_argument("--settle", type=float, default=3.0, help="seconds to wait for the report path before the second read")
    args = ap.parse_args(argv)
    expect = {f for f in args.expect.split(",") if f}
    env = os.environ
    try:
        with httpx.Client(timeout=90.0, verify=env.get("PROBE_VERIFY_TLS", "1") != "0") as client:
            scope = env.get("PROBE_SCOPE", "zuno-ai-run/qwen36-27b-instruct-kserve-route")
            before = read_counters(client, env["LIMITADOR_URL"], scope)
            token = persona_token(client, env["KEYCLOAK_URL"], env["EVAL_CLIENT_SECRET"],
                                  env.get("PROBE_PERSONA", "eval-consultant-01"), env["DEMO_PERSONA_PASSWORD"])
            chat = client.post(
                f"{env['AI_GATEWAY_URL'].rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={"model": env.get("PROBE_MODEL", "local-maas"),
                      "messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 16},
            )
            if chat.status_code != 200:
                print(f"probe could not run: chat answered {chat.status_code}", file=sys.stderr)
                return 2
            time.sleep(args.settle)
            after = read_counters(client, env["LIMITADOR_URL"], scope)
    except (KeyError, httpx.HTTPError) as exc:
        print(f"probe could not run: {exc!r}", file=sys.stderr)
        return 2
    code, message = judge(moved_families(before, after), expect)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
