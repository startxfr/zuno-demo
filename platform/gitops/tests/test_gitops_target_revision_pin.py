"""The branch an Argo CD Application follows can only be set through ansible/tasks/apply_gitops_app.yml, which always
finds it (2026-11-20: AAP job 1482 and six worktree runs re-applied Applications at the manifests' `main`).

Run from the repository root:
    python3 platform/gitops/tests/test_gitops_target_revision_pin.py
"""
from __future__ import annotations

import pathlib
import re
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
ANSIBLE = REPO / "ansible"
APPLY = ANSIBLE / "tasks" / "apply_gitops_app.yml"
RESOLVE = ANSIBLE / "tasks" / "resolve_gitops_target_revision.yml"
WRITE_MODULES = ("kubernetes.core.k8s", "k8s", "kubernetes.core.k8s_json_patch")

# Writes of an Application that never touch spec.source, so they cannot set the branch. Each with its reason.
NO_SOURCE_WRITERS = {
    "ansible/tasks/force_argocd_sync.yml": "patches `operation` only (a sync request)",
    "ansible/tasks/delete_gitops_app.yml": "patches metadata.finalizers only, right before the delete",
    "ansible/playbooks/vault_migrate_kms_raft.yml": "patches spec.syncPolicy only (auto-sync off during the migration)",
    "ansible/roles/argocd/tasks/install.yml": "patches spec.project and spec.destination only (WP-224 move)",
}


def tasks_of(node):
    """Every task dict in a task file, blocks included."""
    if isinstance(node, list):
        for item in node:
            yield from tasks_of(item)
    elif isinstance(node, dict):
        yield node
        for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks", "handlers"):
            if key in node:
                yield from tasks_of(node[key])


def application_writes():
    """(file, task) for every module call that creates or patches an argoproj Application."""
    for path in sorted(ANSIBLE.rglob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        for task in tasks_of(doc):
            for module in WRITE_MODULES:
                args = task.get(module)
                if not isinstance(args, dict) or args.get("state") == "absent":
                    continue
                definition = args.get("definition")
                kind = args.get("kind") or (definition.get("kind") if isinstance(definition, dict) else None)
                if kind == "Application" or (isinstance(definition, str) and "Application" in definition):
                    yield path.relative_to(REPO).as_posix(), task, args


class TargetRevisionPin(unittest.TestCase):
    def test_every_application_write_goes_through_apply_gitops_app(self):
        stray = []
        for rel, task, args in application_writes():
            if rel == "ansible/tasks/apply_gitops_app.yml":
                continue
            if rel not in NO_SOURCE_WRITERS:
                stray.append(f"{rel}: {task.get('name')}")
                continue
            definition = args.get("definition")
            self.assertIsInstance(definition, dict, f"{rel}: {task.get('name')} must use an inline definition")
            self.assertNotIn("source", (definition.get("spec") or {}),
                             f"{rel}: {task.get('name')} writes spec.source - only apply_gitops_app.yml may")
        self.assertEqual(stray, [], "an Application is written outside ansible/tasks/apply_gitops_app.yml, so its "
                                   "targetRevision skips the confidential.yml / branch-pin.yml / cluster-file loaders")

    def test_no_shell_applies_a_gitops_app_manifest(self):
        pattern = re.compile(r"(oc|kubectl)\s+(apply|create|replace)\b[^\n]*gitops/apps/")
        hits = [p.relative_to(REPO).as_posix() for p in ANSIBLE.rglob("*.yml") if pattern.search(p.read_text())]
        self.assertEqual(hits, [])

    def test_apply_gitops_app_resolves_the_revision_before_rendering(self):
        names = [t.get("name", "") for t in tasks_of(yaml.safe_load(APPLY.read_text()))]

        def index(fragment):
            found = [i for i, n in enumerate(names) if fragment in n]
            self.assertTrue(found, f"no task named like {fragment!r} in apply_gitops_app.yml")
            return found[0]

        confidential = index("load ansible/confidential.yml")
        pin = index("load ansible/branch-pin.yml")
        fallback = index("the cluster's committed target revision")
        render = index("render the Application manifest")
        self.assertLess(confidential, pin)
        self.assertLess(pin, fallback, "the cluster file is a FALLBACK: -e, confidential.yml and branch-pin.yml win")
        self.assertLess(fallback, render)

    def test_the_fallback_reads_only_the_one_variable(self):
        include = next(t for t in tasks_of(yaml.safe_load(APPLY.read_text()))
                       if "the cluster's committed target revision" in t.get("name", ""))
        self.assertEqual(include.get("when"), "zuno_gitops_target_revision is not defined")
        self.assertIn("resolve_gitops_target_revision.yml", include["ansible.builtin.include_tasks"])
        loads = [t for t in tasks_of(yaml.safe_load(RESOLVE.read_text())) if "ansible.builtin.include_vars" in t]
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0]["ansible.builtin.include_vars"].get("name"), "_gitops_cluster_file_vars",
                         "a namespaced include_vars: the rest of the cluster file must not leak into every role")

    def test_every_cluster_file_names_its_branch(self):
        for path in sorted((ANSIBLE / "clusters").glob("*.yml")):
            value = (yaml.safe_load(path.read_text()) or {}).get("zuno_gitops_target_revision")
            self.assertIsInstance(value, str, f"{path.name} must set zuno_gitops_target_revision")
            self.assertRegex(value, r"^[A-Za-z0-9._/-]+$", path.name)


if __name__ == "__main__":
    unittest.main()
