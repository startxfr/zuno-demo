"""check_ansible_no_log: the static no_log guard, on small fixture trees, and on the real ansible/ tree.

Run from the repository root:
    python3 platform/security/tests/test_check_ansible_no_log.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_ansible_no_log as c  # noqa: E402


def scan(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "ansible"
        (root / "roles" / "r" / "tasks").mkdir(parents=True)
        (root / "roles" / "r" / "tasks" / "main.yml").write_text(textwrap.dedent(text))
        return [(name, rule) for _, name, rule in c.findings(root, pathlib.Path(tmp))]


class Rules(unittest.TestCase):
    def test_a_secret_read_without_no_log_is_found(self):
        self.assertEqual(scan("""
            - name: read it
              kubernetes.core.k8s_info: {kind: Secret, name: x, namespace: y}
              register: s
            """), [("read it", "secret-object")])

    def test_no_log_clears_it_and_false_does_not(self):
        base = "- name: read it\n  kubernetes.core.k8s_info: {{kind: Secret, name: x}}\n  no_log: {}\n"
        self.assertEqual(scan(base.format("true")), [])
        self.assertEqual(scan(base.format("\"{{ zuno_no_log | default(true) }}\"")), [])
        self.assertEqual(scan(base.format("false")), [("read it", "secret-object")])

    def test_a_definition_of_kind_secret_is_found_other_kinds_are_not(self):
        self.assertEqual(scan("""
            - name: write it
              kubernetes.core.k8s:
                definition: {kind: Secret, metadata: {name: x}}
            - name: write a configmap
              kubernetes.core.k8s:
                definition: {kind: ConfigMap, metadata: {name: x}}
            - name: read a configmap
              kubernetes.core.k8s_info: {kind: ConfigMap, name: x}
            """), [("write it", "secret-object")])

    def test_blocks_are_walked(self):
        self.assertEqual(scan("""
            - name: outer
              block:
                - name: inner
                  kubernetes.core.k8s_info: {kind: Secret}
              rescue:
                - name: rescue
                  kubernetes.core.k8s: {kind: Secret, state: absent}
            """), [("inner", "secret-object"), ("rescue", "secret-object")])

    def test_http_with_a_secret_variable_is_found_a_fixed_token_is_not(self):
        self.assertEqual(scan("""
            - name: real
              ansible.builtin.uri:
                url: https://x
                headers: {Authorization: "Bearer {{ _tok.stdout }}"}
            - name: fixed
              ansible.builtin.uri:
                url: https://x
                headers: {Authorization: "Bearer invalid"}
            - name: names only
              ansible.builtin.uri:
                url: https://x
                headers: {X: "{{ token_secret_name }}"}
            """), [("real", "secret-http")])


class RealTree(unittest.TestCase):
    def test_every_secret_task_of_ansible_carries_no_log_or_is_baselined(self):
        found = c.findings()
        baseline = c.load_baseline()
        self.assertEqual([f for f in found if c.key(f[0], f[1]) not in baseline], [])
        self.assertEqual(sorted(baseline - {c.key(p, n) for p, n, _ in found}), [])


if __name__ == "__main__":
    unittest.main()
