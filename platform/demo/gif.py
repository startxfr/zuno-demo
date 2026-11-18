"""Cut a demo recording into its GIF (ADR-0617, WP-284).

    python3 platform/demo/gif.py <id> [<recording dir>] [--dry-run]

A recording is a directory `~/.cache/zuno/demo/recordings/<id>-<YYYYmmdd-HHMMSS>/` written by
`evaluations/browser/record.sh <id> <dir>`: `recording.webm`, `markers.json` and one `<marker>.png` per marker. The cut
list `ansible/demos/<id>/gif.yml` names the moments to keep:

    target_seconds: [40, 60]      # the GIF's total length, inclusive
    width: 960                    # pixels; the picture keeps the viewport ratio, a 56 px caption band goes under it
    fps: 10
    moments:
      - {still: login, hold: 2.5, caption: "Sign in with the company account"}
      - {from: q1-sent, to: q1-done, fit: 5, hold: 2.5, step: "0:45", caption: "0:45 An answer"}

A `still` moment shows the marker's PNG for `hold` seconds. A motion moment plays the recording from one marker to
the next: `fit: <seconds>` sets its playing time whatever the real span (speed = span / fit, kept within 0.5-16, so a
fast answer is slowed down at most to half speed and the moment is then simply shorter; `fit` never freezes a frame),
or a fixed `speed:`; `hold` freezes the last frame. Every moment lasts at least 2 s. `step` must be a time of the
page's 5-minute table. Each moment's caption is written in a black band under the picture, so it hides nothing.
A recording of several takes (one persona each, `takes.json` beside one sub-directory per take): every moment names
its take, `take: <name>`, and is cut from that take's video and PNGs; the takes share one viewport.

When markers.json names `motion_from`, no motion moment may start before that marker: the take holds the sign-in
before it, which a public GIF never shows in motion.

An assembled take (markers.json `kind: assembled`) is made by hand from media that already exist, such as a recorded
fallback or screenshots, with no recorder run: it creates nothing (`created` [], `cleaned` null) and has no persona
(no `owned`). Its `source` lists the originals, [{path, sha256, file, altered}]: `file` is the copy's name in the
take's directory (the original's file name when absent); `altered: {sha256, how}` marks a file made from its
original (a frame taken out of a video, a crop), whose own SHA-256 is then the one checked. Every file a moment reads
must be one of the sources, and every source's SHA-256 is checked before anything is cut. `video` names the file
motion moments play (a plain name; `recording.webm` when absent). A caption fits the GIF's width: 60 characters at
960 px and wider, fewer on a narrower GIF.

ffmpeg runs in the Playwright image by podman (the workstation has no ffmpeg). The GIF is written next to the
recording, `<id>.gif`, never in the repository: it is published only after the owner's "go <id>" (ADR-0617).
Exit codes: 0 built, 1 the cut list, the recording or the result is wrong, 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import catalogue  # noqa: E402
import session  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with Ansible
    yaml = None

IMAGE = "mcr.microsoft.com/playwright:v1.48.0-jammy"
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
MOUNT = "/rec"
CAPTIONS = ".gif-captions"
MIN_MOMENT = 2.0
MAX_BYTES = 8 * 1024 * 1024
AIM_BYTES = 5 * 1024 * 1024
SPEED_RANGE = (0.5, 16.0)
BAND = 56                   # pixels of the caption band under the picture
FPS_RANGE = (5, 15)
WIDTH_RANGE = (480, 1280)
STAMP = re.compile(r"^\d{8}-\d{6}$")   # <YYYYmmdd-HHMMSS>, the suffix of a recording directory
TAKE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CAPTION_MAX = 60           # about 780 px at 26 px Liberation Sans: inside 960 with a margin
CAPTION_PX = 13            # pixels per character of a caption at 26 px Liberation Sans, a wide average
CAPTION_MARGIN = 40        # pixels kept free across the band
FFMPEG_TIMEOUT = 900
TAKE_KINDS = ("browser", "terminal", "assembled")
VIDEO = "recording.webm"   # the file motion moments play, unless markers.json names another (`video`)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CutError(ValueError):
    """The cut list, the recording or the result is wrong; every reason is listed."""

    def __init__(self, reasons: Sequence[str]):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


@dataclass
class Moment:
    index: int
    kind: str              # still | motion
    caption: str
    hold: float
    marker: str = ""       # still: its PNG
    start: float = 0.0     # motion: recording time of `from`
    end: float = 0.0       # motion: recording time of `to`
    speed: float = 1.0
    step: str = ""
    take: str = ""         # the take it is cut from, when the recording holds several (takes.json); "" otherwise

    @property
    def span(self) -> float:
        return self.end - self.start

    @property
    def seconds(self) -> float:
        """Length in the GIF: a still's hold, or a motion's span at its speed plus its hold (never padded by `fit`)."""
        return self.hold if self.kind == "still" else self.span / self.speed + self.hold

    def label(self) -> str:
        where = f"{self.take}: " if self.take else ""
        if self.kind == "still":
            return f"{where}still {self.marker}"
        return f"{where}{self.start:.1f}-{self.end:.1f} s x{self.speed:.1f}"

    @property
    def prefix(self) -> str:
        """The take's sub-directory in the recording, with its slash; "" for a single take."""
        return f"{self.take}/" if self.take else ""


@dataclass
class Plan:
    demo: str
    moments: List[Moment]
    width: int
    height: int
    fps: int
    target: Sequence[float]
    viewport: Dict[str, int]

    @property
    def seconds(self) -> float:
        return sum(m.seconds for m in self.moments)

    @property
    def out_height(self) -> int:
        """The GIF's height: the picture plus the caption band under it."""
        return self.height + BAND


# --- inputs ------------------------------------------------------------------------------------------------------

def recordings_dir() -> pathlib.Path:
    return session.recordings_dir()


def cut_list_path(demo_id: str, root: Optional[pathlib.Path] = None) -> pathlib.Path:
    return catalogue.demo_dir(demo_id, root) / "gif.yml"


def load_cut_list(path: pathlib.Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is missing: install Ansible (it ships PyYAML) or `pip install pyyaml`")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CutError([f"{path}: not a mapping"])
    return data


def load_markers(directory: pathlib.Path) -> dict:
    path = directory / "markers.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CutError([f"{path} is missing: not a recording directory"])
    except ValueError as exc:
        raise CutError([f"{path} is not JSON: {exc}"])
    if not isinstance(data, dict):
        raise CutError([f"{path}: not an object"])
    return data


def load_takes(directory: pathlib.Path) -> Optional[Dict[str, dict]]:
    """take name -> its markers.json, in the order of `takes.json`, for a recording of several takes (one recorder
    run per persona, ADR-0618: each take in its own sub-directory, with the single-take files). None for a
    single take, whose markers.json is at the top of the directory."""
    path = directory / "takes.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CutError([f"{path} is not JSON: {exc}"])
    listed = data.get("takes") if isinstance(data, dict) else None
    if not isinstance(listed, list) or not listed:
        raise CutError([f"{path}: `takes` must be a non-empty list"])
    takes: Dict[str, dict] = {}
    for item in listed:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not TAKE_NAME.match(name) or name in takes:
            raise CutError([f"{path}: take {item!r} needs a name of its own (a-z, 0-9, -)"])
        takes[name] = load_markers(directory / name)
    return takes


def latest_recording(demo_id: str, base: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """The newest `<id>-<stamp>/` holding a markers.json (or a takes.json: several takes), or None."""
    base = base or recordings_dir()
    if not base.is_dir():
        return None
    # The whole suffix is the stamp: a scout's `<id>-<stamp>-scout/` is not a recording (a scout of several takes
    # holds a takes.json too).
    found = [p for p in base.glob(f"{demo_id}-*") if p.is_dir()
             and ((p / "markers.json").is_file() or (p / "takes.json").is_file())
             and STAMP.match(p.name[len(demo_id) + 1:])]
    return sorted(found)[-1] if found else None


def page_times(demo_id: str, root: Optional[pathlib.Path] = None) -> List[str]:
    """The times of the page's 5-minute table."""
    entry = catalogue.find(demo_id, root)
    return [s.time for s in catalogue.load(entry).steps("5")]


# --- the plan ----------------------------------------------------------------------------------------------------

def _number(value, name: str, reasons: List[str], where: str) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        reasons.append(f"{where}: `{name}` must be a number")
        return None
    return float(value)


def _take_facts(demo_id: str, markers: dict, reasons: List[str]) -> dict:
    """What one markers.json says: its checks (appended to `reasons`), its marker times, its PNGs, the time no motion
    may start before, and its viewport."""
    if markers.get("status") != "pass":
        reasons.append(f"the recording did not pass (status {markers.get('status')!r}: "
                       f"{markers.get('detail') or 'no detail'}): record it again")
    # ADR-0618 clause 9: a browser take says what it created and whether it cleaned it, and what the persona owns
    # before and after (cleaned null: nothing was created). A terminal take replays a captured session: it creates
    # nothing and reads no persona's list (owned null). `kind` absent: a browser take of the first chain.
    # An assembled take is made by hand from media that already exist: like a terminal take it creates nothing and
    # reads no persona's list; its `source` says where every file came from.
    kind = markers.get("kind", "browser")
    sources: Dict[str, dict] = {}
    if kind not in TAKE_KINDS:
        reasons.append(f"markers.json: unknown take kind {kind!r}")
    elif kind in ("terminal", "assembled"):
        if markers.get("created") or markers.get("cleaned") is not None:
            reasons.append(f"{'an' if kind == 'assembled' else 'a'} {kind} take creates nothing: its `created` must "
                           "be [] and its `cleaned` null")
        if kind == "assembled":
            sources = _sources(markers, reasons)
    else:
        if markers.get("cleaned") is False:
            created = ", ".join(f"{c.get('kind')} {c.get('id')}" for c in markers.get("created") or []
                                if isinstance(c, dict))
            reasons.append(f"the take did not clean what it created ({created or 'see markers.json'}): delete it by "
                           "hand, then record again")
        owned = markers.get("owned")
        if not isinstance(owned, dict):
            reasons.append("markers.json does not say what the persona owns before and after the take (`owned`)")
        elif owned.get("same") is not True:
            reasons.append(f"what the persona owns changed during the take ({owned.get('before')} before, "
                           f"{owned.get('after')} after): read the take's log, then record again")
    # A take whose page showed a node name or a private address is never cut, whatever its status says (record.mjs
    # counts them at each marker; the repository is public). No cut list can excuse it: record again.
    shown = markers.get("private_addresses")
    if isinstance(shown, dict) and shown.get("flagged"):
        reasons.append(f"the take showed node names or private IP addresses (at {', '.join(map(str, shown.get('at') or [])) or 'see markers.json'}): "
                       "it must not be published, record it again")
    if markers.get("demo") not in (None, demo_id):
        reasons.append(f"the recording is of {markers.get('demo')!r}, not {demo_id!r}")
    at: Dict[str, float] = {}
    png: Dict[str, str] = {}
    previous = None
    for item in markers.get("markers") or []:
        name = item.get("name") if isinstance(item, dict) else None
        t = item.get("t") if isinstance(item, dict) else None
        if not isinstance(name, str) or isinstance(t, bool) or not isinstance(t, (int, float)):
            reasons.append(f"markers.json: malformed marker {item!r}")
            continue
        if name in at:
            reasons.append(f"markers.json: marker {name!r} appears twice")
        if previous is not None and t < previous:
            reasons.append(f"markers.json: marker {name!r} goes back in time")
        at[name] = float(t)
        png[name] = str(item.get("png") or f"{name}.png")
        previous = t
    # The walkthrough names the first marker a motion segment may start at: before it, the video holds the sign-in
    # (the owner's rule: a public GIF never shows it in motion). Stills are allowed anywhere. Absent: no limit.
    motion_from = markers.get("motion_from")
    floor = None
    if motion_from is not None:
        if motion_from not in at:
            reasons.append(f"markers.json: `motion_from` {motion_from!r} is not a marker")
        else:
            floor = at[motion_from]
    viewport = markers.get("viewport") or {}
    vw, vh = viewport.get("width"), viewport.get("height")
    if not (isinstance(vw, int) and isinstance(vh, int) and vw > 0 and vh > 0):
        reasons.append("markers.json: `viewport` needs integer width and height")
        vw, vh = 16, 10
    video = markers.get("video", VIDEO)
    if not plain_name(video):
        reasons.append(f"markers.json: `video` {video!r} must be a plain file name in the take's directory, no path")
        video = VIDEO
    return {"at": at, "png": png, "floor": floor, "motion_from": motion_from, "vw": vw, "vh": vh, "kind": kind,
            "sources": sources, "video": video}


def plain_name(name) -> bool:
    """A file name in the take's directory: no path separator, not `.` or `..`."""
    return isinstance(name, str) and bool(name) and "/" not in name and "\\" not in name and name not in (".", "..")


def _sources(markers: dict, reasons: List[str]) -> Dict[str, dict]:
    """An assembled take's `source`: file name in the take's directory -> its entry {path, sha256, file, altered}.
    Malformed entries are reasons (appended) and left out."""
    listed = markers.get("source")
    if not isinstance(listed, list) or not listed:
        reasons.append("an assembled take needs `source`: the originals it was made from, [{path, sha256}]")
        return {}
    files: Dict[str, dict] = {}
    for item in listed:
        if not isinstance(item, dict) or set(item) - {"path", "sha256", "file", "altered"}:
            reasons.append(f"markers.json: source {item!r} takes only path, sha256, file and altered")
            continue
        path, digest, altered = item.get("path"), item.get("sha256"), item.get("altered")
        name = item.get("file", pathlib.PurePosixPath(path).name if isinstance(path, str) else None)
        problems = []
        if not isinstance(path, str) or not path.strip():
            problems.append("`path` names the original")
        if not isinstance(digest, str) or not SHA256.match(digest):
            problems.append("`sha256` is the original's, 64 lower-case hex digits")
        if not plain_name(name):
            problems.append("`file` is a plain file name in the take's directory")
        if altered is not None and not (isinstance(altered, dict) and set(altered) == {"sha256", "how"}
                                         and isinstance(altered["sha256"], str) and SHA256.match(altered["sha256"])
                                         and isinstance(altered["how"], str) and altered["how"].strip()
                                         and "\n" not in altered["how"]):
            problems.append("`altered` is {sha256, how}: the file's own SHA-256 and one line on how it was made")
        if not problems and name in files:
            problems.append(f"{name} is listed twice")
        if problems:
            reasons.append(f"markers.json: source {path!r}: " + "; ".join(problems))
            continue
        files[name] = item
    return files


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sources(directory: pathlib.Path, markers: dict, takes: Optional[Dict[str, dict]] = None) -> None:
    """Every source of an assembled take is in the take's directory with the SHA-256 recorded for it (`altered.sha256`
    for a file made from its original, else the original's): otherwise the take does not hold what it says it was
    made from, and nothing is cut. Takes of other kinds have no sources."""
    reasons: List[str] = []
    for prefix, m in ([(f"{name}/", m) for name, m in takes.items()] if takes else [("", markers)]):
        if m.get("kind") != "assembled":
            continue
        for name, item in _sources(m, []).items():
            want = (item.get("altered") or {}).get("sha256") or item["sha256"]
            try:
                got = _sha256(directory / f"{prefix}{name}")
            except OSError:
                reasons.append(f"{directory}: missing {prefix}{name}, a source of the take")
                continue
            if got != want:
                reasons.append(f"{prefix}{name}: its SHA-256 {got[:16]}... is not the recorded {want[:16]}...: the "
                               "take does not hold the file its `source` names")
    if reasons:
        raise CutError(reasons)


def caption_max(width: int) -> int:
    """The longest caption a GIF of this width shows whole: 60 characters at 960 px and wider, fewer below."""
    return min(CAPTION_MAX, (width - CAPTION_MARGIN) // CAPTION_PX)


def plan(demo_id: str, cut: dict, markers: dict, times: Optional[Sequence[str]] = None,
         takes: Optional[Dict[str, dict]] = None) -> Plan:
    """Check the cut list against the recording and the page; return what to cut, or raise CutError. `takes` (name ->
    markers.json) is given for a recording of several takes: every moment then names its `take`, and each take is
    checked on its own, its reasons prefixed with its name."""
    reasons: List[str] = []
    facts: Dict[str, dict] = {}
    if takes:
        for name, own_markers in takes.items():
            own: List[str] = []
            facts[name] = _take_facts(demo_id, own_markers, own)
            reasons += [f"take {name}: {reason}" for reason in own]
        # One picture size for the whole GIF. Two viewports (a terminal take beside a browser take) would need a
        # scale and a pad per moment: not done, refused.
        if len({(f["vw"], f["vh"]) for f in facts.values()}) > 1:
            reasons.append("the takes do not share one viewport ("
                           + ", ".join(f"{name} {f['vw']}x{f['vh']}" for name, f in facts.items())
                           + "): one GIF has one picture size")
    else:
        facts[""] = _take_facts(demo_id, markers, reasons)
    first = next(iter(facts.values()))
    vw, vh = first["vw"], first["vh"]

    unknown = sorted(set(cut) - {"target_seconds", "width", "fps", "moments", "record_notice"})
    if unknown:
        reasons.append(f"the cut list has unknown key(s) {', '.join(unknown)}")
    width = cut.get("width", 960)
    fps = cut.get("fps", 10)
    target = cut.get("target_seconds", [40, 60])
    if not isinstance(width, int) or not WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]:
        reasons.append(f"`width` must be an integer from {WIDTH_RANGE[0]} to {WIDTH_RANGE[1]}")
        width = 960
    if not isinstance(fps, int) or not FPS_RANGE[0] <= fps <= FPS_RANGE[1]:
        reasons.append(f"`fps` must be an integer from {FPS_RANGE[0]} to {FPS_RANGE[1]}")
        fps = 10
    if (not isinstance(target, list) or len(target) != 2
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in target)
            or not 0 < target[0] <= target[1]):
        reasons.append("`target_seconds` must be [min, max] in seconds")
        target = [40, 60]
    height = int(round(width * vh / vw / 2.0)) * 2
    if vh > vw:
        reasons.append(f"the take's viewport is {vw}x{vh}, taller than wide: a GIF frame stays landscape (for a "
                       "terminal take, fewer `record.rows` or more `record.cols`)")

    raw = cut.get("moments")
    if not isinstance(raw, list) or not raw:
        reasons.append("`moments` must be a non-empty list")
        raw = []
    moments: List[Moment] = []
    for index, item in enumerate(raw, 1):
        where = f"moment {index}"
        if not isinstance(item, dict):
            reasons.append(f"{where}: not a mapping")
            continue
        unknown = sorted(set(item) - {"still", "from", "to", "fit", "speed", "hold", "step", "caption", "take"})
        if unknown:
            reasons.append(f"{where}: unknown key(s) {', '.join(unknown)}")
        take = item.get("take", "")
        if takes and take not in facts:
            reasons.append(f"{where}: `take` must name one of the recording's takes ({', '.join(facts)})")
            take = next(iter(facts))
        elif not takes and "take" in item:
            reasons.append(f"{where}: `take` is for a recording of several takes; this one has a single take")
            take = ""
        at, floor, motion_from = facts[take]["at"], facts[take]["floor"], facts[take]["motion_from"]
        caption = item.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            reasons.append(f"{where}: `caption` is required")
            caption = ""
        elif len(caption) > caption_max(width) or "\n" in caption:
            narrow = f" on a {width} px GIF" if caption_max(width) < CAPTION_MAX else ""
            reasons.append(f"{where}: the caption must be one line of at most {caption_max(width)} characters{narrow}")
        step = item.get("step")
        if step is not None:
            step = guard_time(step)
            if times is not None and step not in times:
                reasons.append(f"{where}: step {step} is not a time of the page's 5-minute table "
                               f"({', '.join(times)})")
        hold = item.get("hold", 0)
        hold = _number(hold, "hold", reasons, where)
        if hold is not None and hold < 0:
            reasons.append(f"{where}: `hold` cannot be negative")
        hold = hold if hold is not None and hold >= 0 else 0.0
        if "still" in item:
            if any(k in item for k in ("from", "to", "fit", "speed")):
                reasons.append(f"{where}: a `still` takes only `hold`, `step` and `caption`")
            name = item["still"]
            if name not in at:
                reasons.append(f"{where}: marker {name!r} is not in markers.json")
            moment = Moment(index, "still", caption.strip(), hold, marker=str(name), step=step or "")
        elif "from" in item and "to" in item:
            start, end = at.get(item["from"]), at.get(item["to"])
            for key in ("from", "to"):
                if item[key] not in at:
                    reasons.append(f"{where}: marker {item[key]!r} is not in markers.json")
            if start is not None and end is not None and end <= start:
                reasons.append(f"{where}: `to` ({item['to']}) is not after `from` ({item['from']})")
            if start is not None and floor is not None and start < floor:
                reasons.append(f"{where}: a motion segment cannot start before `{motion_from}` (the recording shows "
                               f"the sign-in before it); use a still")
            moment = Moment(index, "motion", caption.strip(), hold, start=start or 0.0, end=end or 0.0,
                            step=step or "")
            if ("fit" in item) == ("speed" in item):
                reasons.append(f"{where}: a motion moment takes `fit` or `speed`, one of them")
            elif "fit" in item:
                fit = _number(item["fit"], "fit", reasons, where)
                if fit is not None and fit <= 0:
                    reasons.append(f"{where}: `fit` must be positive")
                elif fit is not None and moment.span > 0:
                    moment.speed = min(max(moment.span / fit, SPEED_RANGE[0]), SPEED_RANGE[1])
            else:
                speed = _number(item["speed"], "speed", reasons, where)
                if speed is not None and not SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]:
                    reasons.append(f"{where}: `speed` must be from {SPEED_RANGE[0]:g} to {SPEED_RANGE[1]:g}")
                elif speed is not None:
                    moment.speed = speed
        else:
            reasons.append(f"{where}: needs `still: <marker>` or `from:` and `to:` markers")
            continue
        if moment.seconds < MIN_MOMENT - 1e-9:
            reasons.append(f"{where}: lasts {moment.seconds:.1f} s in the GIF; every moment needs at least "
                           f"{MIN_MOMENT:g} s (raise `hold` or `fit`)")
        # An assembled take is cut only from files its `source` names (verify_sources checks their SHA-256).
        own = facts[take]
        if own["kind"] == "assembled" and own["sources"]:
            reads = own["png"].get(moment.marker, "") if moment.kind == "still" else own["video"]
            if reads and reads not in own["sources"]:
                reasons.append(f"{where}: {reads} is not a source of the assembled take: list it in `source`")
        moment.take = take
        moments.append(moment)
    result = Plan(demo_id, moments, width, height, fps, target, {"width": vw, "height": vh})
    if moments and not reasons and not target[0] <= result.seconds <= target[1]:
        reasons.append(f"the GIF would last {result.seconds:.1f} s, outside {target[0]:g}-{target[1]:g} s: "
                       f"change `hold` or `fit`")
    if reasons:
        raise CutError(reasons)
    return result


def guard_time(value) -> str:
    """A step time as M:SS. YAML 1.1 reads an unquoted 0:45 as the base-60 integer 45; quote it."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value // 60}:{value % 60:02d}"
    return str(value)


# --- ffmpeg ------------------------------------------------------------------------------------------------------

def caption_files(p: Plan) -> Dict[int, str]:
    """moment index -> caption file name under CAPTIONS (drawtext reads a file: no escaping of the text)."""
    return {m.index: f"{CAPTIONS}/{m.index:02d}.txt" for m in p.moments}


def _drawtext(path: str) -> str:
    """The caption, centred in the band under the picture (never over it: the band is added by `pad`)."""
    return (f"drawtext=fontfile={FONT}:textfile={MOUNT}/{path}:fontsize=26:fontcolor=white:"
            f"x=(w-text_w)/2:y=h-{BAND}+({BAND}-text_h)/2")


def _png_names(markers: dict) -> Dict[str, str]:
    return {m.get("name"): m.get("png") or f"{m.get('name')}.png" for m in markers.get("markers") or []
            if isinstance(m, dict)}


def _video(markers: dict) -> str:
    """The file a take's motion moments play (plan() has refused anything but a plain name)."""
    video = markers.get("video", VIDEO)
    return video if plain_name(video) else VIDEO


def ffmpeg_argv(p: Plan, markers: dict, output: str, takes: Optional[Dict[str, dict]] = None) -> List[str]:
    """One ffmpeg command for the whole GIF, paths as seen inside the container (the recording at /rec; a take of
    several is at /rec/<take>/)."""
    files = caption_files(p)
    names = {name: _png_names(m) for name, m in (takes or {"": markers}).items()}
    videos = {name: _video(m) for name, m in (takes or {"": markers}).items()}
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    graph: List[str] = []
    size = f"scale={p.width}:{p.height}:flags=lanczos,setsar=1,pad={p.width}:{p.out_height}:0:0:color=black"
    # One input per moment, in order: a motion moment seeks into the recording (-ss/-t before -i), so no frame of
    # the whole take is ever buffered; a still loops its PNG for the hold.
    for number, m in enumerate(p.moments):
        text = _drawtext(files[m.index])
        if m.kind == "still":
            argv += ["-loop", "1", "-framerate", str(p.fps), "-t", f"{m.hold:.3f}",
                     "-i", f"{MOUNT}/{m.prefix}{names[m.take].get(m.marker, m.marker + '.png')}"]
            graph.append(f"[{number}:v]fps={p.fps},{size},{text},format=rgb24[v{m.index}]")
        else:
            argv += ["-ss", f"{m.start:.3f}", "-t", f"{m.span:.3f}", "-i", f"{MOUNT}/{m.prefix}{videos[m.take]}"]
            chain = f"[{number}:v]setpts=(PTS-STARTPTS)/{m.speed:.4f},fps={p.fps},{size}"
            if m.hold > 0:
                chain += f",tpad=stop_mode=clone:stop_duration={m.hold:.3f}"
            graph.append(f"{chain},{text},format=rgb24[v{m.index}]")
    graph.append("".join(f"[v{m.index}]" for m in p.moments) + f"concat=n={len(p.moments)}:v=1:a=0,split[g1][g2]")
    graph.append("[g1]palettegen=stats_mode=diff[pal]")
    graph.append("[g2][pal]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
    argv += ["-filter_complex", ";".join(graph), "-loop", "0", f"{MOUNT}/{output}"]
    return argv


def podman(directory: pathlib.Path, argv: List[str]) -> List[str]:
    return ["podman", "run", "--rm", "--network", "none", "-v", f"{directory}:{MOUNT}:Z", IMAGE] + argv


def _duration(directory: pathlib.Path, name: str) -> Optional[float]:
    probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"{MOUNT}/{name}"]
    done = subprocess.run(podman(directory, probe), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=120)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return None


def size_problem(path: pathlib.Path) -> Optional[str]:
    size = path.stat().st_size
    if size > MAX_BYTES:
        return (f"{path.name} is {size / 1048576:.1f} MB, over the {MAX_BYTES // 1048576} MB limit: lower `fps` or "
                "`width`, or shorten the holds")
    return None


@dataclass
class Built:
    path: pathlib.Path
    seconds: Optional[float]
    size: int
    plan: Plan

    def summary(self) -> List[str]:
        lines = [f"GIF: {self.path}",
                 f"  {self.size / 1048576:.1f} MB (limit {MAX_BYTES // 1048576} MB, aim {AIM_BYTES // 1048576} MB), "
                 f"{self.seconds if self.seconds is None else round(self.seconds, 1)} s by ffprobe "
                 f"({self.plan.seconds:.1f} s planned), {self.plan.width}x{self.plan.out_height} "
                 f"(picture {self.plan.width}x{self.plan.height} + caption band {BAND}), {self.plan.fps} fps"]
        for m in self.plan.moments:
            step = f" [{m.step}]" if m.step else ""
            lines.append(f"  {m.index}. {m.seconds:4.1f} s  {m.label()}{step}  \"{m.caption}\"")
        if self.size > AIM_BYTES:
            lines.append(f"  Over the {AIM_BYTES // 1048576} MB aim: consider fewer fps or shorter holds.")
        return lines


def git_blob(path: pathlib.Path) -> Optional[str]:
    """The git blob id of a file (`git hash-object`), computed here: the cut list a GIF was cut with."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def build(demo_id: str, directory: pathlib.Path, cut: dict, *, times: Optional[Sequence[str]] = None,
          runner=subprocess.run, cut_path: Optional[pathlib.Path] = None) -> Built:
    """Cut `directory`'s recording into `<id>.gif` in the same directory, or raise CutError. `<id>.gif.json` records
    the provenance: the take, its start, and the git blob of the cut list (`cut_path`), for the publication record."""
    takes = load_takes(directory)
    markers = next(iter(takes.values())) if takes else load_markers(directory)
    p = plan(demo_id, cut, markers, times, takes=takes)
    missing = []
    names = {name: _png_names(m) for name, m in (takes or {"": markers}).items()}
    videos = {name: _video(m) for name, m in (takes or {"": markers}).items()}
    for m in p.moments:
        needed = f"{m.prefix}{videos[m.take]}" if m.kind == "motion" else f"{m.prefix}{names[m.take][m.marker]}"
        if needed not in missing and not (directory / needed).is_file():
            missing.append(needed)
    if missing:
        raise CutError([f"{directory}: missing {', '.join(missing)}"])
    verify_sources(directory, markers, takes)
    if shutil.which("podman") is None:
        raise CutError(["podman is not on PATH: ffmpeg runs in the Playwright image (see evaluations/browser/)"])
    captions = directory / CAPTIONS
    captions.mkdir(exist_ok=True)
    for m in p.moments:
        (directory / caption_files(p)[m.index]).write_text(m.caption, encoding="utf-8")
    output = f"{demo_id}.gif"
    done = runner(podman(directory, ffmpeg_argv(p, markers, output, takes)), stdout=subprocess.PIPE,
                  stderr=subprocess.STDOUT, universal_newlines=True, timeout=FFMPEG_TIMEOUT)
    path = directory / output
    if done.returncode != 0 or not path.is_file():
        tail = "\n".join((done.stdout or "").strip().split("\n")[-15:])
        raise CutError([f"ffmpeg failed (exit {done.returncode}): {tail}"])
    built = Built(path, _duration(directory, output), path.stat().st_size, p)
    created, cleaned = markers.get("created"), markers.get("cleaned")
    if takes:
        created = [c for m in takes.values() for c in m.get("created") or []]
        states = [m.get("cleaned") for m in takes.values() if m.get("cleaned") is not None]
        cleaned = (all(state is True for state in states) if states else None)
    (directory / f"{demo_id}.gif.json").write_text(json.dumps({
        "demo": demo_id, "gif": output, "bytes": built.size, "seconds": built.seconds, "planned": p.seconds,
        "take": directory.name, "started": markers.get("started"), "created": created, "cleaned": cleaned,
        # An assembled take: what it was made from (the originals' paths and SHA-256, as markers.json lists them).
        "kind": markers.get("kind", "browser"),
        "source": [s for m in (takes or {"": markers}).values() for s in m.get("source") or []] or None,
        # A recording of several takes: each with its persona, its start and what it created. `created` and
        # `cleaned` above are then the whole recording's (everything the takes created; cleaned only if every take
        # that created something cleaned it), and `started` is the first take's.
        "takes": [{"name": name, "persona": m.get("persona"), "started": m.get("started"), "created": m.get("created"),
                   "cleaned": m.get("cleaned")} for name, m in (takes or {}).items()],
        "cut_list": f"ansible/demos/{demo_id}/gif.yml", "cut_list_blob": git_blob(cut_path) if cut_path else None,
        "width": p.width, "height": p.out_height, "picture_height": p.height, "fps": p.fps,
        "moments": [{"caption": m.caption, "seconds": round(m.seconds, 2), "cut": m.label(), "step": m.step,
                     **({"take": m.take} if m.take else {})}
                    for m in p.moments]}, indent=2) + "\n", encoding="utf-8")
    problems = [x for x in (size_problem(path),) if x]
    if built.seconds is not None and not p.target[0] - 0.5 <= built.seconds <= p.target[1] + 0.5:
        problems.append(f"ffprobe says {built.seconds:.1f} s, outside {p.target[0]:g}-{p.target[1]:g} s")
    if problems:
        raise CutError(problems + [f"(the GIF is left in {directory} for a look)"])
    return built


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cut a demo recording into its GIF (ADR-0617). Offline.")
    parser.add_argument("demo")
    parser.add_argument("directory", nargs="?", help="a recording directory (default: the newest for the demo)")
    parser.add_argument("--dry-run", action="store_true", help="check the cut list and print the ffmpeg command")
    args = parser.parse_args(argv)
    path = cut_list_path(args.demo)
    if not path.is_file():
        sys.stderr.write(f"{path} is missing: this demo has no cut list (ADR-0617)\n")
        return 2
    directory = pathlib.Path(args.directory) if args.directory else latest_recording(args.demo)
    if directory is None:
        sys.stderr.write(f"No recording of {args.demo} under {recordings_dir()}: run `make demo record {args.demo}`\n")
        return 1
    try:
        cut = load_cut_list(path)
        times = page_times(args.demo)
        if args.dry_run:
            takes = load_takes(directory)
            markers = next(iter(takes.values())) if takes else load_markers(directory)
            p = plan(args.demo, cut, markers, times, takes=takes)
            verify_sources(directory, markers, takes)
            print(" ".join(podman(directory, ffmpeg_argv(p, markers, f"{args.demo}.gif", takes))))
            print(f"{len(p.moments)} moments, {p.seconds:.1f} s planned")
            return 0
        built = build(args.demo, directory, cut, times=times, cut_path=path)
    except CutError as exc:
        for reason in exc.reasons:
            sys.stderr.write(f"REFUSED: {reason}\n")
        return 1
    print("\n".join(built.summary()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
