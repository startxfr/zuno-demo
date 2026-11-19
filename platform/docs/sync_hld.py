#!/usr/bin/env python3
"""Bring every copy of the platform map (HLD) back to the reference in docs/architecture/README.md.

The map is copied into the architecture README and into every demo scenario page; only the highlight lines
(`classDef focus ...;` and `class <NODE> focus;`) differ from page to page. Edit the reference, then run:

    python3 platform/docs/sync_hld.py            # rewrite the copies
    python3 platform/docs/sync_hld.py --check    # list the pages that would change, change nothing (exit 1 if any)

Each copy keeps its own highlight lines. check_docs.py fails on a copy that differs from the reference.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check_docs  # noqa: E402


def sync_page(text: str, reference: str) -> str:
    """The page text with each platform-map block replaced by the reference body plus the block's own highlight lines."""
    out, pos = [], 0
    for m in check_docs.MERMAID_BLOCK_RE.finditer(text):
        block = m.group(1)
        if not block.startswith(check_docs.HLD_SIGNATURE):
            continue
        focus = [l for l in block.split("\n") if check_docs.HLD_FOCUS_LINE_RE.match(l)]
        new = reference + ("\n\n" + "\n".join(focus) if focus else "") + "\n"
        out.append(text[pos:m.start(1)])
        out.append(new)
        pos = m.end(1)
    out.append(text[pos:])
    return "".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="only list the pages that would change")
    args = ap.parse_args(argv)
    root = check_docs.REPO_ROOT
    refs = check_docs.hld_blocks((root / check_docs.HLD_REFERENCE).read_text())
    if len(refs) != 1:
        print(f"{check_docs.HLD_REFERENCE} must hold exactly one platform map, found {len(refs)}", file=sys.stderr)
        return 2
    reference = check_docs.hld_without_focus(refs[0])
    changed = []
    for path in sorted((root / "docs").rglob("*.md")):
        rel = str(path.relative_to(root))
        if rel == check_docs.HLD_REFERENCE:
            continue
        text = path.read_text()
        new = sync_page(text, reference)
        if new != text:
            changed.append(rel)
            if not args.check:
                path.write_text(new)
    for rel in changed:
        print(("would change " if args.check else "rewrote ") + rel)
    print(f"{len(changed)} page(s) {'differ' if args.check else 'rewritten'}; the reference is {check_docs.HLD_REFERENCE}")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
