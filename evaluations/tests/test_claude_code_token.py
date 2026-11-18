"""Claude Code's apiKeyHelper for Praxis (ADR-0619 clause 8, WP-298): the refresh-token cache, the refresh, the
device sign-in's polling and what reaches stderr. No network: Keycloak is a fake `post`.

Run from the repository root: python3 evaluations/tests/test_claude_code_token.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "claude-code"))

import zuno_claude_token as z  # noqa: E402

ISSUER = "https://keycloak.apps.example.test/realms/zuno"
ACCESS, REFRESH, ROTATED = "acc.ess.token-1", "refresh-token-1", "refresh-token-2"


class FakeKeycloak:
    """Answers the token, device and logout endpoints from a script of (status, body); records the calls."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, form):
        self.calls.append((url.rsplit("/", 1)[-1], dict(form)))
        return self.answers.pop(0)


class Cache(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="zuno-claude-code-")) / "claude-code"
        self.env = {"ZUNO_ISSUER": ISSUER, "ZUNO_CLAUDE_CODE_CACHE": str(self.dir)}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir.parent, ignore_errors=True)

    def save(self, **answer):
        z.save_cache(self.dir, ISSUER, dict({"refresh_token": REFRESH, "refresh_expires_in": 1800}, **answer), now=1000)

    def test_written_0600_in_a_0700_directory_and_read_back(self):
        self.save()
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.dir / "token.json").stat().st_mode), 0o600)
        self.assertEqual(z.load_cache(self.dir, ISSUER, now=1000), REFRESH)
        record = json.loads((self.dir / "token.json").read_text())
        self.assertEqual(set(record), {"issuer", "client_id", "refresh_token", "refresh_expires_at", "saved_at"})
        self.assertNotIn(ACCESS, json.dumps(record))                       # the access token is never stored
        self.assertEqual([p.name for p in self.dir.iterdir()], ["token.json"])  # no temporary file left

    def test_a_cache_others_may_read_is_refused(self):
        self.save()
        os.chmod(self.dir / "token.json", 0o644)
        with self.assertRaises(z.TokenError) as ctx:
            z.load_cache(self.dir, ISSUER, now=1000)
        self.assertIn("readable by other users (mode 644)", str(ctx.exception))
        self.assertNotIn(REFRESH, str(ctx.exception))

    def test_another_issuer_or_client_or_an_expired_token_is_no_cache(self):
        self.save()
        self.assertIsNone(z.load_cache(self.dir, "https://keycloak.other.test/realms/zuno", now=1000))
        self.assertIsNone(z.load_cache(self.dir, ISSUER, client_id="blender", now=1000))
        self.assertEqual(z.load_cache(self.dir, ISSUER, now=1000 + 1800 - z.EARLY - 1), REFRESH)
        self.assertIsNone(z.load_cache(self.dir, ISSUER, now=1000 + 1800 - z.EARLY))
        self.save(refresh_expires_in=0)                                     # an offline token: no end of its own
        self.assertEqual(z.load_cache(self.dir, ISSUER, now=10 ** 9), REFRESH)
        self.assertIsNone(z.load_cache(self.dir / "absent", ISSUER))

    def test_no_refresh_token_in_the_answer_is_an_error(self):
        with self.assertRaises(z.TokenError):
            z.save_cache(self.dir, ISSUER, {"access_token": ACCESS})

    def test_token_refreshes_prints_nothing_else_and_caches_the_rotated_refresh_token(self):
        self.save()
        keycloak = FakeKeycloak((200, {"access_token": ACCESS, "refresh_token": ROTATED, "refresh_expires_in": 1800}))
        self.assertEqual(z.token(self.env, post=keycloak, now=1000), ACCESS)
        self.assertEqual(keycloak.calls, [("token", {"grant_type": "refresh_token", "client_id": "claude-code",
                                                     "refresh_token": REFRESH})])
        self.assertEqual(z.load_cache(self.dir, ISSUER, now=1000), ROTATED)

    def test_without_a_sign_in_the_helper_never_starts_one(self):
        keycloak = FakeKeycloak()
        with self.assertRaises(z.TokenError) as ctx:
            z.token(self.env, post=keycloak)
        self.assertIn("run `zuno_claude_token.py login`", str(ctx.exception))
        self.assertEqual(keycloak.calls, [])

    def test_a_refused_refresh_token_clears_the_cache(self):
        self.save()
        with self.assertRaises(z.TokenError) as ctx:
            z.token(self.env, post=FakeKeycloak((400, {"error": "invalid_grant", "error_description": REFRESH})), now=1000)
        self.assertIn("login", str(ctx.exception))
        self.assertNotIn(REFRESH, str(ctx.exception))
        self.assertFalse((self.dir / "token.json").exists())

    def test_another_keycloak_error_keeps_the_cache_and_names_only_the_error(self):
        self.save()
        with self.assertRaises(z.TokenError) as ctx:
            z.token(self.env, post=FakeKeycloak((503, {})), now=1000)
        self.assertEqual(str(ctx.exception), "Keycloak refused the refresh: HTTP 503 http_503")
        self.assertTrue((self.dir / "token.json").exists())

    def test_main_prints_the_token_on_stdout_and_errors_without_secrets_on_stderr(self):
        self.save(refresh_expires_in=0)                                     # main() reads the real clock
        out, err = io.StringIO(), io.StringIO()
        keycloak = FakeKeycloak((200, {"access_token": ACCESS, "refresh_token": ROTATED, "refresh_expires_in": 1800}),
                                (400, {"error": "invalid_grant"}))
        real = z.http_post
        z.http_post = lambda ca_file=None: keycloak
        try:
            with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                self.assertEqual(z.main([]), 0)
                self.assertEqual(z.main(["token"]), 1)
                self.assertEqual(z.main(["nonsense"]), 2)
        finally:
            z.http_post = real
        self.assertEqual(out.getvalue(), ACCESS + "\n")
        for secret in (ACCESS, REFRESH, ROTATED):
            self.assertNotIn(secret, err.getvalue())


class DeviceLogin(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="zuno-claude-code-"))
        self.env = {"ZUNO_ISSUER": ISSUER, "ZUNO_CLAUDE_CODE_CACHE": str(self.dir)}
        self.slept = []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def device(self):
        return (200, {"device_code": "dev-code-secret", "user_code": "ABCD-EFGH", "interval": 5, "expires_in": 600,
                      "verification_uri": f"{ISSUER}/device",
                      "verification_uri_complete": f"{ISSUER}/device?user_code=ABCD-EFGH"})

    def test_polls_until_signed_in_then_caches_and_shows_no_token(self):
        keycloak = FakeKeycloak(self.device(), (400, {"error": "authorization_pending"}), (400, {"error": "slow_down"}),
                                (200, {"access_token": ACCESS, "refresh_token": REFRESH, "refresh_expires_in": 1800}))
        out = io.StringIO()
        z.login(self.env, post=keycloak, out=out, sleep=self.slept.append, clock=lambda: 0.0)
        self.assertEqual(self.slept, [5.0, 5.0, 10.0])                      # slow_down adds 5 s
        self.assertEqual(keycloak.calls[0], ("device", {"client_id": "claude-code", "scope": "openid"}))
        self.assertEqual(keycloak.calls[1][1]["grant_type"], "urn:ietf:params:oauth:grant-type:device_code")
        self.assertIn("ABCD-EFGH", out.getvalue())                          # the person types the user code
        for secret in (ACCESS, REFRESH, "dev-code-secret"):
            self.assertNotIn(secret, out.getvalue())
        self.assertEqual(z.load_cache(self.dir, ISSUER), REFRESH)

    def test_a_denied_or_expired_sign_in_is_an_error(self):
        for error in ("access_denied", "expired_token"):
            keycloak = FakeKeycloak(self.device(), (400, {"error": error}))
            with self.assertRaises(z.TokenError) as ctx:
                z.login(self.env, post=keycloak, out=io.StringIO(), sleep=self.slept.append, clock=lambda: 0.0)
            self.assertIn(error, str(ctx.exception))
        ticks = iter([0.0, 700.0])
        keycloak = FakeKeycloak(self.device())
        with self.assertRaises(z.TokenError) as ctx:
            z.login(self.env, post=keycloak, out=io.StringIO(), sleep=self.slept.append, clock=lambda: next(ticks))
        self.assertIn("not completed in time", str(ctx.exception))
        self.assertFalse((self.dir / "token.json").exists())

    def test_logout_ends_the_session_and_deletes_the_cache(self):
        z.save_cache(self.dir, ISSUER, {"refresh_token": REFRESH, "refresh_expires_in": 0})
        keycloak = FakeKeycloak((204, {}))
        self.assertEqual(z.logout(self.env, post=keycloak), "Keycloak answered HTTP 204")
        self.assertEqual(keycloak.calls, [("logout", {"client_id": "claude-code", "refresh_token": REFRESH})])
        self.assertFalse((self.dir / "token.json").exists())
        self.assertEqual(z.logout(self.env, post=FakeKeycloak()), "no cached sign-in")


class Settings(unittest.TestCase):
    def test_the_issuer_comes_from_the_domain_or_is_given(self):
        self.assertEqual(z.issuer_url({"ZUNO_CLUSTER_DOMAIN": "apps.demo333.startx.fr"}),
                         "https://keycloak.apps.demo333.startx.fr/realms/zuno")
        self.assertEqual(z.issuer_url({"ZUNO_ISSUER": ISSUER + "/"}), ISSUER)
        with self.assertRaises(z.TokenError):
            z.issuer_url({})

    def test_the_settings_example_runs_this_helper_on_local_models(self):
        example = json.loads((pathlib.Path(z.__file__).parent / "settings.example.json").read_text())
        self.assertIn("zuno_claude_token.py", example["apiKeyHelper"])
        env = example["env"]
        self.assertTrue(env["ANTHROPIC_BASE_URL"].startswith("https://praxis."))
        self.assertEqual(env["ANTHROPIC_MODEL"], "qwen3.6-27b-instruct")
        # Every alias resolves to a local model, so /model cannot pick a SaaS one by its alias.
        for key in ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            self.assertEqual(env[key], "qwen3.6-27b-instruct")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "qwen3.5-9b")
        self.assertEqual(env["ANTHROPIC_SMALL_FAST_MODEL"], "qwen3.5-9b")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
        self.assertTrue(example["skipWebFetchPreflight"])
        self.assertLess(int(env["CLAUDE_CODE_API_KEY_HELPER_TTL_MS"]), 900 * 1000)   # under the 900 s access token
        # No system message after the first turn: the Qwen chat templates refuse it (400, live 2026-11-18).
        self.assertEqual(env["CLAUDE_CODE_MODEL_CAPABILITIES"], "-mid_conv_system")


if __name__ == "__main__":
    unittest.main()
