#!/usr/bin/env python3
"""Verify the UnifAI runtime images by digest, signature and attestations (ADR-0586).

The UnifAI stack runs images of `quay.io/zuno/unifai-*` that the fork builds. Before
the `unifai` role applies them, and again when `make d1 check unifai` compares what
runs, this script requires of every image:

1. a reference **pinned by digest** (`repo@sha256:...`): a tag is mutable, so it is
   refused as unpinned;
2. a keyless **signature** whose certificate identity is the fork's publish workflow
   (platform/supply-chain/image-identities.yaml), checked offline against the
   committed Sigstore trusted root - the same machinery as the OKF releases
   (admit_okf_bundle.offline_trust);
3. a **provenance** attestation and a signed **SBOM** artifact, by the same identity. The
   SBOM (tens of MB) is too large for the public Rekor log as an attestation, so the fork
   publishes it as an OCI artifact tagged `sha256-<image digest>.sbom` and signs that.

A development build (`devel` branch workflow) is accepted only with --accept-dev; a
release (a `vX.Y.Z` tag workflow) always. Third-party images (databases, queues) are
out of this policy: they are pinned by digest elsewhere and carry no publisher
signature.

Run from the repository root (needs cosign v2 on PATH and the registry):

    python3 platform/supply-chain/verify_unifai_images.py --ref quay.io/zuno/unifai-ui@sha256:... [--accept-dev]
    python3 platform/supply-chain/verify_unifai_images.py --refs-json refs.json
    oc get pods -n zuno-unifai -o json | python3 .../verify_unifai_images.py --refs-json refs.json --pods -

Exit code 0 when everything verifies, 1 otherwise (the JSON on stdout lists every
failure, never just the first). 2 for a usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Optional, Set

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402

IDENTITIES_PATH = HERE / "image-identities.yaml"
DIGEST_RE = re.compile(r"@(sha256:[0-9a-f]{64})$")
FAMILY_PREFIX = "quay.io/zuno/unifai-"
OPERATOR_PREFIX = "quay.io/zuno/unifai-operator"


class ImageError(ValueError):
    """A reference this policy cannot judge (not an UnifAI image, or not pinned)."""


@dataclass
class Result:
    reference: str
    ok: bool
    reason: str = ""


def load_identities(path: pathlib.Path = IDENTITIES_PATH) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("issuer", "images", "operator", "attestations"):
        if key not in doc:
            raise ImageError(f"{path}: missing '{key}'")
    return doc


def repository(reference: str) -> str:
    """The repository of a reference, without tag or digest (a registry port is not a tag)."""
    name = reference.split("@", 1)[0]
    slash = name.rfind("/")
    colon = name.rfind(":")
    return name[:colon] if colon > slash else name


def kind_of(reference: str) -> str:
    repo = repository(reference)
    if repo.startswith(OPERATOR_PREFIX):
        return "operator"
    if repo.startswith(FAMILY_PREFIX):
        return "images"
    raise ImageError(f"{reference}: not an UnifAI image of this policy (expected {FAMILY_PREFIX}*)")


def digest_of(reference: str) -> str:
    match = DIGEST_RE.search(reference)
    if not match:
        raise ImageError(f"{reference}: not pinned by digest (a tag is mutable; pin repo@sha256:...)")
    return match.group(1)


def sbom_reference(reference: str) -> str:
    """Where the fork publishes the SBOM of a pinned image: `<repo>:sha256-<hex>.sbom`."""
    return f"{repository(reference)}:{digest_of(reference).replace(':', '-')}.sbom"


def subject_regexp(identities: dict, kind: str, accept_dev: bool) -> str:
    section = identities[kind]
    parts = [section["release_subject_regexp"]]
    if accept_dev and section.get("dev_subject_regexp"):
        parts.append(section["dev_subject_regexp"])
    return "|".join(f"(?:{p})" for p in parts)


def verify_image(reference: str, env: Dict[str, str], identities: dict, accept_dev: bool = False) -> Result:
    try:
        digest_of(reference)
        kind = kind_of(reference)
    except ImageError as exc:
        return Result(reference, False, str(exc))
    subject = subject_regexp(identities, kind, accept_dev)
    flags = ["--certificate-oidc-issuer", identities["issuer"], "--certificate-identity-regexp", subject,
             "--output", "json"]
    steps = [
        ("signature", ["verify", "--offline", reference] + flags),
        ("provenance", ["verify-attestation", "--type", identities["attestations"]["provenance"],
                        "--offline", reference] + flags),
        ("sbom", ["verify", "--offline", sbom_reference(reference)] + flags),
    ]
    for label, args in steps:
        try:
            admit.run([admit.require("cosign")] + args, env=env)
        except admit.AdmissionError as exc:
            return Result(reference, False, f"{label}: {exc}")
    return Result(reference, True, "signature, provenance and signed sbom verified")


def verify_all(references: Iterable[str], accept_dev: bool = False,
               identities: Optional[dict] = None) -> List[Result]:
    identities = identities or load_identities()
    with admit.offline_trust() as env:
        return [verify_image(ref, env, identities, accept_dev) for ref in references]


def _running_references(pods: dict) -> List[str]:
    """Every distinct `<repository>@sha256:...` of an UnifAI-family image a pod runs."""
    seen: List[str] = []
    for pod in pods.get("items", []):
        status = pod.get("status") or {}
        for entry in (status.get("containerStatuses") or []) + (status.get("initContainerStatuses") or []):
            image_id = re.sub(r"^[a-z-]+://", "", entry.get("imageID") or "")
            if image_id.startswith(FAMILY_PREFIX) and DIGEST_RE.search(image_id) and image_id not in seen:
                seen.append(image_id)
    return seen


def check_pods(pods: dict, pinned_digests: Set[str], verify: Callable[[str], Result]) -> List[str]:
    """Findings for what actually runs: an application image whose digest is not one of
    the pinned ones (drift), and any running UnifAI image, operator included, that does
    not verify. `verify` is called once per distinct running image."""
    findings: List[str] = []
    for reference in _running_references(pods):
        digest = digest_of(reference)
        if kind_of(reference) == "images" and pinned_digests and digest not in pinned_digests:
            findings.append(f"{reference}: runs but is not one of the pinned digests (drift)")
        result = verify(reference)
        if not result.ok:
            findings.append(f"{reference}: {result.reason}")
    return findings


def check_third_party(pods: dict, pinned: Iterable[str]) -> List[str]:
    """Drift of the pinned third-party services (unsigned, pinned only). A live container
    whose repository is one of the pinned references must run exactly one of them. The pod
    spec is read, not the runtime's imageID: for a pinned manifest list the runtime reports
    the digest of the platform manifest, which is never the pin. Pods that ended (Jobs that
    completed before a pin) are ignored."""
    by_repo: Dict[str, Set[str]] = {}
    for ref in pinned:
        by_repo.setdefault(repository(ref), set()).add(ref)
    findings: List[str] = []
    for pod in pods.get("items", []):
        if (pod.get("status") or {}).get("phase") in ("Succeeded", "Failed"):
            continue
        spec = pod.get("spec") or {}
        name = (pod.get("metadata") or {}).get("name", "?")
        for container in (spec.get("containers") or []) + (spec.get("initContainers") or []):
            image = container.get("image") or ""
            allowed = by_repo.get(repository(image))
            if allowed and image not in allowed:
                finding = f"{name}: runs {image}, expected one of the pinned {', '.join(sorted(allowed))} (drift)"
                if finding not in findings:
                    findings.append(finding)
    return findings


def _read_json(arg: str):
    return json.load(sys.stdin) if arg == "-" else json.loads(pathlib.Path(arg).read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", action="append", default=[], help="an image reference, repo@sha256:... (repeatable)")
    parser.add_argument("--refs-json", help="a JSON list of references ('-' for stdin)")
    parser.add_argument("--accept-dev", action="store_true", help="also accept development (devel branch) builds")
    parser.add_argument("--third-party", action="append", default=[],
                        help="a pinned third-party reference (repeatable): with --pods, a pod running another image "
                             "of its repository is drift. Pinned only, never signature-checked")
    parser.add_argument("--pods", help="`oc get pods -o json` output ('-' for stdin): compare what runs")
    args = parser.parse_args(argv)
    if args.refs_json == "-" and args.pods == "-":
        parser.error("--refs-json and --pods cannot both read stdin")
    references = list(args.ref) + (list(_read_json(args.refs_json)) if args.refs_json else [])
    if not references and not args.pods:
        parser.error("give at least one --ref, a --refs-json or --pods")

    identities = load_identities()
    results: List[Result] = []
    pod_findings: List[str] = []
    try:
        with admit.offline_trust() as env:
            cache: Dict[str, Result] = {}

            def verify(ref: str) -> Result:
                if ref not in cache:
                    cache[ref] = verify_image(ref, env, identities, args.accept_dev)
                return cache[ref]

            results = [verify(ref) for ref in references]
            if args.pods:
                pinned = {digest_of(r) for r in references if DIGEST_RE.search(r) and kind_of(r) == "images"}
                pods = _read_json(args.pods)
                pod_findings = check_pods(pods, pinned, verify) + check_third_party(pods, args.third_party)
    except (admit.AdmissionError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    ok = all(r.ok for r in results) and not pod_findings
    print(json.dumps({"ok": ok, "results": [asdict(r) for r in results], "pod_findings": pod_findings}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
