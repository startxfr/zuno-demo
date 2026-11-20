"""Run a demo's action and step files through the one runner playbook, locally (ADR-0616 clauses 3 and 12, WP-270).

    ansible-playbook -i ansible/inventories/demo333/hosts.yml ansible/playbooks/demo_run.yml -e @<vars file>

Never through AAP: a checkout without ansible/confidential.yml would route `make dN` there, and AAP runs `devel` from
git, not this tree. The vars file (mode 0600, under $XDG_RUNTIME_DIR) names the units to run; the playbook writes one
result per unit to a JSON file this module reads back.

Tests and CI smoke runs set HOME to a temporary directory. When Ansible is installed in the user site (`pip install
--user`, ~/.local), that HOME hides it from ansible-playbook ("No module named 'ansible'"): such a run also sets
PYTHONUSERBASE to the real ~/.local. A presenter never runs with a temporary HOME, so nothing here works around it.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

import session

ENGINE_ROOT = pathlib.Path(os.environ.get("ZUNO_REPO_ROOT") or pathlib.Path(__file__).resolve().parents[2])
INVENTORY = "ansible/inventories/demo333/hosts.yml"
PLAYBOOK = "ansible/playbooks/demo_run.yml"


@dataclass
class Unit:
    name: str          # an action ("status") or a step time ("7:30")
    file: str          # relative to the demo directory: "status.yml", "steps/07-30.yml"
    kind: str = "action"
    # A workshop plays other demos' files (ADR-0616 clause 10): the directory and id of the demo that owns the file,
    # the action or step time the owner's manifest knows it by, and whether its probes wait for one merged run.
    dir: str = ""
    demo: str = ""
    action: str = ""
    time: str = ""
    defer_flush: bool = False


@dataclass
class UnitResult:
    name: str
    status: str                     # ok | failed | nothing | skipped | missing
    commands: List[dict] = field(default_factory=list)
    checks: List[dict] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return self.status in ("failed", "missing")


@dataclass
class RunResult:
    rc: int
    units: List[UnitResult]
    log_path: Optional[pathlib.Path]
    error: str = ""

    def unit(self, name: str) -> Optional[UnitResult]:
        for u in self.units:
            if u.name == name:
                return u
        return None


def _runtime_dir() -> Optional[str]:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return runtime if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK) else None


def domain_cache_path() -> pathlib.Path:
    return session.cache_dir() / "cluster-domain.json"


def api_server() -> str:
    """The API server of the current `oc` context ("" when it cannot be told: then nothing is cached)."""
    if shutil.which("oc") is None:
        return ""
    try:
        done = subprocess.run(["oc", "whoami", "--show-server"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def cached_domain(server: str) -> str:
    """The apps domain demo_run.yml discovered for this API server on an earlier run, or ""."""
    if not server:
        return ""
    try:
        data = json.loads(domain_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    value = data.get(server) if isinstance(data, dict) else None
    return value if isinstance(value, str) else ""


def remember_domain(server: str, domain: str) -> None:
    if not server or not domain:
        return
    path = domain_cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if data.get(server) == domain:
        return
    data[server] = domain
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_time(value: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_results(raw: list) -> List[UnitResult]:
    results = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        started, ended = _parse_time(item.get("started", "")), _parse_time(item.get("ended", ""))
        seconds = (ended - started).total_seconds() if started and ended else 0.0
        results.append(UnitResult(
            name=str(item.get("name", "")),
            status=str(item.get("status", "failed")),
            commands=list(item.get("commands") or []),
            checks=list(item.get("checks") or []),
            messages=[str(m) for m in (item.get("messages") or [])],
            error=str(item.get("error") or ""),
            seconds=seconds,
        ))
    return results


def log_file(demo_id: str, label: str) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in label)
    path = session.logs_dir() / f"{demo_id}-{safe}-{stamp}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_units(demo_id: str, demo_dir: pathlib.Path, units: List[Unit], *, confirmed: str = "",
              stream: bool = False, label: str = "", engine_root: Optional[pathlib.Path] = None) -> RunResult:
    """Run the units in one playbook run; a unit that fails does not stop the next one."""
    engine_root = engine_root or ENGINE_ROOT
    if not units:
        return RunResult(0, [], None)
    if shutil.which("ansible-playbook") is None:
        return RunResult(2, [], None, "ansible-playbook is not on PATH (it ships with Ansible, see ansible/README.md)")
    if os.environ.get("VERBOSE") in ("1", "true", "yes"):
        stream = True
    log_path = log_file(demo_id, label or units[0].name)
    workdir = tempfile.mkdtemp(prefix="zuno-demo-", dir=_runtime_dir())
    os.chmod(workdir, 0o700)
    results_path = pathlib.Path(workdir) / "results.json"
    vars_path = pathlib.Path(workdir) / "vars.json"
    data = {
        "demo_id": demo_id,
        "demo_dir": str(demo_dir),
        "demo_lib": str(engine_root / "ansible" / "demos" / "_lib"),
        "demo_readonly": str(engine_root / "platform" / "demo" / "readonly.py"),
        "demo_units": [{"name": u.name, "file": u.file, "kind": u.kind, "dir": u.dir, "demo": u.demo,
                        "action": u.action or (u.name if u.kind == "action" else ""),
                        "time": u.time or (u.name if u.kind == "step" else ""),
                        "defer_flush": u.defer_flush} for u in units],
        "demo_confirmed": confirmed,
        "demo_results_path": str(results_path),
    }
    needs_cluster = _needs_cluster(demo_dir)
    server = api_server() if needs_cluster else ""
    domain = cached_domain(server)
    if domain:
        data["cluster_base_domain"] = domain
    fd = os.open(str(vars_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    cmd = ["ansible-playbook", "-i", str(engine_root / INVENTORY), str(engine_root / PLAYBOOK), "-e", f"@{vars_path}"]
    env = dict(os.environ)
    env.setdefault("ANSIBLE_NOCOLOR", "1") if not stream else None
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            log.write("$ " + " ".join(cmd) + "\n")
            log.flush()
            proc = subprocess.Popen(cmd, cwd=str(engine_root), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
            assert proc.stdout is not None
            with proc.stdout:
                for line in proc.stdout:
                    log.write(line)
                    if stream:
                        sys.stdout.write(line)
                        sys.stdout.flush()
            rc = proc.wait()
        raw = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else []
        handed = pathlib.Path(str(results_path) + ".domain")
        if not domain and handed.exists():
            remember_domain(server, handed.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        return RunResult(1, [], log_path, f"the runner failed: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    results = parse_results(raw)
    error = ""
    if rc != 0 and not results:
        error = f"demo_run.yml stopped before any unit ran (exit {rc}); see {log_path}"
        tail = _tail(log_path, 12)
        if tail:
            error += "\n" + tail
    ran = {r.name for r in results}
    for unit in units:
        if unit.name not in ran and not error:
            results.append(UnitResult(unit.name, "failed", error="did not run (see the log)"))
    return RunResult(rc, results, log_path, error)


def _needs_cluster(demo_dir: pathlib.Path) -> bool:
    """False only when the demo's manifest says `cluster: false` (the fixtures)."""
    try:
        text = (pathlib.Path(demo_dir) / "demo.yml").read_text(encoding="utf-8")
    except OSError:
        return True
    return not any(line.strip().replace(" ", "") == "cluster:false" for line in text.split("\n"))


def _tail(path: pathlib.Path, lines: int) -> str:
    try:
        content = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    except OSError:
        return ""
    interesting = [l for l in content if "fatal:" in l or "FAILED" in l or "ERROR" in l or "msg" in l]
    return "\n".join((interesting or content)[-lines:])
