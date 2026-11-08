#!/usr/bin/env python3
"""Measure the Blender prompt set (ADR-0610 clause 8, WP-245).

Each prompt of prompts.json goes, `--repeats` times, through the same path as the add-on: a device sign-in of the
public client `blender` as an evaluation persona (no human, device_login.py), then a streamed completion at
https://ai-gateway.<domain> with X-Zuno-Agent: blender and X-Zuno-Task: bpy. Every answer is reduced to its code and
statically checked with the add-on's own functions, then all scripts are replayed in headless Blender through the
add-on's Run operator (test_in_blender.py), each in an empty scene, optionally rendered to PNG.

A run succeeds when the call answers 200, the script passes the static check, Run finishes and at least one object
exists. A prompt is stage-ready when every repeat succeeds. The summary (no token, no script text) is written to
--results; scripts and renders go to --work-dir, outside the repository.

    python3 evaluations/blender/measure_prompts.py --blender /path/to/blender \
        --results evaluations/blender/results/prompt-set-gpt-oss-20b-YYYY-MM-DD.json --work-dir ~/blender-measure

Runs from a workstation where `oc` is logged in (the persona password is read from
zuno-ai-run/acceptance-gate-credentials, never printed). The entry's rate limit is 60 requests per user per 5
minutes: 12 prompts x 2 repeats stays under it.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import ssl
import subprocess
import sys
import time
from typing import Dict, List

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def judge_run(gen: Dict, blender: Dict) -> "tuple[bool, str]":
    """(success, reason) for one generation and its Blender replay."""
    if gen.get("status") != 200:
        return False, f"gateway {gen.get('status')}: {gen.get('error', '')}".strip()
    if gen.get("check"):
        return False, "static check: " + "; ".join(gen["check"][:2])
    if not blender:
        return False, "no Blender result"
    if blender.get("outcome") != "FINISHED":
        return False, "Blender: " + (blender.get("error") or blender.get("outcome") or "failed")
    if blender.get("objects", 0) < 1:
        return False, "Blender: no object created"
    return True, f"{blender['objects']} objects, {blender.get('modifiers', 0)} modifiers, {blender.get('materials', 0)} materials"


def aggregate(runs: List[Dict], repeats: int) -> Dict:
    """Per prompt: successes out of repeats, mean seconds, reasons; the stage-ready set; the overall rate."""
    by_id: Dict[str, Dict] = {}
    for r in runs:
        p = by_id.setdefault(r["id"], {"id": r["id"], "prompt": r["prompt"], "successes": 0, "runs": 0,
                                       "seconds": [], "reasons": []})
        p["runs"] += 1
        p["successes"] += 1 if r["ok"] else 0
        if r.get("seconds") is not None:
            p["seconds"].append(r["seconds"])
        p["reasons"].append(r["reason"])
    prompts = []
    for p in by_id.values():
        secs = p.pop("seconds")
        p["mean_seconds"] = round(sum(secs) / len(secs), 1) if secs else None
        p["stage_ready"] = p["runs"] == repeats and p["successes"] == repeats
        prompts.append(p)
    total = sum(p["runs"] for p in prompts)
    ok = sum(p["successes"] for p in prompts)
    return {"prompts": prompts, "stage_ready": [p["id"] for p in prompts if p["stage_ready"]],
            "runs": total, "successes": ok, "success_rate": round(ok / total, 3) if total else 0.0}


def _blender_results(blender_bin: str, addon: pathlib.Path, scripts: List[pathlib.Path], render_dir: str) -> Dict:
    cmd = [blender_bin, "--background", "--factory-startup", "--python", str(HERE / "test_in_blender.py"), "--",
           str(addon)] + (["--render-dir", render_dir] if render_dir else []) + [str(s) for s in scripts]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    results = {}
    for line in out.stdout.splitlines():
        if line.startswith("RESULT_JSON "):
            r = json.loads(line[len("RESULT_JSON "):])
            results[r["script"]] = r
    return results


def main(argv=None) -> int:
    import golden_path_probe as g
    from bpy_stub import ADDON, load_addon
    from device_login import device_token, refresh, revoke

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prompts", default=str(HERE / "prompts.json"))
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--persona", default=os.getenv("BLENDER_EVAL_PERSONA", "eval-ai-dev-01"))
    ap.add_argument("--blender", default=os.getenv("BLENDER_BIN", "blender"))
    ap.add_argument("--work-dir", default=str(pathlib.Path.home() / "blender-measure"))
    ap.add_argument("--render", action="store_true", help="render each successful script to PNG in --work-dir")
    ap.add_argument("--results", default="")
    ap.add_argument("--only", default="", help="comma list of prompt ids")
    args = ap.parse_args(argv)

    prompts = json.loads(pathlib.Path(args.prompts).read_text())["prompts"]
    if args.only:
        prompts = [p for p in prompts if p["id"] in set(args.only.split(","))]
    addon = load_addon()
    domain = g.cluster_domain()
    gateway, issuer = addon.endpoints(domain)
    password = g.secret_value("zuno-ai-run", "acceptance-gate-credentials", "demo-persona-password")
    tls = ssl.create_default_context()  # the add-on always verifies; so does its measurement
    work = pathlib.Path(args.work_dir).expanduser()
    (work / "scripts").mkdir(parents=True, exist_ok=True)

    tokens = device_token(issuer, args.persona, password, verify=True, timeout=60)
    expires = time.monotonic() + int(tokens.get("expires_in", 300)) - 30
    gens: List[Dict] = []
    try:
        for p in prompts:
            for n in range(1, args.repeats + 1):
                if time.monotonic() > expires:
                    tokens = refresh(issuer, tokens["refresh_token"])
                    expires = time.monotonic() + int(tokens.get("expires_in", 300)) - 30
                payload = {"model": addon.MODEL, "temperature": 0.2,
                           "messages": [{"role": "system", "content": addon.SYSTEM_PROMPT},
                                        {"role": "user", "content": f"Create this 3D object or scene: {p['prompt']}"}]}
                started = time.monotonic()
                try:
                    status, answer = addon._stream_chat(f"{gateway}/v1/chat/completions", payload, tls,
                                                        tokens["access_token"], timeout=120)
                except Exception as exc:  # noqa: BLE001 - a cut stream is a failed run, not a crash of the measurement
                    status, answer = 0, {"error": type(exc).__name__}
                gen = {"id": p["id"], "prompt": p["prompt"], "repeat": n, "status": status,
                       "seconds": round(time.monotonic() - started, 1)}
                if status == 200:
                    code = addon.extract_code(answer)
                    gen["check"] = addon.check_script(code)
                    gen["lines"] = len(code.splitlines())
                    script = work / "scripts" / f"{p['id']}-{n}.py"
                    script.write_text(code + "\n", encoding="utf-8")
                    gen["script"] = script.name
                else:
                    gen["error"] = str(answer.get("error", answer) if isinstance(answer, dict) else answer)[:160]
                print(f"{p['id']:<14} #{n} HTTP {status} {gen['seconds']:5.1f}s "
                      f"{'check PASS' if status == 200 and not gen.get('check') else gen.get('check') or gen.get('error')}",
                      flush=True)
                gens.append(gen)
    finally:
        revoke(issuer, tokens.get("refresh_token", ""))

    scripts = [work / "scripts" / gen["script"] for gen in gens if gen.get("script") and not gen.get("check")]
    replay = _blender_results(args.blender, ADDON, scripts, str(work / "renders") if args.render else "")
    runs = []
    for gen in gens:
        blender = dict(replay.get(gen.get("script", ""), {}))
        if blender.get("render"):
            blender["render"] = os.path.basename(blender["render"])  # no workstation path in the committed results
        ok, reason = judge_run(gen, blender)
        runs.append({**{k: v for k, v in gen.items() if k != "check"}, "check": gen.get("check", []),
                     "blender": blender, "ok": ok, "reason": reason})
    summary = aggregate(runs, args.repeats)
    report = {"date": datetime.date.today().isoformat(), "persona": args.persona, "gateway": gateway,
              "repeats": args.repeats, **summary, "runs": runs}
    for p in summary["prompts"]:
        print(f"{'READY' if p['stage_ready'] else '-----'} {p['id']:<14} {p['successes']}/{p['runs']} "
              f"{p['mean_seconds']}s  {p['reasons'][-1]}")
    print(f"RESULT: {summary['successes']}/{summary['runs']} runs succeed; stage-ready: {', '.join(summary['stage_ready'])}")
    if args.results:
        pathlib.Path(args.results).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
