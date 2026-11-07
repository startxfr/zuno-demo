"""ADR-0603 M16 (WP-226) tests for render_release_digests.py.

Every test runs against a throwaway copy of the real gitops/charts/*/values.yaml
files and a synthetic ledger under a temp directory; the repository is never
written. Where helm is on PATH, the rendered values are also passed through the
real chart templates to prove the Deployment gets repository@digest,
IfNotPresent and no :latest image trigger.

Run from platform/supply-chain:

    python3 tests/test_render_release_digests.py
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

TESTS_DIR = Path(__file__).resolve().parent
SUPPLY_CHAIN_DIR = TESTS_DIR.parent
REPO_ROOT = SUPPLY_CHAIN_DIR.parents[1]
sys.path.insert(0, str(SUPPLY_CHAIN_DIR))
import render_release_digests as rrd  # noqa: E402

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
PINS = [
    ("gitops/charts/ai-gateway/values.yaml", "image.tag"),
    ("gitops/charts/mcp-gateway/values.yaml", "image.tag"),
    ("gitops/charts/mcp-gateway/values.yaml", "okf.fetch.image.tag"),
    ("gitops/charts/mlops/values.yaml", "images.mlops.tag"),
]


def _scratch() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="wp226-render-"))
    for values in REPO_ROOT.glob(rrd.CHARTS_GLOB):
        target = tmp / values.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(values, target)
    (tmp / "platform" / "supply-chain").mkdir(parents=True)
    return tmp


def _ledger(root: Path, pins) -> Path:
    path = root / "platform" / "supply-chain" / "pinned-releases.yaml"
    path.write_text(yaml.safe_dump({"releases": [{"release_tag": "v9.9.9", "pins": pins}]}, sort_keys=False))
    return path


def _pin(chart_values, path, digest=DIGEST_A, signed=True):
    pin = {"chart_values": chart_values, "path": path, "tag": "v9.9.9", "digest": digest}
    if signed is not None:
        pin["signed"] = signed
    return pin


def _run(root: Path, *argv) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return rrd.main(list(argv), root=root)


def _value(root: Path, chart_values: str, path: str):
    return rrd._lookup(yaml.safe_load((root / chart_values).read_text()), path)


def test_render_writes_each_digest_and_keeps_comments() -> None:
    root = _scratch()
    _ledger(root, [_pin(c, p) for c, p in PINS])
    before = (root / PINS[0][0]).read_text()
    assert _run(root, "--release", "v9.9.9") == 0
    for chart_values, path in PINS:
        assert _value(root, chart_values, rrd.digest_path(path)) == DIGEST_A, (chart_values, path)
        assert _value(root, chart_values, path) == "latest", "the tag is left alone"
    after = (root / PINS[0][0]).read_text()
    comments = [line for line in before.splitlines() if line.strip().startswith("#")]
    assert comments == [line for line in after.splitlines() if line.strip().startswith("#")]
    assert _run(root, "--check") == 0


def test_null_or_unsigned_digest_is_refused_and_nothing_written() -> None:
    for bad in (_pin(*PINS[1], digest=None), _pin(*PINS[1], signed=None), _pin(*PINS[1], digest="sha256:abc")):
        root = _scratch()
        _ledger(root, [_pin(*PINS[0]), bad])
        snapshot = (root / PINS[0][0]).read_text()
        assert _run(root, "--release", "v9.9.9") == 1
        assert (root / PINS[0][0]).read_text() == snapshot, "a refusal writes nothing"


def test_chart_without_a_digest_key_is_refused() -> None:
    root = _scratch()
    _ledger(root, [_pin("gitops/charts/keycloak/values.yaml", "image.tag")])
    assert _run(root, "--release", "v9.9.9") == 1


def test_unknown_release_is_refused() -> None:
    root = _scratch()
    _ledger(root, [_pin(*PINS[0])])
    assert _run(root, "--release", "v0.0.0") == 1


def test_dry_run_writes_nothing() -> None:
    root = _scratch()
    _ledger(root, [_pin(*PINS[0])])
    assert _run(root, "--release", "v9.9.9", "--dry-run") == 0
    assert _value(root, PINS[0][0], "image.digest") == ""


def test_check_refuses_a_hand_edited_digest() -> None:
    root = _scratch()
    _ledger(root, [_pin(*PINS[0])])
    assert _run(root, "--release", "v9.9.9") == 0
    target = root / PINS[0][0]
    target.write_text(target.read_text().replace(DIGEST_A, DIGEST_B))
    assert _run(root, "--check") == 1


def test_check_ignores_third_party_digests() -> None:
    root = _scratch()
    _ledger(root, [])
    assert _value(root, "gitops/charts/mcp-k8s/values.yaml", "image.digest"), "fixture: mcp-k8s pins by digest"
    assert _run(root, "--check") == 0


def test_clear_returns_every_chart_to_latest() -> None:
    root = _scratch()
    _ledger(root, [_pin(c, p) for c, p in PINS])
    assert _run(root, "--release", "v9.9.9") == 0
    assert _run(root, "--clear") == 0
    assert all(not value for _, _, value in rrd.rendered_digests(root))


def test_rendered_chart_pins_the_deployment() -> None:
    if shutil.which("helm") is None:
        print("  skip: helm not on PATH")
        return
    root = _scratch()
    _ledger(root, [_pin("gitops/charts/ai-gateway/values.yaml", "image.tag")])
    assert _run(root, "--release", "v9.9.9") == 0
    chart = REPO_ROOT / "gitops" / "charts" / "ai-gateway"
    rendered = subprocess.run(
        ["helm", "template", "t", str(chart), "-f", str(root / "gitops/charts/ai-gateway/values.yaml"),
         "--show-only", "templates/deployment.yaml"],
        capture_output=True, text=True, check=True).stdout
    doc = yaml.safe_load(rendered)
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].endswith("/zuno-ai-build/ai-gateway@" + DIGEST_A), container["image"]
    assert container["imagePullPolicy"] == "IfNotPresent"
    assert "image.openshift.io/triggers" not in (doc["metadata"].get("annotations") or {})
    latest = yaml.safe_load(subprocess.run(
        ["helm", "template", "t", str(chart), "--show-only", "templates/deployment.yaml"],
        capture_output=True, text=True, check=True).stdout)
    assert latest["spec"]["template"]["spec"]["containers"][0]["image"].endswith(":latest")
    assert "image.openshift.io/triggers" in latest["metadata"]["annotations"]


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure
            failed += 1
            print(f"FAIL {name}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
