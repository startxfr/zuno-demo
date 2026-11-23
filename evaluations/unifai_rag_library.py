#!/usr/bin/env python3
"""A persona's Personal documents in UnifAI's RAG, through the UnifAI UI route (ADR-0616, WP-274).

`make demo start` and `make demo stop` of the unifai-live-rag demo use it to prepare and clean the library of
consultant-01: delete named documents, upload named files and wait until they are DONE.

The endpoints were mapped live on demo333 on 2026-11-14 (zuno-demo-reorg-demo333, upload and delete of a test file
with the owner's go). The UI route's nginx maps `/api1/` to the RAG server's `/api/`, and each Flask blueprint adds its
own prefix:

    GET    /api1/data_sources/data.sources.get?source_type=DOCUMENT   the persona's sources, `status` == "DONE" when ready
    POST   /api1/docs/upload           {"files": [{"name", "content": <base64>}]}          (JSON, not multipart)
    PUT    /api1/pipelines/embed       {"data": [{"source_name", "tags"}], "source_type": "document",
                                        "skip_validation": true}                          starts the pipeline
    DELETE /api1/data_sources/data.source.delete   {"pipeline_ids": [<source_id>]}   200, 207 partial, 500 failure

A library is per user (`upload_by`), with no team or scope parameter. The persona signs in as itself:
`EVAL_PERSONAS=0` is forced, because the eval twin (`test-eval-consultant-01`) has its own, empty library.

    python3 evaluations/unifai_rag_library.py --persona consultant-01 list
    python3 evaluations/unifai_rag_library.py --persona consultant-01 delete a.md b.md
    python3 evaluations/unifai_rag_library.py --persona consultant-01 upload docs/demo/unifai-rag-upload/a.md --wait 300
    python3 evaluations/unifai_rag_library.py --persona consultant-01 warm consultant-01-my-assistant

The password is read at run time from zuno-ai-run/acceptance-gate-credentials and never printed. The output is one
JSON object per line; the exit code is 0 only when every action succeeded.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
DONE = "DONE"
_FAILED_WORDS = ("FAIL", "ERROR")


class LibraryError(RuntimeError):
    pass


# -- the API, on any client with httpx's get/post/put/request methods ---------------------------------------------


def _json(resp: Any, what: str) -> Dict[str, Any]:
    if resp.status_code != 200:
        raise LibraryError(f"{what}: HTTP {resp.status_code}")
    return resp.json()


def list_sources(client: Any, api: str) -> List[Dict[str, Any]]:
    """The persona's document sources: source_id, source_name, status."""
    body = _json(client.get(f"{api}/data_sources/data.sources.get", params={"source_type": "DOCUMENT"}),
                 "list sources")
    return [
        {"source_id": s.get("source_id", ""), "source_name": s.get("source_name", ""),
         "status": str(s.get("status") or "").upper()}
        for s in body.get("sources") or []
    ]


def check_name(name: str) -> str:
    """The server refuses names with a path in them (HTTP 400); refuse them before the call."""
    if not name or "/" in name or "\\" in name or ".." in name:
        raise LibraryError(f"refused file name {name!r}: a bare file name is required")
    return name


def delete_named(client: Any, api: str, names: Iterable[str]) -> List[Dict[str, Any]]:
    """Delete every source whose name is exactly one of `names`; nothing else is touched."""
    wanted = [check_name(n) for n in names]
    by_name: Dict[str, List[str]] = {}
    for s in list_sources(client, api):
        if s["source_name"] in wanted:
            by_name.setdefault(s["source_name"], []).append(s["source_id"])
    results = []
    for name in wanted:
        ids = by_name.get(name, [])
        if not ids:
            results.append({"action": "delete", "name": name, "result": "absent", "ok": True})
            continue
        resp = client.request("DELETE", f"{api}/data_sources/data.source.delete", json={"pipeline_ids": ids})
        failed = []
        if resp.status_code == 200:
            failed = (resp.json().get("results") or {}).get("failed") or []
        ok = resp.status_code == 200 and not failed
        results.append({"action": "delete", "name": name, "count": len(ids),
                        "result": "deleted" if ok else f"HTTP {resp.status_code}", "ok": ok})
    return results


def upload_files(client: Any, api: str, paths: Iterable[pathlib.Path]) -> List[Dict[str, Any]]:
    """Upload each file under its own name and start its pipeline. A name already in the library is left alone."""
    present = {s["source_name"] for s in list_sources(client, api)}
    results = []
    for path in paths:
        name = check_name(path.name)
        if name in present:
            results.append({"action": "upload", "name": name, "result": "present", "ok": True})
            continue
        content = base64.b64encode(path.read_bytes()).decode()
        _json(client.post(f"{api}/docs/upload", json={"files": [{"name": name, "content": content}]}),
              f"upload {name}")
        body = _json(client.put(f"{api}/pipelines/embed", json={
            "data": [{"source_name": name, "tags": []}], "source_type": "document", "skip_validation": True,
        }), f"embed {name}")
        ok = bool(body.get("registration_completed"))
        results.append({"action": "upload", "name": name, "result": "started" if ok else "not registered", "ok": ok})
    return results


def wait_done(client: Any, api: str, names: Iterable[str], timeout: float = 300, interval: float = 3,
              sleep: Callable[[float], None] = time.sleep,
              clock: Callable[[], float] = time.monotonic) -> List[Dict[str, Any]]:
    """Poll until every named source is DONE; a failed pipeline or the timeout ends the wait."""
    wanted = [check_name(n) for n in names]
    start = clock()
    while True:
        status = {}
        for s in list_sources(client, api):
            if s["source_name"] in wanted:
                status[s["source_name"]] = s["status"]
        failed = [n for n in wanted if any(w in status.get(n, "") for w in _FAILED_WORDS)]
        done = [n for n in wanted if status.get(n) == DONE]
        elapsed = round(clock() - start, 1)
        if failed or len(done) == len(wanted) or elapsed >= timeout:
            return [
                {"action": "wait", "name": n, "result": status.get(n, "absent") or "unknown",
                 "seconds": elapsed, "ok": status.get(n) == DONE}
                for n in wanted
            ]
        sleep(interval)


# -- sign-in and command line -------------------------------------------------------------------------------------


def _oc(*args: str) -> str:
    cmd = ["oc"] + (["--context", os.environ["OC_CONTEXT"]] if os.getenv("OC_CONTEXT") else []) + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if out.returncode != 0 or not out.stdout.strip():
        raise LibraryError(f"`oc {args[0]} ...` failed (is `oc` logged in?)")
    return out.stdout.strip()


WARM_PROMPT = "In one short sentence, say what you can help me with."


def persona_target(persona: str) -> tuple:
    """(UnifaiTarget, client, api base) for the persona itself, never its eval twin."""
    os.environ["EVAL_PERSONAS"] = "0"
    sys.path.insert(0, str(HERE / "common"))
    from unifai_target import UnifaiTarget  # imports httpx, needed only here

    ui = os.getenv("UNIFAI_URL") or f"https://unifai-ui-zuno-unifai.{_oc('get', 'ingresses.config.openshift.io', 'cluster', '-o', 'jsonpath={.spec.domain}')}"
    password = base64.b64decode(_oc("-n", "zuno-ai-run", "get", "secret", "acceptance-gate-credentials",
                                    "-o", "jsonpath={.data.demo-persona-password}")).decode()
    target = UnifaiTarget(password, ui_url=ui)
    return target, target.client(persona), f"{ui.rstrip('/')}/api1"


def warm(target: Any, persona: str, workflow: str, timeout: float = 180) -> List[Dict[str, Any]]:
    """One turn on the persona's own workflow, so the model answers fast on stage; the session is deleted after."""
    try:
        run = target.run(persona, WARM_PROMPT, workflow=workflow, timeout=timeout)
    finally:
        target.cleanup()
    ok = run.status == 200 and bool(run.reply.strip())
    return [{"action": "warm", "workflow": workflow, "seconds": round(run.seconds, 1),
             "result": "answered" if ok else f"HTTP {run.status}", "ok": ok}]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--persona", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_del = sub.add_parser("delete")
    p_del.add_argument("names", nargs="+")
    p_up = sub.add_parser("upload")
    p_up.add_argument("files", nargs="+", type=pathlib.Path)
    p_up.add_argument("--wait", type=float, default=0, help="seconds to wait until every file is DONE (0: no wait)")
    p_warm = sub.add_parser("warm")
    p_warm.add_argument("workflow")
    args = parser.parse_args(argv)

    try:
        target, client, api = persona_target(args.persona)
        if args.command == "warm":
            results = warm(target, args.persona, args.workflow)
        elif args.command == "list":
            results = [dict(s, action="list", ok=True) for s in list_sources(client, api)]
        elif args.command == "delete":
            results = delete_named(client, api, args.names)
        else:
            missing = [str(f) for f in args.files if not f.is_file()]
            if missing:
                raise LibraryError(f"no such file: {', '.join(missing)}")
            results = upload_files(client, api, args.files)
            if args.wait > 0 and all(r["ok"] for r in results):
                results += wait_done(client, api, [f.name for f in args.files], timeout=args.wait)
    except LibraryError as exc:
        print(json.dumps({"action": args.command, "result": str(exc), "ok": False}))
        return 1
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
