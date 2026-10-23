#!/usr/bin/env python3
"""Admit a zuno-demo-agents OKF release (ADR-0580, WP-160).

The platform consumes one release of startxfr/zuno-demo-agents: the corp
artifact pinned in platform/okf/agents.lock, which indexes one artifact per
agent (ADR-0577). Nothing is trusted because of where it came from:

    verify    the corp artifact and every agent artifact it lists carry a
              keyless signature from the release workflow of the agents
              repository (ADR-0578: publish.yml on a v* tag), checked
              OFFLINE against platform/okf/sigstore/trusted_root.json, plus
              the contract-tests attestation
    extract   verify, then unpack the release into a directory
              (agents/<name>/..., policies/..., okf-index.json)
    validate  the platform can serve what the release asks for: every model
              its routing prefers is bound in provider-routing.yaml, every
              tool its tasks allow has a backend binding, every knowledge
              domain has a database binding (ADR-0576 amendment); and no OKF
              v0.3 bundle widens the release's corp policies (ADR-0579)
    diff      what changes between two extracted releases, for a promotion
              pull request (ADR-0580 clause 2)
    latest    the newest vX.Y.Z release in the registry
    admit     verify + extract + validate the locked release (or --release),
              optionally rewriting the lock (--update-lock)

`--dev` accepts the agents repository's dev identity (publish-dev.yml on
devel/main) instead of the release one, and skips the attestation check:
for testing against devel artifacts only, never for the lock.

Requires `cosign` (v2) and `oras` on PATH. Run from the repository root:
    python3 platform/supply-chain/admit_okf_bundle.py admit
    python3 platform/supply-chain/admit_okf_bundle.py admit --release v0.1.1 --update-lock
"""
from __future__ import annotations

import argparse
import hashlib
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from typing import Dict, Iterator, List, Optional, Set, Tuple

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import okf_narrowing  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "platform" / "okf" / "agents.lock"
SIGSTORE_DIR = REPO_ROOT / "platform" / "okf" / "sigstore"
PROVIDER_ROUTING_PATH = REPO_ROOT / "platform" / "ai-gateway" / "provider-routing.yaml"
TOOL_BINDINGS_PATH = REPO_ROOT / "platform" / "bindings" / "tools" / "tool-bindings.yaml"
# WP-168: knowledge domains are served by UnifAI RAG sources, scoped by a
# `knowledge.*` tag; rag-service and its per-domain database bindings are
# retired. The sources are declared in the unifai chart: `ragSources` in its
# values and the Red Hat documentation catalogue.
UNIFAI_RAG_SOURCE_FILES = (
    (REPO_ROOT / "gitops" / "charts" / "unifai" / "values.yaml", "ragSources"),
    (REPO_ROOT / "gitops" / "charts" / "unifai" / "files" / "redhat-docs.yaml", "sources"),
)

INDEX_MEDIA_TYPE = "application/vnd.zuno.okf.index.v1+json"
SEMVER_TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class AdmissionError(RuntimeError):
    pass


# --- configuration ------------------------------------------------------------

def identity() -> dict:
    return yaml.safe_load((SIGSTORE_DIR / "identity.yaml").read_text(encoding="utf-8"))


def read_lock(path: pathlib.Path = LOCK_PATH) -> Optional[str]:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def write_lock(reference: str, release: str, path: pathlib.Path = LOCK_PATH) -> None:
    if "@sha256:" not in reference:
        raise AdmissionError(f"the lock only takes a digest reference, got {reference}")
    path.write_text(
        "# The zuno-demo-agents release this platform runs (ADR-0580). The only\n"
        "# file that names an agents version; change it through a promotion PR\n"
        "# (.github/workflows/okf-promote.yml) or `make d3 admit agents\n"
        "# RELEASE=vX.Y.Z UPDATE_LOCK=1`, never by hand.\n"
        f"# release {release}\n"
        f"{reference}\n",
        encoding="utf-8")


# --- tools --------------------------------------------------------------------

def run(args: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[pathlib.Path] = None) -> str:
    result = subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode != 0:
        raise AdmissionError(f"{' '.join(args[:3])} ... failed: {(result.stderr or result.stdout).strip()[:800]}")
    return result.stdout


def require(binary: str) -> str:
    path = shutil.which(binary)
    if path is None:
        raise AdmissionError(f"{binary} not found on PATH")
    return path


def _pem(kind: str, raw_b64: str) -> str:
    return f"-----BEGIN {kind}-----\n" + "\n".join(textwrap.wrap(raw_b64, 64)) + f"\n-----END {kind}-----\n"


@contextlib.contextmanager
def offline_trust() -> Iterator[Dict[str, str]]:
    """Environment for `cosign verify --offline` built only from trusted_root.json.

    cosign 2.4 has no --trusted-root flag; it does honour explicit trust
    material through SIGSTORE_ROOT_FILE (Fulcio chain), SIGSTORE_REKOR_PUBLIC_KEY
    and SIGSTORE_CT_LOG_PUBLIC_KEY_FILE. HOME points at an empty directory so
    no TUF cache of the machine is used: what is committed is what is trusted.
    """
    root = json.loads((SIGSTORE_DIR / "trusted_root.json").read_text(encoding="utf-8"))
    ident = identity()
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        certs = [c["rawBytes"] for ca in root["certificateAuthorities"] for c in ca["certChain"]["certificates"]]
        (t / "fulcio.pem").write_text("".join(_pem("CERTIFICATE", c) for c in certs))
        rekor = [x for x in root["tlogs"] if x["baseUrl"] == ident["rekor_url"]]
        ctlog = [x for x in root["ctlogs"] if x["baseUrl"] == ident["ctlog_url"]]
        if not rekor or not ctlog:
            raise AdmissionError("trusted_root.json lacks the Rekor or CT log named in identity.yaml")
        (t / "rekor.pem").write_text(_pem("PUBLIC KEY", rekor[0]["publicKey"]["rawBytes"]))
        (t / "ctlog.pem").write_text(_pem("PUBLIC KEY", ctlog[0]["publicKey"]["rawBytes"]))
        (t / "home").mkdir()
        env = dict(os.environ)
        env.update({
            "HOME": str(t / "home"),
            "SIGSTORE_ROOT_FILE": str(t / "fulcio.pem"),
            "SIGSTORE_REKOR_PUBLIC_KEY": str(t / "rekor.pem"),
            "SIGSTORE_CT_LOG_PUBLIC_KEY_FILE": str(t / "ctlog.pem"),
        })
        yield env


# --- verify / extract -----------------------------------------------------------

def _subject(dev: bool) -> str:
    ident = identity()
    return ident["dev_subject_regexp"] if dev else ident["release_subject_regexp"]


def verify_signature(reference: str, env: Dict[str, str], dev: bool) -> None:
    run([require("cosign"), "verify", "--offline", reference,
         "--certificate-oidc-issuer", identity()["issuer"],
         "--certificate-identity-regexp", _subject(dev), "--output", "json"], env=env)


def verify_attestation(reference: str, env: Dict[str, str]) -> None:
    ident = identity()
    run([require("cosign"), "verify-attestation", "--offline", reference,
         "--type", ident["contract_tests_predicate"],
         "--certificate-oidc-issuer", ident["issuer"],
         "--certificate-identity-regexp", ident["release_subject_regexp"], "--output", "json"], env=env)


def manifest(reference: str) -> dict:
    return json.loads(run([require("oras"), "manifest", "fetch", reference]))


def fetch_blob(repository: str, digest: str) -> bytes:
    result = subprocess.run([require("oras"), "blob", "fetch", f"{repository}@{digest}", "--output", "-"],
                            capture_output=True)
    if result.returncode != 0:
        raise AdmissionError(f"oras blob fetch {repository}@{digest}: {result.stderr.decode()[:400]}")
    return result.stdout


def _layer(reference: str, media_type: str) -> bytes:
    repository = reference.split("@", 1)[0]
    layers = [l for l in manifest(reference).get("layers", []) if l["mediaType"] == media_type]
    if len(layers) != 1:
        raise AdmissionError(f"{reference}: expected one {media_type} layer, found {len(layers)}")
    return fetch_blob(repository, layers[0]["digest"])


def verify(reference: str, dev: bool = False) -> dict:
    """Verify the corp artifact and every agent it lists; return the index."""
    if "@sha256:" not in reference:
        raise AdmissionError(f"verify takes a digest reference, got {reference}")
    with offline_trust() as env:
        verify_signature(reference, env, dev)
        corp = manifest(reference)
        channel = corp.get("annotations", {}).get("zuno.okf.channel")
        if not dev and channel != "release":
            raise AdmissionError(f"{reference} is a {channel!r} artifact, not a release")
        if not dev:
            verify_attestation(reference, env)
        index = json.loads(_layer(reference, INDEX_MEDIA_TYPE))
        for agent in index["agents"]:
            verify_signature(agent["reference"], env, dev)
            if not dev:
                verify_attestation(agent["reference"], env)
    return index


def _untar(data: bytes, dest: pathlib.Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not member.isfile() or not str(target).startswith(str(dest.resolve()) + os.sep):
                raise AdmissionError(f"refusing archive entry {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())


def extract(reference: str, out: pathlib.Path, dev: bool = False) -> dict:
    index = verify(reference, dev)
    _untar(_layer(reference, "application/vnd.zuno.okf.policies.v1.tar+gzip"), out / "policies")
    for agent in index["agents"]:
        _untar(_layer(agent["reference"], "application/vnd.zuno.okf.bundle.v2.tar+gzip"),
               out / "agents" / agent["name"])
    (out / "okf-index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return index


# --- release content ------------------------------------------------------------

def frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    return (yaml.safe_load(text[4:end]) or {}) if text.startswith("---\n") and end > 0 else {}


def load_yaml(path: pathlib.Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}


def served_knowledge_domains() -> Set[str]:
    """The knowledge domains some UnifAI RAG source carries as a tag."""
    domains: Set[str] = set()
    for path, key in UNIFAI_RAG_SOURCE_FILES:
        for source in load_yaml(path).get(key) or []:
            domains.update(t for t in source.get("tags") or [] if str(t).startswith("knowledge."))
    return domains


def agents_view(release: pathlib.Path) -> Dict[str, dict]:
    """agent -> {groups, classification, tasks: {task: {tools, knowledge, quota_class}}}"""
    view: Dict[str, dict] = {}
    index = json.loads((release / "okf-index.json").read_text()) if (release / "okf-index.json").is_file() else {}
    versions = {a["name"]: a["version"] for a in index.get("agents", [])}
    for agent_md in sorted((release / "agents").glob("*/agent.okf.md")):
        z = frontmatter(agent_md).get("zuno") or {}
        tasks = {}
        for task in z.get("tasks") or []:
            tz = frontmatter(agent_md.parent / "tasks" / f"{task}.md").get("zuno") or {}
            tasks[task] = {
                "tools": sorted(tz.get("allowed_tools") or []),
                "knowledge": sorted(tz.get("allowed_knowledge") or []),
                "quota_class": tz.get("quota_class", "standard"),
            }
        view[agent_md.parent.name] = {
            "version": versions.get(agent_md.parent.name, "?"),
            "status": z.get("status", "active"),
            "groups": sorted((z.get("access") or {}).get("groups") or []),
            "classification": (z.get("model") or {}).get("preferred_classification"),
            "tasks": tasks,
        }
    return view


def preferred_models(release: pathlib.Path) -> Dict[Tuple[str, str], List[str]]:
    doc = load_yaml(release / "policies" / "model-routing" / "model-routing-policy.yaml")
    out = {}
    for entry in doc.get("preferences") or []:
        names = list(entry.get("preferred") or []) + list(entry.get("fallback") or []) + list(entry.get("prefer") or [])
        out[(entry["agent"], entry["task"])] = names
    return out


# --- validate -------------------------------------------------------------------

def validate(release: pathlib.Path) -> Tuple[List[str], List[str]]:
    """(errors, warnings): what the platform cannot serve, and what it may not need."""
    errors: List[str] = []
    warnings: List[str] = []

    providers = {p["name"] for p in load_yaml(PROVIDER_ROUTING_PATH).get("providers") or []}
    catalog = {m["name"] for m in load_yaml(release / "policies" / "models" / "model-catalog.yaml").get("models") or []}
    for (agent, task), names in sorted(preferred_models(release).items()):
        for name in names:
            if name not in catalog:
                errors.append(f"model-routing {agent}/{task} prefers {name!r}, absent from the release's model catalog")
            elif name not in providers:
                errors.append(f"model-routing {agent}/{task} prefers {name!r}, not bound in provider-routing.yaml")
    for name in sorted(catalog - providers):
        warnings.append(f"model catalog names {name!r}, which provider-routing.yaml does not bind")

    tool_policy = {t["tool"]: t for t in load_yaml(release / "policies" / "tools" / "tool-policy.yaml").get("tools") or []}
    by_capability = {t.get("capability"): t for t in tool_policy.values()}
    bound: Set[str] = set()
    for b in load_yaml(TOOL_BINDINGS_PATH).get("bindings") or []:
        bound.add(b["capability"])
        bound.update(b.get("aliases") or [])
    domains = served_knowledge_domains()

    for agent, a in sorted(agents_view(release).items()):
        for task, t in sorted(a["tasks"].items()):
            for tool in t["tools"]:
                entry = tool_policy.get(tool) or by_capability.get(tool)
                if entry is None:
                    errors.append(f"{agent}/{task} allows tool {tool!r}, absent from the release's tool policy")
                elif entry.get("capability") not in bound and tool not in bound:
                    errors.append(f"{agent}/{task} allows tool {tool!r} ({entry.get('capability')}), "
                                  f"which has no backend binding in tool-bindings.yaml")
            for domain in t["knowledge"]:
                # Not an error: allowing a domain nothing serves grants no
                # access, the task just retrieves nothing from it.
                if domain not in domains:
                    warnings.append(f"{agent}/{task} allows knowledge domain {domain!r}, "
                                    f"which no UnifAI RAG source serves (no source tagged with it)")
    # OKF v0.3: the release's bundles may only narrow its own corp policies
    # (ADR-0579 clause 5), re-checked here after the agents repository's CI.
    errors += okf_narrowing.check_release(release)
    return errors, warnings


# --- diff -----------------------------------------------------------------------

def _set_change(label: str, old: List[str], new: List[str]) -> List[str]:
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    out = []
    if added:
        out.append(f"{label} +{', '.join(added)}")
    if removed:
        out.append(f"{label} -{', '.join(removed)}")
    return out


def diff(old: Optional[pathlib.Path], new: pathlib.Path) -> str:
    """Markdown summary of what a promotion changes."""
    o = agents_view(old) if old else {}
    n = agents_view(new)
    lines: List[str] = []
    for name in sorted(set(o) | set(n)):
        if name not in o:
            a = n[name]
            lines.append(f"- **{name}** added ({a['version']}): groups {', '.join(a['groups']) or '-'}, "
                         f"tasks {', '.join(sorted(a['tasks'])) or '-'}")
            continue
        if name not in n:
            lines.append(f"- **{name}** removed")
            continue
        a, b = o[name], n[name]
        changes: List[str] = []
        if a["version"] != b["version"]:
            changes.append(f"version {a['version']} -> {b['version']}")
        changes += _set_change("groups", a["groups"], b["groups"])
        if a["classification"] != b["classification"]:
            changes.append(f"classification {a['classification']} -> {b['classification']}")
        changes += _set_change("tasks", list(a["tasks"]), list(b["tasks"]))
        for task in sorted(set(a["tasks"]) & set(b["tasks"])):
            ta, tb = a["tasks"][task], b["tasks"][task]
            changes += _set_change(f"{task} tools", ta["tools"], tb["tools"])
            changes += _set_change(f"{task} knowledge", ta["knowledge"], tb["knowledge"])
            if ta["quota_class"] != tb["quota_class"]:
                changes.append(f"{task} quota {ta['quota_class']} -> {tb['quota_class']}")
        if changes:
            lines.append(f"- **{name}**: " + "; ".join(changes))
    om = preferred_models(old) if old else {}
    nm = preferred_models(new)
    for key in sorted(set(om) | set(nm)):
        before, after = om.get(key) or [], nm.get(key) or []
        if before != after:
            changes = _set_change("models", before, after) or [f"order now {', '.join(after)}"]
            lines.append(f"- model routing `{key[0]}/{key[1]}`: " + "; ".join(changes))
    # Every corp policy file, whatever the release adds (limits, skills, ...).
    def policy_files(root: Optional[pathlib.Path]) -> Dict[str, str]:
        base = root / "policies" if root else None
        if base is None or not base.is_dir():
            return {}
        return {p.relative_to(base).as_posix(): _digest_path(p) for p in sorted(base.rglob("*")) if p.is_file()}
    po, pn = policy_files(old), policy_files(new)
    for rel in sorted(set(po) | set(pn)):
        if rel not in po:
            lines.append(f"- corp policy `{rel}` added")
        elif rel not in pn:
            lines.append(f"- corp policy `{rel}` removed")
        elif po[rel] != pn[rel]:
            lines.append(f"- corp policy `{rel}` changed")
    return "\n".join(lines) if lines else "- no change in agents, routing or corp policies"


def _digest_path(path: Optional[pathlib.Path]) -> Optional[str]:
    if path is None or not path.exists():
        return None
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    return "|".join(f"{p.relative_to(path).as_posix() if path.is_dir() else p.name}:"
                    f"{hashlib.sha256(p.read_bytes()).hexdigest()}" for p in files)


# --- registry -------------------------------------------------------------------

def latest_release(repository: str) -> Tuple[str, str]:
    tags = run([require("oras"), "repo", "tags", repository]).split()
    releases = sorted((t for t in tags if SEMVER_TAG_RE.match(t)),
                      key=lambda t: tuple(int(x) for x in SEMVER_TAG_RE.match(t).groups()))
    if not releases:
        raise AdmissionError(f"{repository} has no vX.Y.Z release tag")
    tag = releases[-1]
    return tag, f"{repository}@{resolve(f'{repository}:{tag}')}"


def resolve(reference: str) -> str:
    return run([require("oras"), "resolve", reference]).strip()


def release_reference(release: str) -> str:
    repository = identity()["corp_repository"]
    return f"{repository}@{resolve(f'{repository}:{release}')}"


# --- cli ------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "extract"):
        p = sub.add_parser(name)
        p.add_argument("reference", nargs="?", help="corp artifact @sha256 reference (default: the lock)")
        p.add_argument("--dev", action="store_true", help="accept dev artifacts (testing only)")
        if name == "extract":
            p.add_argument("--out", type=pathlib.Path, required=True)
    p = sub.add_parser("validate")
    p.add_argument("release_dir", type=pathlib.Path)
    p = sub.add_parser("diff")
    p.add_argument("old_dir", type=pathlib.Path, nargs="?")
    p.add_argument("new_dir", type=pathlib.Path)
    sub.add_parser("latest")
    p = sub.add_parser("admit")
    p.add_argument("--release", help="vX.Y.Z to admit instead of the lock")
    p.add_argument("--update-lock", action="store_true", help="write the admitted release to the lock")
    p.add_argument("--out", type=pathlib.Path, help="keep the extracted release here")
    args = parser.parse_args(argv)

    try:
        if args.command in ("verify", "extract"):
            reference = args.reference or read_lock()
            if not reference:
                raise AdmissionError(f"no reference given and {LOCK_PATH.relative_to(REPO_ROOT)} pins nothing")
            if args.command == "verify":
                index = verify(reference, args.dev)
            else:
                index = extract(reference, args.out, args.dev)
            print(f"VERIFIED {reference}: release {index['release']} ({index['channel']}), "
                  f"{len(index['agents'])} agent(s): "
                  + ", ".join(f"{a['name']} {a['version']}" for a in index["agents"]))
        elif args.command == "validate":
            errors, warnings = validate(args.release_dir)
            for w in warnings:
                print(f"  ! {w}")
            for e in errors:
                print(f"  ✗ {e}")
            if errors:
                print(f"\nRESULT: FAIL - the platform cannot serve this release ({len(errors)} issue(s)).")
                return 1
            print("RESULT: PASS - every model, tool and knowledge domain of the release is bound.")
        elif args.command == "diff":
            print(diff(args.old_dir, args.new_dir))
        elif args.command == "latest":
            tag, reference = latest_release(identity()["corp_repository"])
            print(f"{tag} {reference}")
        else:
            if args.release:
                reference, release = release_reference(args.release), args.release
            else:
                reference = read_lock()
                if not reference:
                    raise AdmissionError(f"{LOCK_PATH.relative_to(REPO_ROOT)} pins nothing: give --release")
                release = None
            with tempfile.TemporaryDirectory() as tmp:
                out = args.out or pathlib.Path(tmp)
                index = extract(reference, out)
                errors, warnings = validate(out)
                for w in warnings:
                    print(f"  ! {w}")
                for e in errors:
                    print(f"  ✗ {e}")
                if errors:
                    print(f"\nRESULT: FAIL - {reference} is signed but the platform cannot serve it.")
                    return 1
            release = release or f"v{index['release']}"
            if args.update_lock:
                write_lock(reference, release)
                print(f"locked {release}: {reference}")
            print(f"RESULT: PASS - {release} ({reference}) is verified and servable.")
    except AdmissionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
