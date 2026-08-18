"""ADR-0511 (WP-54) token-budget ledger tests.

Covers the precedence semantics the policy file's header documents:
group budget as the always-enforced outer ceiling; project drawn first
when a verified binding is present, user as its fallback; user-only
outside project context; explicit denial detail; per-class fail modes
on a broken config. Pure in-process tests over an injected config -
no cluster, no Redis, no model calls.
"""
from __future__ import annotations

import unittest

from app.quota import QuotaDenial, TokenBudgetLedger

CONFIG = {
    "classes": {
        "standard": {
            "fail_mode": "open",
            "tokens": {
                # group deliberately roomy: it is checked FIRST (outer
                # ceiling), so user/project denials are only observable
                # while the group pool still has headroom
                "user": {"budget": 100, "window": "1h"},
                "group": {"budget": 1000, "window": "1h"},
                "project": {"budget": 150, "window": "1h"},
            },
        },
        "intensive": {
            "fail_mode": "closed",
            "tokens": {
                "user": {"budget": 50, "window": "1h"},
                "group": {"budget": 80, "window": "1h"},
                "project": {"budget": 60, "window": "1h"},
            },
        },
    },
    "precedence": {"in_project_context": ["project", "user", "group"], "default": ["user", "group"]},
}

NOW = 1_700_000_000.0  # fixed instant - all tests stay inside one window
GROUPS = ["consultant"]


class QuotaLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = TokenBudgetLedger(config=CONFIG)

    def test_allows_within_budget_and_denies_user_exhaustion(self) -> None:
        self.assertIsNone(self.ledger.check("standard", "u1", GROUPS, None, now=NOW))
        self.ledger.consume("standard", "u1", GROUPS, None, 100, now=NOW)
        denial = self.ledger.check("standard", "u1", GROUPS, None, now=NOW)
        self.assertIsInstance(denial, QuotaDenial)
        self.assertEqual(denial.dimension, "user")
        self.assertEqual(denial.detail()["error"], "quota_exceeded")
        self.assertEqual(denial.detail()["budget_tokens"], 100)
        # a different user in the same groups is untouched (their own user
        # budget is fresh; the shared group ceiling still has headroom)
        self.assertIsNone(self.ledger.check("standard", "u2", GROUPS, None, now=NOW))

    def test_project_drawn_first_then_user_fallback(self) -> None:
        # exhaust the project budget: consumption attributes to the project,
        # never touching the user's own budget
        self.ledger.consume("standard", "u1", GROUPS, "proj-1", 150, now=NOW)
        self.assertIsNone(self.ledger.check("standard", "u1", GROUPS, "proj-1", now=NOW))
        # further consumption in project context now falls back to the user
        self.ledger.consume("standard", "u1", GROUPS, "proj-1", 100, now=NOW)
        denial = self.ledger.check("standard", "u1", GROUPS, "proj-1", now=NOW)
        self.assertEqual(denial.dimension, "user")
        # outside project context the user budget is equally exhausted -
        # proof the fallback drew from the user, not the project, pool
        self.assertEqual(self.ledger.check("standard", "u1", GROUPS, None, now=NOW).dimension, "user")

    def test_group_ceiling_denies_regardless_of_project_headroom(self) -> None:
        # 1000 group tokens consumed across users exhausts the shared pool;
        # a third user with untouched user AND project budgets is still
        # denied - the group ceiling is outermost, always enforced
        for sub, tokens in (("u1", 100), ("u2", 100), ("u3", 100), ("u4", 100),
                            ("u5", 100), ("u6", 100), ("u7", 100), ("u8", 100),
                            ("u9", 100), ("u10", 100)):
            self.ledger.consume("standard", sub, GROUPS, None, tokens, now=NOW)
        denial = self.ledger.check("standard", "u-fresh", GROUPS, "proj-untouched", now=NOW)
        self.assertEqual(denial.dimension, "group")

    def test_windows_roll_over(self) -> None:
        self.ledger.consume("standard", "u1", GROUPS, None, 100, now=NOW)
        self.assertIsNotNone(self.ledger.check("standard", "u1", GROUPS, None, now=NOW))
        one_window_later = NOW + 3600 + 1
        self.assertIsNone(self.ledger.check("standard", "u1", GROUPS, None, now=one_window_later))

    def test_unknown_class_fails_closed(self) -> None:
        denial = self.ledger.check("nonexistent", "u1", GROUPS, None, now=NOW)
        self.assertIsNotNone(denial)

    def test_fail_modes_read_from_config(self) -> None:
        self.assertTrue(self.ledger.fail_open("standard"))
        self.assertFalse(self.ledger.fail_open("intensive"))
        broken = TokenBudgetLedger(config={})
        self.assertFalse(broken.fail_open("intensive"))
        self.assertIsNotNone(broken.check("intensive", "u1", GROUPS, None, now=NOW))

    def test_generated_config_file_loads(self) -> None:
        # the committed, generated app/quota_budgets.yaml must itself be a
        # valid config with the standard class present (drift against the
        # policy file is caught separately by the generator's --check)
        real = TokenBudgetLedger()
        self.assertIsNone(real._config_error)
        self.assertIn("standard", real._classes)
        self.assertIsNone(real.check("standard", "fresh-user", GROUPS, None, now=NOW))


if __name__ == "__main__":
    unittest.main()
