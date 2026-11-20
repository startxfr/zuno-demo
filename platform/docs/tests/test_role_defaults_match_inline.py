"""A role's defaults/main.yml and the inline `var | default('literal')` of its tasks must agree (best-practices audit, lot 3).

The roles repeat a literal as an inline default instead of declaring the variable: `models_lmeval_namespace | default('zuno-ai-run')`
28 times. Declaring it once in defaults/main.yml is clearer, but two sources of one value drift: this test fails when a plain-string
default of a role's defaults file differs from an inline default of the same variable in the same role. It also pins the six
variables declared by the audit, so removing one is a conscious choice.

Run from the repository root:
    python3 platform/docs/tests/test_role_defaults_match_inline.py
"""
from __future__ import annotations

import pathlib
import re
import unittest

import yaml

ROLES = pathlib.Path(__file__).resolve().parents[3] / "ansible" / "roles"
INLINE = re.compile(r"\b([a-z][a-z0-9_]*)\s*\|\s*default\(\s*'([^'{}]*)'\s*\)")
DECLARED_BY_THE_AUDIT = {
    "day3": {"lightspeed_namespace": "openshift-lightspeed"},
    "mlops": {"mlops_namespace": "zuno-mlops"},
    "models": {"models_reconcile_namespace": "zuno-ai-run", "models_lmeval_namespace": "zuno-ai-run"},
    "lightspeed_config": {"lightspeed_config_namespace": "openshift-lightspeed"},
    "openshift_ai": {"openshift_ai_maas_db_copy_namespace": "redhat-ai-gateway-infra"},
}


def role_defaults(role: pathlib.Path) -> dict:
    path = role / "defaults" / "main.yml"
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


class RoleDefaults(unittest.TestCase):
    def test_no_inline_default_disagrees_with_the_defaults_file(self):
        conflicts = []
        for role in sorted(p for p in ROLES.iterdir() if p.is_dir()):
            defaults = role_defaults(role)
            for path in role.rglob("*.yml"):
                if "defaults" in path.parts:
                    continue
                for var, literal in INLINE.findall(path.read_text()):
                    if isinstance(defaults.get(var), str) and defaults[var] != literal:
                        conflicts.append(f"{path.relative_to(ROLES.parent.parent)}: {var} | default('{literal}') but defaults/main.yml says {defaults[var]!r}")
        self.assertEqual(conflicts, [], "an inline default and its role's defaults file disagree: change one so they match")

    def test_the_variables_declared_by_the_audit_are_there_with_their_values(self):
        for role, expected in DECLARED_BY_THE_AUDIT.items():
            defaults = role_defaults(ROLES / role)
            for var, value in expected.items():
                self.assertEqual(defaults.get(var), value, f"{role}: {var}")

    def test_each_declared_variable_is_used_inline_with_the_same_literal(self):
        for role, expected in DECLARED_BY_THE_AUDIT.items():
            used = {}
            for path in (ROLES / role).rglob("*.yml"):
                if "defaults" in path.parts:
                    continue
                for var, literal in INLINE.findall(path.read_text()):
                    used.setdefault(var, set()).add(literal)
            for var, value in expected.items():
                self.assertEqual(used.get(var), {value}, f"{role}: {var} is used with {used.get(var)}")


if __name__ == "__main__":
    unittest.main()
