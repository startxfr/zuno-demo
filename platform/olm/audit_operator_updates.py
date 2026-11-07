#!/usr/bin/env python3
"""Which OLM operators of a cluster can be updated, and how. Read-only.

Motivation (demo333, 2026-11-04): every Subscription reported `AtLatestKnown`, yet five operators
had newer versions: RHOAI and GitOps behind a Manual InstallPlan nobody approved, rhcl stuck at
the head of a channel (`stable`) that stopped at 1.4.3 while `stable-1.5` serves 1.5.0, and
authorino, limitador and dns frozen because rhcl 1.4.3 requires them at an exact version
(`olm.package.required`). `AtLatestKnown` only means "no candidate in this channel".

For every Subscription this reports:

- the installed CSV and the head of its channel, read from the PackageManifest of ITS catalog
  (`package@catalog`, never by name alone: community and Red Hat homonyms are different
  operators);
- InstallPlans waiting for approval in its namespace;
- other channels of the same package whose head is newer than the current channel's head
  (pre-releases such as `-ea.2` marked);
- the CSVs that pin it through `olm.package.required`, which is why OLM leaves it behind;
- a package its catalog no longer serves (ADR-0558).

Input is one JSON object on stdin, `{"subscriptions": [...], "packagemanifests": [...],
"installplans": [...], "csvs": [...]}` (the `items` of each list; `csvs` only needs the installed
CSVs), or `--oc-context <context>` to read it with `oc`.

Exit 0 when every operator is at the head of its channel with nothing pending and no newer
channel, 1 when an update is available (or a package has vanished), 2 when it could not run.
`--format json` prints the rows; `--format known-good` prints the installed set as YAML (the
WP-145 known-good file), with the support class of each operator (ADR-0607 clause 1).

`--against <known-good file>` is the gate of ADR-0607 clause 8: exit 3 when a pre-GA operator
(tech-preview, early-access, alpha, staging) runs another version than the recorded one, when a
Subscription is missing from the file, or when a recorded operator is not installed. A GA or
community operator on Automatic approval moves by design; its difference is reported, not failed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

PRERELEASE_TAGS = ("ea", "rc", "tp", "alpha", "beta", "dev", "ec", "pre")
# ADR-0607 clause 1. The classes a version gate holds to the recorded version.
PRE_GA_CLASSES = ("tech-preview", "early-access", "alpha", "staging")
EXIT_KNOWN_GOOD_DRIFT = 3
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)(?:-([0-9A-Za-z.\-]+))?")


def version_of(csv_name: Optional[str]) -> Optional[str]:
    """The version part of a CSV name: `rhods-operator.3.5.2` -> `3.5.2`,
    `aap-operator.v2.7.0-0.17` -> `2.7.0-0.17`."""
    if not csv_name:
        return None
    rest = csv_name.split(".", 1)[1] if "." in csv_name else csv_name
    m = _VERSION_RE.search(rest)
    if not m:
        return None
    return m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")


def is_prerelease(version: Optional[str]) -> bool:
    if not version or "-" not in version:
        return False
    suffix = version.split("-", 1)[1].lower()
    return suffix.startswith(PRERELEASE_TAGS)


def version_key(version: Optional[str]) -> Tuple:
    """Sort key. A pre-release (`3.6.0-ea.2`) sorts before its release, a build suffix
    (`26.6.7-opr.3`, `4.22.0-202610271454`) after it."""
    if not version:
        return ((-1,),)
    core, _, suffix = version.partition("-")
    nums = tuple(int(p) for p in core.split("."))
    nums = nums + (0,) * (4 - len(nums))
    flag = 1 if not suffix else (0 if is_prerelease(version) else 2)
    tokens = tuple((0, int(t)) if t.isdigit() else (1, t) for t in re.split(r"[.\-]", suffix) if t)
    return (nums, flag, tokens)


def _required_pins(csvs: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """package -> ["rhcl-operator.v1.4.3 requires 1.4.3", ...] from olm.package.required."""
    pins: Dict[str, List[str]] = {}
    for csv in csvs:
        raw = ((csv.get("metadata") or {}).get("annotations") or {}).get("operatorframework.io/properties")
        if not raw:
            continue
        try:
            props = json.loads(raw).get("properties") or []
        except ValueError:
            continue
        for p in props:
            if p.get("type") == "olm.package.required":
                v = p.get("value") or {}
                pin = f"{csv['metadata']['name']} requires {v.get('versionRange')}"
                # A CSV can list the same requirement twice, and two Subscriptions can share a CSV.
                if pin not in pins.setdefault(v.get("packageName"), []):
                    pins[v.get("packageName")].append(pin)
    return pins


def audit(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    manifests = {(p["metadata"]["name"], (p.get("status") or {}).get("catalogSource")): p
                 for p in doc.get("packagemanifests") or []}
    pending: Dict[str, List[str]] = {}
    for plan in doc.get("installplans") or []:
        spec, status = plan.get("spec") or {}, plan.get("status") or {}
        if spec.get("approved") is False and status.get("phase") == "RequiresApproval":
            pending.setdefault(plan["metadata"]["namespace"], []).extend(
                f"{plan['metadata']['name']}:{c}" for c in spec.get("clusterServiceVersionNames") or [])
    pins = _required_pins(doc.get("csvs") or [])

    rows: List[Dict[str, Any]] = []
    for sub in doc.get("subscriptions") or []:
        spec, status = sub.get("spec") or {}, sub.get("status") or {}
        pkg, source, channel = spec.get("name"), spec.get("source"), spec.get("channel")
        installed = status.get("installedCSV")
        installed_v = version_of(installed)
        row: Dict[str, Any] = {
            "namespace": sub["metadata"]["namespace"], "package": pkg, "catalog": source,
            "channel": channel, "approval": spec.get("installPlanApproval", "Automatic"),
            "installed": installed_v, "channel_head": None, "newer_channels": [],
            "pending_installplans": pending.get(sub["metadata"]["namespace"], []),
            "pinned_by": pins.get(pkg, []), "findings": [],
        }
        pm = manifests.get((pkg, source))
        if pm is None:
            row["findings"].append(f"package {pkg} is not served by catalog {source} (ADR-0558: frozen, no update path)")
            rows.append(row)
            continue
        heads = {c["name"]: version_of(c.get("currentCSV")) for c in (pm.get("status") or {}).get("channels") or []}
        head = heads.get(channel)
        if channel not in heads:
            row["findings"].append(f"channel {channel} is not published by {pkg}@{source}")
        row["channel_head"] = head
        if head and version_key(head) > version_key(installed_v):
            how = "pending InstallPlan" if row["pending_installplans"] else (
                "pinned by " + "; ".join(row["pinned_by"]) if row["pinned_by"] else "OLM has not moved")
            row["findings"].append(f"{installed_v} -> {head} in channel {channel} ({how})")
        floor = head or installed_v
        newer = sorted(((n, v) for n, v in heads.items() if v and version_key(v) > version_key(floor)),
                       key=lambda nv: version_key(nv[1]), reverse=True)
        # One entry per distinct version: several channels (stable-3.x, eus-3.5) often share a head.
        seen = set()
        for name, v in newer:
            if v in seen:
                continue
            seen.add(v)
            row["newer_channels"].append({"channel": name, "head": v, "prerelease": is_prerelease(v)})
        if row["newer_channels"]:
            best = row["newer_channels"][0]
            row["findings"].append(f"newer channel {best['channel']} -> {best['head']}"
                                   + (" (pre-release)" if best["prerelease"] else ""))
        rows.append(row)
    rows.sort(key=lambda r: (r["package"] or "", r["namespace"]))
    return rows


def render_text(rows: List[Dict[str, Any]]) -> str:
    out = []
    for r in rows:
        mark = "UPDATE" if r["findings"] else "ok"
        newer = ", ".join(f"{c['channel']}:{c['head']}{'*' if c['prerelease'] else ''}" for c in r["newer_channels"])
        out.append(f"{mark:6} {r['package']}@{r['catalog']} [{r['namespace']}] channel={r['channel']} "
                   f"approval={r['approval']} installed={r['installed']} head={r['channel_head']}"
                   + (f" newer={newer}" if newer else ""))
        for f in r["findings"]:
            out.append(f"         - {f}")
    out.append("(* = pre-release)")
    return "\n".join(out)


def support_class(catalog: Optional[str], channel: Optional[str], version: Optional[str]) -> str:
    """ADR-0607 clause 1: ga, tech-preview, early-access, alpha, staging, or community (a community
    catalog's operator on a stable channel: GA-like lifecycle, no vendor support)."""
    ch, v = (channel or "").lower(), (version or "").lower()
    if "staging" in ch:
        return "staging"
    if "alpha" in ch or re.search(r"-alpha", v):
        return "alpha"
    if "beta" in ch or "early" in ch or re.search(r"-ea(\.|$)", v):
        return "early-access"
    if "preview" in ch or re.search(r"-tp(\.|$)", v):
        return "tech-preview"
    if catalog == "community-operators":
        return "community"
    return "ga"


def compare_known_good(rows: List[Dict[str, Any]], known: Dict[str, Any]) -> List[str]:
    """Findings of the known-good gate, each prefixed FAIL or INFO (ADR-0607 clause 8)."""
    recorded = {(o.get("package"), o.get("namespace")): o for o in known.get("operators") or []}
    findings: List[str] = []
    seen = set()
    for r in rows:
        key = (r["package"], r["namespace"])
        seen.add(key)
        o = recorded.get(key)
        cls = support_class(r["catalog"], r["channel"], r["installed"])
        if o is None:
            findings.append(f"FAIL {r['package']} [{r['namespace']}] ({cls}) is installed but not in the known-good set")
        elif str(o.get("version")) != str(r["installed"]):
            sev = "FAIL" if cls in PRE_GA_CLASSES else "INFO"
            findings.append(f"{sev} {r['package']} [{r['namespace']}] ({cls}) installed {r['installed']}, "
                            f"known-good {o.get('version')}")
    for key, o in sorted(recorded.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if key not in seen:
            findings.append(f"FAIL {o.get('package')} [{o.get('namespace')}] is in the known-good set but not installed")
    return findings


def render_known_good(rows: List[Dict[str, Any]], cluster: str) -> str:
    lines = [f"# Known-good operator set (WP-145), generated by platform/olm/audit_operator_updates.py",
             f"cluster: {cluster}",
             f"measured: {datetime.datetime.now(datetime.timezone.utc).date().isoformat()}", "operators:"]
    for r in rows:
        lines += [f"  - package: {r['package']}", f"    catalog: {r['catalog']}",
                  f"    namespace: {r['namespace']}", f"    channel: {r['channel']}",
                  f"    approval: {r['approval']}",
                  f"    class: {support_class(r['catalog'], r['channel'], r['installed'])}",
                  f"    version: \"{r['installed']}\""]
    return "\n".join(lines) + "\n"


def collect_with_oc(context: str) -> Dict[str, Any]:
    def get(*args: str) -> Dict[str, Any]:
        res = subprocess.run(["oc", "--context", context, "get", *args, "-o", "json"],
                             check=True, capture_output=True, text=True)
        return json.loads(res.stdout)
    subs = get("subscriptions.operators.coreos.com", "-A")["items"]
    csvs = []
    for s in subs:
        name = (s.get("status") or {}).get("installedCSV")
        if name:
            try:
                csvs.append(get("clusterserviceversion", "-n", s["metadata"]["namespace"], name))
            except subprocess.CalledProcessError:
                pass
    return {"subscriptions": subs, "csvs": csvs,
            "packagemanifests": get("packagemanifests.packages.operators.coreos.com")["items"],
            "installplans": get("installplans.operators.coreos.com", "-A")["items"]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--oc-context", help="read the cluster with `oc --context` instead of stdin")
    parser.add_argument("--format", choices=("text", "json", "known-good"), default="text")
    parser.add_argument("--cluster", default="unknown", help="cluster name written in the known-good file")
    parser.add_argument("--against", help="known-good file to gate on (ADR-0607 clause 8); exit 3 on a FAIL finding")
    args = parser.parse_args(argv)
    try:
        doc = collect_with_oc(args.oc_context) if args.oc_context else json.load(sys.stdin)
        rows = audit(doc)
    except (ValueError, KeyError, TypeError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": f"could not run: {exc}"}))
        return 2
    if args.format == "json":
        print(json.dumps({"ok": not any(r["findings"] for r in rows), "operators": rows}, indent=2))
    elif args.format == "known-good":
        print(render_known_good(rows, args.cluster), end="")
    else:
        print(render_text(rows))
    if args.against:
        import yaml

        with open(args.against) as fh:
            gate = compare_known_good(rows, yaml.safe_load(fh) or {})
        print(f"known-good gate against {args.against}:")
        for line in gate or ["PASS every operator matches the known-good set"]:
            print("  " + line)
        if any(line.startswith("FAIL") for line in gate):
            return EXIT_KNOWN_GOOD_DRIFT
    return 1 if any(r["findings"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
