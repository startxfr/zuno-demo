"""The demo catalogue read from its pages (ADR-0616 clauses 2 and 3, WP-270).

A demo is one page of `docs/demo/`: a scenario (`scenarios/<layer>/*.md`, plus `unifai-live-rag.md`, `blender-3d.md` and
`world-model.md`) or a workshop (`workshops/*.md`, plus `three-experiences.md` and `five-experiences.md`). Its id is the
file stem. The page is the source of truth: a step is one timed row of the `| Time | Do | Say | You should see |` table
of `## 5-minute version` or `## 15-minute version`; the 15-minute version is the 5-minute rows followed by its own.

Stdlib only, Python 3.9: the presenter's workstation runs it outside any virtualenv.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[2]

ROOT_SCENARIOS = ("unifai-live-rag", "blender-3d", "world-model")
ROOT_WORKSHOPS = ("three-experiences", "five-experiences")
VERSION_SECTIONS = {"5": "5-minute version", "15": "15-minute version"}
STEP_HEADER = ["Time", "Do", "Say", "You should see"]
FIFTEEN_LEAD = "Run the 5-minute version, then:"
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
LIFECYCLE_SECTION = "Presenter lifecycle"
LEGACY_SECTION = "Before you start"
LIFECYCLE_ACTIONS = ("status", "check", "install", "start", "stop", "uninstall")
IF_WRONG_SECTION = "If something goes wrong"

# The blocks of a version section that are not steps. Prose and lists are never steps, so their entries only document
# them and let a test notice when the page no longer has them; a table or a `###` subsection that is not listed here
# is a parse error.
EXCLUDED_BLOCKS = (
    {"page": "ai-gateway-routing", "version": "15", "kind": "subsection",
     "match": "The coding pair: C1 and C3",
     "why": "optional untimed Do | Say | You should see table, played on request"},
    {"page": "blender-3d", "version": "5", "kind": "table",
     "match": ["Order", "Prompt", "Measured", "What the audience sees"],
     "why": "the stage prompt list the Do cells refer to"},
    {"page": "quotas", "version": "15", "kind": "prose",
     "match": "**Optional replay of the 2026-11-03 proof (rehearsal only).**",
     "why": "numbered replay that changes the cluster; never a stage step"},
    {"page": "world-model", "version": "5", "kind": "prose",
     "match": "The model's context is about ten seconds",
     "why": "presenter notes around the table"},
)


class ParseError(ValueError):
    """A page does not follow the contract the engine relies on."""

    def __init__(self, path: pathlib.Path, line: int, message: str):
        super().__init__(f"{path}:{line}: {message}")
        self.path = path
        self.line = line


def repo_root() -> pathlib.Path:
    """Where the pages and the demo directories live: ZUNO_DEMO_ROOT (tests and fixtures), else the repository."""
    override = os.environ.get("ZUNO_DEMO_ROOT")
    if override:
        root = pathlib.Path(override)
        return root if root.is_absolute() else (pathlib.Path.cwd() / root).resolve()
    return pathlib.Path(os.environ.get("ZUNO_REPO_ROOT") or ENGINE_ROOT)


def github_slug(title: str, seen: Dict[str, int]) -> str:
    """The `#fragment` GitHub gives a heading; the rule of platform/docs/check_docs.py markdown_anchors."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title).replace("`", "")
    slug = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def split_cells(line: str) -> List[str]:
    """The cells of a markdown table row: split on `|` not preceded by a backslash, then unescape `\\|`."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", body)]


def is_separator(cells: List[str]) -> bool:
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", c) for c in cells)


@dataclass
class Section:
    level: int
    title: str
    slug: str
    line: int                      # 1-based line of the heading
    lines: List[str] = field(default_factory=list)   # body, up to the next heading of the same or a higher level

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip("\n")


@dataclass
class Table:
    line: int
    header: List[str]
    rows: List[Tuple[int, List[str]]]      # (1-based line, cells)


@dataclass
class Step:
    number: int          # 1-based position in its version
    time: str            # "7:30": the step id
    origin: str          # "5" or "15": the section the row is written in
    do: str
    say: str
    see: str
    line: int

    @property
    def file_name(self) -> str:
        minutes, seconds = self.time.split(":")
        return f"{int(minutes):02d}-{seconds}.yml"


@dataclass
class Page:
    id: str
    kind: str            # scenario | workshop
    layer: str
    path: pathlib.Path
    text: str
    sections: List[Section]
    steps5: List[Step] = field(default_factory=list)
    steps15_own: List[Step] = field(default_factory=list)
    excluded_seen: List[dict] = field(default_factory=list)

    def section(self, title: str, level: int = 2) -> Optional[Section]:
        for s in self.sections:
            if s.level == level and s.title == title:
                return s
        return None

    def subsections(self, parent: Section) -> List[Section]:
        """The `###` sections inside a `##` section, in page order."""
        result = []
        for s in self.sections:
            if s.level == parent.level + 1 and parent.line < s.line and self._parent_of(s) is parent:
                result.append(s)
        return result

    def _parent_of(self, sub: Section) -> Optional[Section]:
        parent = None
        for s in self.sections:
            if s.line >= sub.line:
                break
            if s.level < sub.level:
                parent = s
        return parent

    def steps(self, version: str) -> List[Step]:
        if self.kind != "scenario":
            return []
        if version == "5":
            return list(self.steps5)
        if version == "15":
            merged = list(self.steps5) + list(self.steps15_own)
            return [Step(i, s.time, s.origin, s.do, s.say, s.see, s.line) for i, s in enumerate(merged, 1)]
        raise ValueError(f"unknown version {version!r} (expected 5 or 15)")

    def lifecycle_text(self, action: str) -> Tuple[Optional[str], bool]:
        """(text, migrated): the `### <Action>` of `## Presenter lifecycle`, or the legacy `## Before you start`."""
        lifecycle = self.section(LIFECYCLE_SECTION)
        if lifecycle is not None:
            for sub in self.subsections(lifecycle):
                if sub.title.lower() == action.lower():
                    return sub.text, True
            return None, True
        legacy = self.section(LEGACY_SECTION)
        return (legacy.text if legacy is not None else None), False

    def if_wrong_rows(self) -> List[Dict[str, str]]:
        section = self.section(IF_WRONG_SECTION)
        if section is None:
            return []
        rows: List[Dict[str, str]] = []
        for table in tables_of(section.lines, section.line + 1):
            for _, cells in table.rows:
                rows.append({h: (cells[i] if i < len(cells) else "") for i, h in enumerate(table.header)})
        return rows


def parse_sections(text: str) -> List[Section]:
    """Every `##`..`######` heading outside fenced code, with its body (up to the next heading of the same or a
    higher level). `#` (the page title) is not a section."""
    lines = text.split("\n")
    headings: List[Tuple[int, int, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2)))
    seen: Dict[str, int] = {}
    sections = []
    for n, (i, level, title) in enumerate(headings):
        slug = github_slug(title, seen)
        if level == 1:
            continue
        end = len(lines)
        for j, other_level, _ in headings[n + 1:]:
            if other_level <= level:
                end = j
                break
        sections.append(Section(level, title, slug, i + 1, lines[i + 1:end]))
    return sections


def tables_of(lines: List[str], first_line: int) -> List[Table]:
    """The markdown tables of a block of lines (outside fences); first_line is the page line of lines[0]."""
    tables: List[Table] = []
    in_fence = False
    current: Optional[List[Tuple[int, str]]] = None
    for offset, line in enumerate(lines + [""]):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        is_row = not in_fence and line.lstrip().startswith("|")
        if is_row:
            current = (current or []) + [(first_line + offset, line)]
            continue
        if current:
            header = split_cells(current[0][1])
            body = current[1:]
            if body and is_separator(split_cells(body[0][1])):
                body = body[1:]
            tables.append(Table(current[0][0], header, [(n, split_cells(text)) for n, text in body]))
            current = None
    return tables


def _excluded(page_id: str, version: str, kind: str) -> List[dict]:
    return [b for b in EXCLUDED_BLOCKS if b["page"] == page_id and b["version"] == version and b["kind"] == kind]


def parse_version(page: Page, version: str) -> List[Step]:
    """The steps written in one version section, checked against the contract."""
    section = page.section(VERSION_SECTIONS[version])
    if section is None:
        raise ParseError(page.path, 1, f"no `## {VERSION_SECTIONS[version]}` section")
    body = list(section.lines)
    first = section.line + 1
    if version == "15":
        lead = next((l.strip() for l in body if l.strip()), "")
        if lead != FIFTEEN_LEAD:
            raise ParseError(page.path, section.line, f"the 15-minute version must start with {FIFTEEN_LEAD!r}")
    # Drop excluded `###` subsections; any other subsection is an error.
    kept: List[Optional[str]] = list(body)
    for sub in page.subsections(section):
        names = [b for b in _excluded(page.id, version, "subsection") if b["match"] == sub.title]
        if not names:
            raise ParseError(page.path, sub.line, f"unknown subsection {sub.title!r} in {VERSION_SECTIONS[version]!r} "
                                                  "(add it to EXCLUDED_BLOCKS if it is not a step)")
        page.excluded_seen.append(names[0])
        start = sub.line - first
        for k in range(start, start + 1 + len(sub.lines)):
            if 0 <= k < len(kept):
                kept[k] = ""
    for block in _excluded(page.id, version, "prose"):
        if any(block["match"] in (l or "") for l in kept):
            page.excluded_seen.append(block)
    step_tables = []
    for table in tables_of([l or "" for l in kept], first):
        if table.header == STEP_HEADER:
            step_tables.append(table)
            continue
        names = [b for b in _excluded(page.id, version, "table") if b["match"] == table.header]
        if not names:
            raise ParseError(page.path, table.line, f"unknown table {' | '.join(table.header)!r} in "
                                                    f"{VERSION_SECTIONS[version]!r} (add it to EXCLUDED_BLOCKS if it "
                                                    "is not a step table)")
        page.excluded_seen.append(names[0])
    if len(step_tables) != 1:
        raise ParseError(page.path, section.line, f"{VERSION_SECTIONS[version]!r} must hold exactly one "
                                                  f"`| {' | '.join(STEP_HEADER)} |` table, found {len(step_tables)}")
    steps = []
    for line_no, cells in step_tables[0].rows:
        if not cells or not TIME_RE.match(cells[0]):
            raise ParseError(page.path, line_no, f"a step row must start with a time stamp M:SS, got {cells[:1]}")
        if len(cells) != len(STEP_HEADER):
            raise ParseError(page.path, line_no, f"a step row has {len(STEP_HEADER)} cells, got {len(cells)}")
        steps.append(Step(len(steps) + 1, cells[0], version, cells[1], cells[2], cells[3], line_no))
    return steps


COMMAND_RE = re.compile(r"`((?:ONLY=\S+ )?(?:oc|make|curl|git) [^`]+)`")


def do_commands(do_cell: str) -> List[str]:
    """The backticked `oc`, `make`, `curl` and `git` commands of a Do cell, in order (ADR-0616 clause 14)."""
    return [c.strip() for c in COMMAND_RE.findall(do_cell)]


def seconds(time: str) -> int:
    minutes, secs = time.split(":")
    return int(minutes) * 60 + int(secs)


def load_page(path: pathlib.Path, kind: str, layer: str) -> Page:
    text = path.read_text(encoding="utf-8")
    page = Page(path.stem, kind, layer, path, text, parse_sections(text))
    if kind == "scenario":
        page.steps5 = parse_version(page, "5")
        page.steps15_own = parse_version(page, "15")
        times = [s.time for s in page.steps5 + page.steps15_own]
        if len(set(times)) != len(times):
            dup = sorted({t for t in times if times.count(t) > 1})
            raise ParseError(path, 1, f"step times must be unique across both versions: {', '.join(dup)}")
        for before, after in zip(page.steps5 + page.steps15_own, (page.steps5 + page.steps15_own)[1:]):
            if seconds(after.time) <= seconds(before.time):
                raise ParseError(path, after.line, f"step times must ascend: {before.time} then {after.time}")
    return page


@dataclass
class Entry:
    id: str
    kind: str
    layer: str
    path: pathlib.Path


def discover(root: Optional[pathlib.Path] = None) -> List[Entry]:
    """Every demo page of the catalogue, scenarios first, in a stable order."""
    root = root or repo_root()
    demo = root / "docs" / "demo"
    entries: List[Entry] = []
    for path in sorted(demo.glob("scenarios/*/*.md")):
        entries.append(Entry(path.stem, "scenario", path.parent.name, path))
    for stem in ROOT_SCENARIOS:
        path = demo / f"{stem}.md"
        if path.exists():
            entries.append(Entry(stem, "scenario", "experiences", path))
    for stem in ROOT_WORKSHOPS:
        path = demo / f"{stem}.md"
        if path.exists():
            entries.append(Entry(stem, "workshop", "workshop", path))
    for path in sorted(demo.glob("workshops/*.md")):
        entries.append(Entry(path.stem, "workshop", "workshop", path))
    ids = [e.id for e in entries]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"two demo pages share an id: {', '.join(duplicates)}")
    return entries


def find(demo_id: str, root: Optional[pathlib.Path] = None) -> Entry:
    for entry in discover(root):
        if entry.id == demo_id:
            return entry
    raise KeyError(demo_id)


def load(entry: Entry) -> Page:
    return load_page(entry.path, entry.kind, entry.layer)


def demo_dir(demo_id: str, root: Optional[pathlib.Path] = None) -> pathlib.Path:
    return (root or repo_root()) / "ansible" / "demos" / demo_id


def readme_probes(root: Optional[pathlib.Path] = None) -> Dict[str, str]:
    """page stem -> the "Golden-path probe" cell of docs/demo/README.md (`blender`, `none (rehearse first)`...)."""
    readme = (root or repo_root()) / "docs" / "demo" / "README.md"
    if not readme.exists():
        return {}
    result: Dict[str, str] = {}
    for table in tables_of(readme.read_text(encoding="utf-8").split("\n"), 1):
        if "Golden-path probe" not in table.header:
            continue
        col = table.header.index("Golden-path probe")
        for _, cells in table.rows:
            link = re.search(r"\]\(([^)#]+\.md)", cells[0])
            if link and col < len(cells):
                result[pathlib.PurePosixPath(link.group(1)).stem] = cells[col]
    return result


def show_ready(probe_cell: str) -> str:
    cell = probe_cell.lower()
    if not cell:
        return "-"
    if "not show-ready" in cell:
        return "no"
    if cell.startswith("none"):
        return "rehearse first"
    names = re.findall(r"`([^`]+)`", probe_cell)
    return f"probe {','.join(names)}" if names else probe_cell
