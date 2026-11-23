"""The demo guide: one static page of the console links and the demo catalogue (WP-330, ADR-0627).

`python3 platform/demo/guide.py` writes five files into `gitops/charts/demo-guide/files/`; the chart puts them in a
ConfigMap and nginx serves them. Four are the page itself, copied from `platform/demo/guide/` (index.html, app.css,
app.js, qrcode.min.js). The fifth, data.json, is the only generated one: the console links of `guide-links.json` and
every demo of the catalogue (docs/demo/), read with the parser of `catalogue.py`.

    python3 platform/demo/guide.py                # write the files
    python3 platform/demo/guide.py --check        # exit 1 if the committed files are not what the pages produce
    python3 platform/demo/guide.py --domain apps.other.example --gif-ref main

The GIFs are not copied: a card points at the repository's raw URL (the repository is public). A secret never reaches
the page: the generator refuses an output in which a secret pattern appears, and the page is limited to 700 KB, well
under the 1 MiB of a ConfigMap.

Stdlib only, Python 3.9, like the rest of platform/demo/.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalogue  # noqa: E402

SOURCE_DOMAIN = "apps.demo333.startx.fr"      # how the pages write it; --domain replaces it
DEFAULT_REPO = "startxfr/zuno-demo"
DEFAULT_REF = "devel"
OUT_REL = pathlib.Path("gitops") / "charts" / "demo-guide" / "files"
SITE_FILES = ("index.html", "app.css", "app.js", "qrcode.min.js")   # copied from platform/demo/guide/
DATA_FILE = "data.json"
MAX_BYTES = 700_000          # the whole ConfigMap is limited to 1 MiB
MAX_ROLE = 420               # characters of a persona's "role in this demo"
MAX_SHOWS = 360

GROUPS = (   # (catalogue layer, id, title)
    ("experiences", "experiences", "Experiences"),
    ("governance", "governance", "Governance"),
    ("rhoai", "rhoai", "OpenShift AI and models"),
    ("foundation", "foundation", "Foundation and trust"),
    ("resilience", "resilience", "Resilience"),
    ("workshop", "workshops", "Workshops"),
)

URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+\." + re.escape(SOURCE_DOMAIN) + r"[^\s`)>\"'|\]]*")
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;)\"]{6,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
)


class GuideError(RuntimeError):
    """The page cannot be produced as asked."""


def clean(text: str) -> str:
    """Markdown to plain text: links keep their label, emphasis and code marks go, spaces collapse."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = text.replace("**", "").replace("`", "").replace("\\|", "|")
    return re.sub(r"\s+", " ", text).strip()


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.")
    return cut + "…"


def title_of(page: catalogue.Page) -> str:
    first = page.text.lstrip().splitlines()[0] if page.text.strip() else page.id
    return clean(re.sub(r"^#\s*(Scenario|Workshop)\s*:\s*", "", first))


def message_of(page: catalogue.Page) -> str:
    """The `**The message:**` line of the Introduction; else the first paragraph of the Introduction."""
    intro = page.section("Introduction")
    if not intro:
        return ""
    body = intro.text
    found = re.search(r"\*\*The message:?\*\*:?\s*(.+?)(?:\n\s*\n|$)", body, re.S)
    if found:
        return clean(found.group(1)).strip('"“”')
    for para in re.split(r"\n\s*\n", body):
        if para.strip() and not para.lstrip().startswith(("!", "|", ">", "-")):
            return shorten(clean(para), 300)
    return ""


def personas_of(page: catalogue.Page) -> List[Dict[str, str]]:
    sec = page.section("Personas")
    if not sec:
        return []
    for table in catalogue.tables_of(sec.lines, sec.line):
        head = [clean(c).lower() for c in table.header]
        if not head or not head[0].startswith("persona"):
            continue
        profile_col = next((i for i, h in enumerate(head) if h.startswith("profile")), None)
        role_col = next((i for i, h in enumerate(head) if h.startswith("role in")), len(head) - 1)
        rows = []
        for _line, cells in table.rows:
            if not cells:
                continue
            rows.append({
                "name": clean(cells[0]),
                "profile": shorten(clean(cells[profile_col]), 160) if profile_col is not None and profile_col < len(cells) else "",
                "role": shorten(clean(cells[role_col]), MAX_ROLE) if role_col < len(cells) else "",
            })
        return rows
    return []


def urls_of(text: str, domain: str) -> List[str]:
    seen: List[str] = []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(".,;:").replace(SOURCE_DOMAIN, domain)
        if url not in seen:
            seen.append(url)
    return seen


def shows_by_id(root: pathlib.Path) -> Dict[str, str]:
    """page stem -> the `Shows` cell of the README catalogue tables (a one-line description of the demo)."""
    readme = root / "docs" / "demo" / "README.md"
    result: Dict[str, str] = {}
    if not readme.exists():
        return result
    for line in readme.read_text(encoding="utf-8").splitlines():
        found = re.match(r"\|\s*\[[^\]]+\]\(([^)]+\.md)\)\s*\|", line)
        if not found:
            continue
        cells = catalogue.split_cells(line)
        if len(cells) >= 2:
            result[pathlib.PurePosixPath(found.group(1)).stem] = shorten(clean(cells[1]), MAX_SHOWS)
    return result


def build_demo(entry: catalogue.Entry, root: pathlib.Path, shows: Dict[str, str], related: Dict[str, List[str]],
               opts: argparse.Namespace) -> dict:
    page = catalogue.load(entry)
    rel = entry.path.relative_to(root).as_posix()
    gif = root / "docs" / "assets" / "img" / "demo" / f"{entry.id}.gif"
    urls = urls_of(page.text, opts.domain)
    # The consoles curated for a demo whose page names none, or only some: shown apart, as "related".
    related_urls = [f"https://{sub}.{opts.domain}" for sub in related.get(entry.id, [])]
    related_urls = [u for u in related_urls if not any(x == u or x.startswith(u + "/") for x in urls)]
    return {
        "id": entry.id,
        "title": title_of(page),
        "kind": entry.kind,
        "shows": shows.get(entry.id, ""),
        "message": message_of(page),
        "personas": personas_of(page),
        "urls": urls,
        "related": related_urls,
        "gif": f"{opts.gif_base}{entry.id}.gif" if gif.exists() else None,
        "page": f"https://github.com/{opts.repo}/blob/{opts.gif_ref}/{rel}",
    }


def build_data(root: pathlib.Path, opts: argparse.Namespace) -> dict:
    links = json.loads((HERE / "guide-links.json").read_text(encoding="utf-8"))
    layers = []
    for layer in links["layers"]:
        layers.append({
            "id": layer["id"], "title": layer["title"], "blurb": layer["blurb"],
            "links": [{
                "name": item["name"],
                "url": f"https://{item['sub']}.{opts.domain}" + item.get("path", ""),
                "auth": item["auth"],
                "login": item["login"],
                "account": item.get("account", ""),
                "secret": item.get("secret", ""),
            } for item in layer["links"]],
        })
    shows = shows_by_id(root)
    entries = catalogue.discover(root)
    groups = []
    for layer_key, gid, gtitle in GROUPS:
        demos = [build_demo(e, root, shows, links.get("demo_related", {}), opts) for e in entries if e.layer == layer_key]
        if demos:
            groups.append({"id": gid, "title": gtitle, "demos": demos})
    return {
        "domain": opts.domain,
        "repo": opts.repo,
        "ref": opts.gif_ref,
        "layers": layers,
        "personas": links["personas"],
        "passwords_note": links["passwords_note"],
        "groups": groups,
    }


def secret_findings(text: str) -> List[str]:
    found = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            found.append(match.group(0)[:40])
    return found


def produce(root: pathlib.Path, opts: argparse.Namespace) -> Dict[str, bytes]:
    """file name -> bytes of the five files, or GuideError."""
    data = build_data(root, opts)
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    leaks = secret_findings(text)
    if leaks:
        raise GuideError(f"a secret pattern is in the page data, refusing to write it: {leaks}")
    files: Dict[str, bytes] = {DATA_FILE: text.encode("utf-8")}
    for name in SITE_FILES:
        source = HERE / "guide" / name
        if not source.exists():
            raise GuideError(f"missing page source {source}")
        files[name] = source.read_bytes()
    total = sum(len(v) for v in files.values())
    if total > MAX_BYTES:
        raise GuideError(f"the page is {total} bytes, over the {MAX_BYTES} limit (a ConfigMap holds 1 MiB)")
    return files


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="guide.py", description="Write or check the demo guide files.")
    parser.add_argument("--domain", default=SOURCE_DOMAIN, help=f"apps domain of the links (default {SOURCE_DOMAIN})")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/name of the public repository")
    parser.add_argument("--gif-ref", default=DEFAULT_REF, help=f"branch or tag the GIF and page links point at (default {DEFAULT_REF})")
    parser.add_argument("--out", default=None, help=f"output directory (default {OUT_REL})")
    parser.add_argument("--root", default=None, help="repository root (default: this repository)")
    parser.add_argument("--check", action="store_true", help="exit 1 if the files on disk are not what the pages produce")
    opts = parser.parse_args(argv)
    opts.gif_base = f"https://raw.githubusercontent.com/{opts.repo}/{opts.gif_ref}/docs/assets/img/demo/"
    return opts


def main(argv: Optional[List[str]] = None) -> int:
    opts = parse_args(argv)
    root = pathlib.Path(opts.root).resolve() if opts.root else catalogue.repo_root()
    out = pathlib.Path(opts.out) if opts.out else root / OUT_REL
    try:
        files = produce(root, opts)
    except (GuideError, catalogue.ParseError) as exc:
        sys.stderr.write(f"demo guide: {exc}\n")
        return 1
    if opts.check:
        stale = [n for n, body in files.items() if not (out / n).exists() or (out / n).read_bytes() != body]
        extra = sorted(p.name for p in out.glob("*") if p.is_file() and p.name not in files) if out.exists() else []
        if stale or extra:
            sys.stderr.write(f"demo guide: {out} is out of date (stale: {', '.join(stale) or 'none'}; "
                             f"unexpected: {', '.join(extra) or 'none'}). Run: make demo guide\n")
            return 1
        sys.stdout.write(f"demo guide: {len(files)} files up to date ({sum(len(b) for b in files.values())} bytes)\n")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (out / name).write_bytes(body)
    sys.stdout.write(f"demo guide: wrote {len(files)} files to {out} ({sum(len(b) for b in files.values())} bytes)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
