"""Page sections and run results as terminal text (ADR-0616 clause 4, WP-270).

Order of what a command prints: a header, the RESULT of its Ansible file, the page section (the `### <Action>` text,
or the step's Do / Say / You should see), then where to go next. On a failure: FAILED and the page's
`If something goes wrong` rows, those citing the step's time first.
"""
from __future__ import annotations

import html
import re
import shutil
import textwrap
from typing import List, Optional

from catalogue import Page, Step, split_cells, is_separator
from runner import UnitResult

VERSION_LABEL = {"5": "5-minute", "15": "15-minute"}
MAX_WIDTH = 110


def width() -> int:
    return max(60, min(MAX_WIDTH, shutil.get_terminal_size((100, 24)).columns))


def inline(text: str) -> str:
    """Markdown inline markup to plain text: links to their text, bold and entities removed, <br> to a newline."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = text.replace("**", "")
    return html.unescape(text)


def _wrap(text: str, indent: str = "", subsequent: Optional[str] = None, w: Optional[int] = None) -> List[str]:
    w = w or width()
    out: List[str] = []
    first = True
    for part in text.split("\n"):
        filled = textwrap.wrap(part, width=w, initial_indent=indent if first else (subsequent or indent),
                               subsequent_indent=subsequent if subsequent is not None else indent,
                               break_long_words=False, break_on_hyphens=False) or [indent.rstrip()]
        out.extend(filled)
        first = False
    return out


def table_block(header: List[str], rows: List[List[str]], w: Optional[int] = None) -> List[str]:
    """A table as blocks: the first cell as an item, the other cells as `Header: value` lines under it."""
    out: List[str] = []
    for cells in rows:
        first = inline(cells[0]) if cells else ""
        out.extend(_wrap(f"- {header[0]}: {first}" if header else f"- {first}", "", "    ", w))
        for i, h in enumerate(header[1:], 1):
            value = inline(cells[i]) if i < len(cells) else ""
            if value:
                out.extend(_wrap(f"{h}: {value}", "    ", "      ", w))
    return out


def markdown(text: str, w: Optional[int] = None) -> List[str]:
    """A section body for a terminal: paragraphs and lists wrapped, tables as blocks, code kept as it is."""
    lines = (text or "").split("\n")
    out: List[str] = []
    paragraph: List[str] = []
    bullet_indent = ""

    def flush():
        nonlocal paragraph, bullet_indent
        if paragraph:
            joined = " ".join(p.strip() for p in paragraph)
            m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", paragraph[0])
            if m:
                lead = m.group(1) + ("- " if m.group(2) in "-*" else m.group(2) + " ")
                body = " ".join([m.group(3)] + [p.strip() for p in paragraph[1:]])
                out.extend(_wrap(inline(body), lead, " " * len(lead), w))
            else:
                out.extend(_wrap(inline(joined), "", "", w))
        paragraph = []

    i = 0
    in_fence = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith(("```", "~~~")):
            flush()
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            out.append("    " + line)
            i += 1
            continue
        if line.lstrip().startswith("|"):
            flush()
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(split_cells(lines[i]))
                i += 1
            header, rows = block[0], block[1:]
            if rows and is_separator(rows[0]):
                rows = rows[1:]
            out.extend(table_block(header, rows, w))
            continue
        if not line.strip():
            flush()
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue
        heading = re.match(r"^#{2,6}\s+(.*)$", line)
        if heading:
            flush()
            out.append(inline(heading.group(1)).upper())
            i += 1
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line) and paragraph:
            flush()
        if line.startswith(">"):
            line = line.lstrip("> ")
        paragraph.append(line)
        i += 1
    flush()
    while out and out[-1] == "":
        out.pop()
    return out


def result_block(result: Optional[UnitResult], error: str = "") -> List[str]:
    out = ["RESULT"]
    if result is None:
        out.append(f"  {error or 'No result.'}")
        return out
    if result.status == "nothing" and not result.commands and not result.checks:
        out.append("  Nothing to run.")
    elif result.status == "ok" and not (result.commands or result.checks or result.messages):
        out.append("  Done (its tasks are in the log).")
    for cmd in result.commands:
        rc = cmd.get("rc", 0)
        mark = "REFUSED" if cmd.get("refused") else ("ok" if rc == 0 else f"exit {rc}")
        out.append(f"  $ {cmd.get('cmd', '')}   [{mark}]")
        output = str(cmd.get("output") or "").rstrip("\n")
        for line in output.split("\n") if output else []:
            out.append(f"    {line}")
        if cmd.get("truncated"):
            out.append("    ... (first 40 lines; the full output is in the log)")
    for check in result.checks:
        mark = "PASS" if check.get("passed") in (True, "True", "true") else "FAIL"
        detail = f": {check.get('detail')}" if check.get("detail") else ""
        out.append(f"  {mark} {check.get('id', '?')}{detail}")
    for message in result.messages:
        out.extend(_wrap(str(message), "  ", "    "))
    if result.status == "skipped":
        out.append("  SKIPPED")
    if result.error:
        out.extend(_wrap(f"Error: {result.error}", "  ", "    "))
    return out


def step_header(page: Page, version: str, step: Step, total: int) -> str:
    return f"{page.id} · {VERSION_LABEL.get(version, version)} · step {step.number}/{total} · {step.time}"


def step_body(step: Step) -> List[str]:
    out: List[str] = []
    for label, value in (("Do", step.do), ("Say", step.say), ("You should see", step.see)):
        out.append(f"{label}:")
        out.extend(_wrap(inline(value) or "-", "  ", "  "))
    return out


def next_line(steps: List[Step], step: Step) -> str:
    if step.number >= len(steps):
        return "Last step done: make demo stop"
    nxt = steps[step.number]
    do = inline(nxt.do)
    do = do if len(do) <= 70 else do[:67].rstrip() + "..."
    return f"Next: {nxt.number}/{len(steps)} · {nxt.time} · {do}"


def action_section(page: Page, action: str) -> List[str]:
    text, migrated = page.lifecycle_text(action)
    if migrated:
        if text is None:
            return [f"The page has no `### {action.capitalize()}` under `## Presenter lifecycle`."]
        return [action.upper()] + markdown(text)
    out = [f"BEFORE YOU START (page not migrated yet: no `## Presenter lifecycle` section)"]
    out.extend(markdown(text) if text else ["The page has no `## Before you start` section either."])
    return out


def failure_rows(page: Page, time: str = "") -> List[str]:
    rows = page.if_wrong_rows()
    if not rows:
        return ["FAILED", "The page has no `If something goes wrong` rows."]
    if time:
        pattern = re.compile(r"(?<![\d:])" + re.escape(time) + r"(?![\d])")
        rows = [r for r in rows if any(pattern.search(v) for v in r.values())] + \
               [r for r in rows if not any(pattern.search(v) for v in r.values())]
    header = list(rows[0].keys())
    return ["FAILED", "If something goes wrong:"] + table_block(header, [[r.get(h, "") for h in header] for r in rows])
