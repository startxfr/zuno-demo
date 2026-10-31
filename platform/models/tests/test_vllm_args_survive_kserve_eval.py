"""Every vLLM argument of the models chart reaches vLLM intact through KServe's start script.

KServe's LLMInferenceService template starts vLLM with
    bash -c '... eval "exec vllm serve /mnt/models ... $@"' -- <container args>
so the container args are re-parsed by the shell once more. A bare JSON value loses its double
quotes there: qwen35-9b crash-looped on 2026-10-25 with
`--default-chat-template-kwargs {"enable_thinking": false}` ("invalid loads value:
'{enable_thinking:false}'"), fixed in 60d6e81e by single-quoting the JSON inside the argument.

This test renders the chart, passes each LLMInferenceService's `main` container args through the
same `eval` in a real bash, and checks that vLLM would get exactly the intended arguments: each
rendered arg, minus one pair of enclosing single quotes. JSON-valued flags must parse.

Run from the repository root (needs helm and bash):
    python3 -m pytest -q platform/models/tests
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "gitops" / "charts" / "models"
# vLLM flags whose value is JSON.
JSON_FLAGS = {
    "--default-chat-template-kwargs", "--override-generation-config", "--hf-overrides",
    "--kv-transfer-config", "--compilation-config", "--speculative-config", "--limit-mm-per-prompt",
}
# The same re-parse as KServe's template, with printf in place of vllm serve.
KSERVE_EVAL = "eval \"exec printf '%s\\\\0' $@\""

pytestmark = pytest.mark.skipif(not shutil.which("helm"), reason="helm is not installed")


def through_kserve_eval(args):
    out = subprocess.run(["bash", "-c", KSERVE_EVAL, "--", *args], capture_output=True, check=True)
    return out.stdout.decode().split("\0")[:-1]


def intended(arg):
    return arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] == "'" else arg


def check(args):
    """The problems vLLM would see with these container args, as messages."""
    got = through_kserve_eval(args)
    want = [intended(a) for a in args]
    if got != want:
        return [f"the shell eval changes the args: rendered {args!r}, vLLM gets {got!r}"]
    problems = []
    for flag, value in zip(got, got[1:]):
        if flag in JSON_FLAGS:
            try:
                json.loads(value)
            except ValueError as exc:
                problems.append(f"{flag} {value!r} is not JSON after the eval: {exc}")
    return problems


def rendered_model_args(*helm_args):
    out = subprocess.run(["helm", "template", "models", str(CHART), *helm_args],
                         capture_output=True, text=True, check=True).stdout
    found = {}
    for doc in yaml.safe_load_all(out):
        if not doc or doc.get("kind") != "LLMInferenceService":
            continue
        for container in ((doc.get("spec") or {}).get("template") or {}).get("containers") or []:
            if container.get("name") == "main":
                found[doc["metadata"]["name"]] = [str(a) for a in container.get("args") or []]
    return found


def test_the_harness_catches_the_2026_10_25_crash():
    bare = ["--default-chat-template-kwargs", json.dumps({"enable_thinking": False})]
    assert check(bare), "a bare JSON argument must be reported"
    fixed = ["--default-chat-template-kwargs", "'" + json.dumps({"enable_thinking": False}) + "'"]
    assert check(fixed) == []


@pytest.mark.parametrize("helm_args", [
    (),
    # every optional arg block on: tracing, and qwen35's chat-template kwargs (the 2026-10-25 case)
    ("--set", "tracing.enabled=true",
     "--set-json", 'qwen35Model.defaultChatTemplateKwargs={"enable_thinking":false,"note":"two words"}'),
])
def test_every_model_args_survive_the_kserve_eval(helm_args):
    models = rendered_model_args(*helm_args)
    assert models, "the chart renders no LLMInferenceService"
    problems = {name: p for name, args in models.items() if (p := check(args))}
    assert not problems, problems
