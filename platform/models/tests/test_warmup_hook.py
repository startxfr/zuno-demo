"""The vLLM warm-up postStart hook (templates/_warmup.tpl) renders only where enabled and is safe.

A cold --enforce-eager qwen pod compiles its kernels on its first request (2026-10-31: past the 60 s
MaaS timeout). The hook warms the model before the pod becomes Ready. It must never fail the
container (always exit 0), must verify TLS against the pod's serving CA, and must name the model.

Run from the repository root (needs helm and sh):
    python3 -m pytest -q platform/models/tests
"""
from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "gitops" / "charts" / "models"

pytestmark = pytest.mark.skipif(not shutil.which("helm"), reason="helm is not installed")


def hooks(*helm_args):
    out = subprocess.run(["helm", "template", "models", str(CHART), *helm_args],
                         capture_output=True, text=True, check=True).stdout
    found = {}
    for doc in yaml.safe_load_all(out):
        if not doc or doc.get("kind") != "LLMInferenceService":
            continue
        main = [c for c in doc["spec"]["template"]["containers"] if c["name"] == "main"][0]
        found[doc["metadata"]["name"]] = main.get("lifecycle")
    return found


def script(name="qwen35-9b-wesh", *helm_args):
    return hooks(*helm_args)[name]["postStart"]["exec"]["command"][2]


def test_only_the_enabled_model_gets_the_hook():
    got = hooks()
    assert got["qwen35-9b-wesh"] is not None
    assert got["qwen35-9b"] is None and got["qwen36-27b-instruct"] is None and got["gpt-oss-20b"] is None


def test_the_hook_can_be_switched_off():
    assert hooks("--set", "weshModel.warmup.enabled=false")["qwen35-9b-wesh"] is None


def test_the_script_is_valid_verifies_tls_names_the_model_and_never_fails():
    text = script()
    subprocess.run(["sh", "-n"], input=text, text=True, check=True)
    assert "--cacert" in text and " -k " not in text and "--insecure" not in text
    assert '"qwen3.5-9b-wesh"' in text
    assert text.rstrip().endswith("exit 0")


def _fake_curl(tmp_path, healthy=True):
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        'case "$*" in *"/health"*) ' + ("exit 0" if healthy else "exit 7") + ";; esac\n"
        "printf 200\n"
    )
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}


def test_the_script_warms_in_steps_and_exits_0(tmp_path):
    out = subprocess.run(["sh", "-c", script()], env=_fake_curl(tmp_path), cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    for step in ("1 concurrent: HTTP 200", "2 concurrent: HTTP 200 200", "4 concurrent: HTTP 200 200 200 200", "done in"):
        assert step in out.stdout, out.stdout


def test_an_unhealthy_model_is_skipped_with_exit_0(tmp_path):
    text = script("qwen35-9b-wesh", "--set", "weshModel.warmup.waitSeconds=1")
    out = subprocess.run(["sh", "-c", text], env=_fake_curl(tmp_path, healthy=False), cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "skipping" in out.stdout, out.stdout
