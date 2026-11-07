#!/usr/bin/env python3
"""ADR-0603 M16 (WP-226): render a ledgered release's image digests into the
chart values, so what runs is the bytes that were built, signed and recorded.

`make d3 release TAG=<tag>` (ansible/playbooks/day3_release.yml) builds every
component at `<component>:<tag>`, signs it through RHTAS and appends the
digests to `pinned-releases.yaml`. Until now nothing consumed that ledger: every
chart rendered `repository:latest`. This script is the consumer. For each pin of
one release it writes the pin's digest into the `digest` key next to the
ledgered `tag` field (`image.tag` -> `image.digest`, `images.mlops.tag` ->
`images.mlops.digest`, `okf.fetch.image.tag` -> `okf.fetch.image.digest`). The
charts' imageRef helper then renders `repository@sha256:...`, pulls
`IfNotPresent` and drops the `:latest` image trigger (a trigger would rewrite
the pinned image back to whatever `:latest` points at).

Rendering is a deployment decision, not a bookkeeping step: once merged to
`main`, ArgoCD rolls the pinned digests and a later `:latest` build no longer
redeploys those components (ADR-0059's auto-redeploy stops for them). It is
therefore never run implicitly: `make d3 release TAG=<tag> RENDER_DIGESTS=1`,
or this script by hand, each with the user's go for that release.
`--clear` returns every chart to the `:latest` path.

Rules (each refusal changes nothing on disk):

- the release must exist in the ledger; its last entry for that tag is used;
- every pin must carry a `sha256:<64 hex>` digest and `signed: true` (the
  historical `pin_release.py` entries with `digest: null` are refused);
- every target `digest` key must already exist in the chart values (a chart
  whose templates cannot render a digest is not silently half-pinned).

The edit is textual, line by line, so every comment in the values files
survives; `yaml.safe_load` only validates the result.

`--check` (no writes, wired into lint.yml): every non-empty `digest` in a chart
values file is well-formed and equals a signed ledger pin for that same chart and
field.

Run from the repository root:

    python3 platform/supply-chain/render_release_digests.py --release v0.15.0 [--dry-run]
    python3 platform/supply-chain/render_release_digests.py --clear [--dry-run]
    python3 platform/supply-chain/render_release_digests.py --check
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "platform" / "supply-chain" / "pinned-releases.yaml"
CHARTS_GLOB = "gitops/charts/*/values.yaml"
FIRST_PARTY = "/zuno-ai-build/"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$")


class RenderError(Exception):
    pass


def digest_path(tag_path: str) -> str:
    parts = tag_path.split(".")
    if parts[-1] != "tag":
        raise RenderError(f"ledger path {tag_path!r} does not end in .tag")
    return ".".join(parts[:-1] + ["digest"])


def _scalar_lines(lines: Sequence[str]) -> Iterable[Tuple[int, str, str]]:
    """Yield (line index, dotted key path, raw value) for every block-mapping key.

    Enough YAML for chart values files: block mappings, comments, list items
    (whose keys are skipped) and block scalars (whose bodies are skipped)."""
    stack: List[Tuple[int, str]] = []
    skip_deeper_than: Optional[int] = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if skip_deeper_than is not None:
            if indent > skip_deeper_than:
                continue
            skip_deeper_than = None
        if stripped.startswith("- "):
            # A list item: none of the rendered fields lives inside a list.
            skip_deeper_than = indent
            continue
        match = KEY_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        rest = match.group("rest").split(" #", 1)[0].strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [key])
        if rest == "":
            stack.append((indent, key))
        elif rest[:1] in ("|", ">"):
            skip_deeper_than = indent
        yield index, path, rest


def set_scalar(text: str, path: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    hits = [i for i, p, _ in _scalar_lines(lines) if p == path]
    if not hits:
        raise RenderError(f"no {path!r} key")
    if len(hits) > 1:
        raise RenderError(f"{path!r} appears {len(hits)} times")
    i = hits[0]
    match = KEY_RE.match(lines[i])
    assert match
    newline = "\n" if lines[i].endswith("\n") else ""
    lines[i] = f'{match.group("indent")}{match.group("key")}: "{value}"{newline}'
    return "".join(lines)


def _lookup(doc: Any, path: str) -> Any:
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def load_ledger(path: pathlib.Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text()) or {}).get("releases") or []


def release_entry(releases: List[Dict[str, Any]], tag: str) -> Dict[str, Any]:
    entries = [r for r in releases if str(r.get("release_tag")) == tag]
    if not entries:
        raise RenderError(f"release {tag!r} is not in the ledger (run `make d3 release TAG={tag}` first)")
    return entries[-1]


def plan_release(root: pathlib.Path, entry: Dict[str, Any]) -> Dict[pathlib.Path, str]:
    """Return {values file: new text}; raise RenderError on any refusal."""
    pins = entry.get("pins") or []
    if not pins:
        raise RenderError(f"release {entry.get('release_tag')!r} has no pins")
    problems: List[str] = []
    texts: Dict[pathlib.Path, str] = {}
    for pin in pins:
        label = f"{pin.get('chart_values')}:{pin.get('path')}"
        digest = pin.get("digest")
        if not isinstance(digest, str) or not DIGEST_RE.match(digest):
            problems.append(f"{label}: digest {digest!r} is not sha256:<64 hex>")
            continue
        if pin.get("signed") is not True:
            problems.append(f"{label}: not recorded signed: true")
            continue
        values = root / str(pin["chart_values"])
        if not values.is_file():
            problems.append(f"{label}: {values} does not exist")
            continue
        try:
            target = digest_path(str(pin["path"]))
            texts[values] = set_scalar(texts.get(values, values.read_text()), target, digest)
        except RenderError as exc:
            problems.append(f"{label}: {exc}")
    if problems:
        raise RenderError("refused, nothing written:\n  " + "\n  ".join(problems))
    for values, text in texts.items():
        doc = yaml.safe_load(text)
        for pin in pins:
            if root / str(pin["chart_values"]) == values:
                if _lookup(doc, digest_path(str(pin["path"]))) != pin["digest"]:
                    raise RenderError(f"{values}: {pin['path']} did not render (internal error)")
    return texts


def rendered_digests(root: pathlib.Path) -> List[Tuple[str, str, str]]:
    """(chart_values, digest path, value) for every `digest` key of a first-party
    image map (its sibling `repository` is in the zuno-ai-build build namespace).
    Third-party images pinned by digest by hand (mcp-k8s) are not release output."""
    found = []
    for values in sorted(root.glob(CHARTS_GLOB)):
        text = values.read_text()
        doc = yaml.safe_load(text) or {}
        for _, path, raw in _scalar_lines(text.splitlines(keepends=True)):
            if not path.endswith(".digest"):
                continue
            repository = _lookup(doc, path[: -len("digest")] + "repository")
            if not isinstance(repository, str) or FIRST_PARTY not in repository:
                continue
            found.append((str(values.relative_to(root)), path, raw.strip("\"'")))
    return found


def plan_clear(root: pathlib.Path) -> Dict[pathlib.Path, str]:
    texts: Dict[pathlib.Path, str] = {}
    for chart_values, path, value in rendered_digests(root):
        if value:
            values = root / chart_values
            texts[values] = set_scalar(texts.get(values, values.read_text()), path, "")
    return texts


def check(root: pathlib.Path, releases: List[Dict[str, Any]]) -> List[str]:
    signed = {
        (str(p.get("chart_values")), digest_path(str(p.get("path"))), p.get("digest"))
        for r in releases
        for p in (r.get("pins") or [])
        if p.get("signed") is True and str(p.get("path", "")).endswith(".tag")
    }
    problems = []
    for chart_values, path, value in rendered_digests(root):
        if not value:
            continue
        if not DIGEST_RE.match(value):
            problems.append(f"{chart_values}: {path} {value!r} is not sha256:<64 hex>")
        elif (chart_values, path, value) not in signed:
            problems.append(f"{chart_values}: {path} {value} is not a signed pin of any ledgered release "
                            "(digests are rendered by render_release_digests.py, never hand-edited)")
    return problems


def _write(texts: Dict[pathlib.Path, str], root: pathlib.Path, dry_run: bool) -> None:
    for values in sorted(texts):
        rel = values.relative_to(root)
        if dry_run:
            print(f"would write {rel}")
        else:
            values.write_text(texts[values])
            print(f"wrote {rel}")


def main(argv: Optional[Sequence[str]] = None, root: pathlib.Path = REPO_ROOT,
         ledger: Optional[pathlib.Path] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--release", help="release tag to render from the ledger")
    mode.add_argument("--clear", action="store_true", help="empty every rendered digest (back to :latest)")
    mode.add_argument("--check", action="store_true", help="validate rendered digests against the ledger")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    releases = load_ledger(ledger or root / "platform" / "supply-chain" / "pinned-releases.yaml")
    try:
        if args.check:
            problems = check(root, releases)
            for problem in problems:
                print(f"FAIL {problem}")
            pinned = [d for d in rendered_digests(root) if d[2]]
            print(f"{len(pinned)} rendered digest(s), {len(problems)} problem(s)")
            return 1 if problems else 0
        if args.clear:
            texts = plan_clear(root)
        else:
            texts = plan_release(root, release_entry(releases, args.release))
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _write(texts, root, args.dry_run)
    if not texts:
        print("nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
