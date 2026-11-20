#!/usr/bin/env python3
"""Static guard: an Ansible task that reads or writes a Kubernetes Secret, or sends a secret in an HTTP call, carries `no_log: true`.

Without it the secret's value is printed in the task result on a failure, with `-v`, and in the AAP job log. Two rules, on every
task of ansible/ (playbooks, roles, shared tasks), nested blocks included:

  secret-object  a kubernetes.core.k8s / k8s_info task whose kind is `Secret` (the `kind` argument, or the `kind: Secret` of its
                 definition): the result carries the Secret's `data`;
  secret-http    an ansible.builtin.uri / get_url task whose Authorization / X-Api-Key / Cookie header interpolates anything (`{{ ... }}`),
                 or whose headers, body, url_username or url_password interpolate a variable named like a secret (password, secret, token, api key, credential, bearer).

`no_log` may be any value that is not false (a variable such as `zuno_no_log` is kept as the author's choice). A task that must show
its result takes a reasoned entry in the baseline instead, `platform/security/no-log-baseline.txt` (`path :: task name`, one per line).
A NEW finding fails; a baseline line that matches no finding fails too (the baseline only shrinks).

    python3 platform/security/check_ansible_no_log.py [--list]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
ANSIBLE = REPO / "ansible"
BASELINE = pathlib.Path(__file__).resolve().parent / "no-log-baseline.txt"
SKIP_DIRS = ("clusters", "kustomize", "inventories", "collections")
SECRET_WORD = re.compile(r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|bearer)", re.I)
JINJA = re.compile(r"\{\{.*?\}\}", re.S)
NOT_A_VALUE = re.compile(r"(_name|_namespace|_enabled|_mode|_present|_exists|_found|_ref)$")
KEYWORDS = {"name", "when", "register", "tags", "vars", "loop", "with_items", "with_dict", "with_list", "loop_control", "until",
            "retries", "delay", "changed_when", "failed_when", "ignore_errors", "no_log", "become", "become_user", "delegate_to",
            "run_once", "environment", "notify", "block", "rescue", "always", "check_mode", "ignore_unreachable", "any_errors_fatal",
            "throttle", "module_defaults", "args", "async", "poll", "connection", "diff", "listen", "delegate_facts"}
TASK_LISTS = ("tasks", "pre_tasks", "post_tasks", "handlers")


def short(module: str) -> str:
    return module.rsplit(".", 1)[-1]


def walk(seq: Any) -> Iterator[Dict[str, Any]]:
    for task in seq or []:
        if not isinstance(task, dict):
            continue
        for key in ("block", "rescue", "always"):
            if key in task:
                yield from walk(task[key])
        if any(k not in KEYWORDS for k in task):
            yield task


def module_of(task: Dict[str, Any]) -> str:
    return next(k for k in task if k not in KEYWORDS)


def has_no_log(task: Dict[str, Any]) -> bool:
    value = task.get("no_log")
    return value is not None and str(value).strip().lower() not in ("false", "no", "0", "")


def secret_variables(text: str) -> bool:
    for expression in JINJA.findall(text):
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression):
            if SECRET_WORD.search(name) and not NOT_A_VALUE.search(name):
                return True
    return False


def rule_of(task: Dict[str, Any]) -> Optional[str]:
    module = short(module_of(task))
    args = task[module_of(task)]
    if module in ("k8s", "k8s_info") and isinstance(args, dict):
        definition = args.get("definition") or args.get("resource_definition")
        kinds = [args.get("kind")]
        if isinstance(definition, dict):
            kinds.append(definition.get("kind"))
        if isinstance(definition, str) and re.search(r"^\s*kind:\s*Secret\s*$", definition, re.M):
            kinds.append("Secret")
        if "Secret" in kinds:
            return "secret-object"
    if module in ("uri", "get_url") and isinstance(args, dict):
        headers = args.get("headers")
        if isinstance(headers, dict) and any(re.fullmatch(r"(authorization|x-api-key|cookie)", str(k), re.I) and JINJA.search(str(v))
                                             for k, v in headers.items()):
            return "secret-http"
        sent = json.dumps({k: args.get(k) for k in ("headers", "body", "url_username", "url_password")}, default=str)
        if secret_variables(sent):
            return "secret-http"
    return None


def task_lists(document: Any) -> Iterator[Any]:
    if isinstance(document, list):
        for item in document:
            if isinstance(item, dict) and any(k in item for k in TASK_LISTS):
                for key in TASK_LISTS:
                    yield item.get(key)
            else:
                yield [item]


def findings(root: pathlib.Path = ANSIBLE, repo: pathlib.Path = REPO) -> List[Tuple[str, str, str]]:
    """[(relative path, task name, rule)] of the tasks that need `no_log` and lack it."""
    out = []
    for path in sorted(root.rglob("*.yml")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            document = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        for tasks in task_lists(document):
            for task in walk(tasks):
                rule = rule_of(task)
                if rule and not has_no_log(task):
                    out.append((str(path.relative_to(repo)), str(task.get("name", "?")), rule))
    return out


def load_baseline(path: pathlib.Path = BASELINE) -> Set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")}


def key(path: str, name: str) -> str:
    return f"{path} :: {name}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print every finding, baseline included")
    args = ap.parse_args(argv)
    found = findings()
    baseline = load_baseline()
    keys = {key(p, n) for p, n, _ in found}
    new = [(p, n, r) for p, n, r in found if key(p, n) not in baseline]
    stale = sorted(baseline - keys)
    if args.list:
        for p, n, r in found:
            print(f"{r:14} {key(p, n)}")
    for p, n, r in new:
        print(f"FAIL {p}: task '{n}' ({r}) has no no_log: true", file=sys.stderr)
    for line in stale:
        print(f"FAIL baseline line matches no finding any more (remove it): {line}", file=sys.stderr)
    print(f"RESULT: {'FAIL' if new or stale else 'PASS'} - {len(found) - len(new)} baselined, {len(new)} new, {len(stale)} stale")
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
