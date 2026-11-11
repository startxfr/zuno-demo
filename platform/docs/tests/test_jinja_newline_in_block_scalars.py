"""check_docs: no `\n` inside `{{ }}` in a YAML block scalar of ansible/ (WP-211, 2026-11-08).

On ansible-core 2.19 a `{{ }}` expression inside a `>-` or `|` block keeps "\n" as the two characters backslash + n.
The openshift_oauth role glued two PEM certificates that way and degraded two clusteroperators. These cases feed the
helper synthetic YAML; the real tree is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_jinja_newline_in_block_scalars.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

THE_2026_11_08_CASE = '''
- name: "openshift_oauth | publish the supplied Keycloak CA + router CA as keycloak-serving-ca (external mode)"
  kubernetes.core.k8s:
    definition:
      data:
        ca.crt: >-
          {{ ((zuno_keycloak_ca_pem + "\\n") if (zuno_keycloak_ca_pem | length > 0) else '')
             + (_openshift_oauth_router_ca.resources[0].data['ca-bundle.crt']) }}
  when: zuno_keycloak_external_mode | bool
'''

THE_FIX = '''
- name: "openshift_oauth | publish the supplied Keycloak CA"
  kubernetes.core.k8s:
    definition:
      data:
        ca.crt: >-
          {{ ((zuno_keycloak_ca_pem + _openshift_oauth_nl) if (zuno_keycloak_ca_pem | length > 0) else '') }}
  vars:
    _openshift_oauth_nl: "\\n"
'''

STATEMENT_IS_FINE = '''
  vars:
    _policies: >-
      {%- set _ = lines.append('path "zuno/data/' ~ key ~ '" {\\n  capabilities = ["read"]\\n}') -%}
      {{ out }}
'''

DOUBLE_QUOTED_IS_FINE = '''
- ansible.builtin.set_fact:
    joined: "{{ a ~ '\\n' ~ b }}"
'''

MULTI_LINE_EXPRESSION = '''
- ansible.builtin.set_fact:
    pem: >-
      {{ first
         + ('\\n' + second) }}
    other: plain
'''


class JinjaNewlineInBlockScalars(unittest.TestCase):
    def test_the_2026_11_08_case_is_reported_on_its_line(self):
        findings = check_docs.jinja_newline_findings("install.yml", THE_2026_11_08_CASE)
        self.assertEqual(len(findings), 1)
        self.assertIn("install.yml:7:", findings[0].message)

    def test_the_fix_passes(self):
        self.assertEqual(check_docs.jinja_newline_findings("install.yml", THE_FIX), [])

    def test_a_statement_block_passes(self):
        # Inside {% %} the escape does become a newline (the live Vault policies prove it).
        self.assertEqual(check_docs.jinja_newline_findings("run_configure_job.yml", STATEMENT_IS_FINE), [])

    def test_a_double_quoted_scalar_passes(self):
        self.assertEqual(check_docs.jinja_newline_findings("x.yml", DOUBLE_QUOTED_IS_FINE), [])

    def test_an_expression_over_several_lines_is_reported(self):
        findings = check_docs.jinja_newline_findings("x.yml", MULTI_LINE_EXPRESSION)
        self.assertEqual(len(findings), 1)
        self.assertIn("x.yml:5:", findings[0].message)

    def test_the_real_tree_is_clean(self):
        self.assertEqual(check_docs.check_jinja_newline_in_block_scalars(), [])


if __name__ == "__main__":
    unittest.main()
