"""demo_token.sh: the Vault token goes to the clipboard or a pipe, never on screen (ADR-0628, WP-331).

Fake `oc`, `wl-copy` and `xclip` on PATH stand in for the cluster and the
desktop: no cluster and no display are needed.

Run from the repository root:
    python3 platform/vault/tests/test_demo_token.py
"""
from __future__ import annotations

import json
import os
import pathlib
import pty
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "demo_token.sh"
TOKEN = "hvs.FAKE-demo-reader-token"
JWT = "eyJFAKE.jwt.sig"

FAKE_OC = f"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_DIR/oc.log"
case "$1 $2" in
  "get pods") echo zuno-vault-0 ;;
  "create token") echo {JWT} ;;
  "exec -i")
    jwt="$(cat)"
    [[ $jwt == {JWT} ]] || {{ echo "jwt not on stdin" >&2; exit 9; }}
    for a in "$@"; do [[ $a == *{JWT}* ]] && {{ echo "jwt on the command line" >&2; exit 9; }}; done
    echo '{json.dumps({"auth": {"client_token": TOKEN, "token_policies": ["default", "demo-reader"],
                                 "metadata": {"role": "demo-reader"}, "lease_duration": 1800}})}' ;;
  *) echo "unexpected oc $*" >&2; exit 9 ;;
esac
"""
FAKE_COPY = '#!/usr/bin/env bash\ncat > "$FAKE_DIR/clipboard"\n'


class DemoToken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.write("oc", FAKE_OC)
        for tool in ("python3", "sed", "cat", "bash", "env"):
            path = subprocess.run(["bash", "-c", f"command -v {tool}"], capture_output=True, text=True).stdout.strip()
            (self.bin / tool).symlink_to(path)
        self.env = {"PATH": str(self.bin), "FAKE_DIR": str(self.dir), "HOME": str(self.dir)}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, *args, env=None, **kw):
        return subprocess.run([str(SCRIPT), *args], env={**self.env, **(env or {})}, capture_output=True,
                              text=True, **kw)

    def test_clipboard_gets_the_token_and_the_screen_does_not(self):
        self.write("wl-copy", FAKE_COPY)
        r = self.run_script(env={"WAYLAND_DISPLAY": "wayland-0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.dir / "clipboard").read_text(), TOKEN)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)
        self.assertNotIn(JWT, r.stdout + r.stderr)
        self.assertIn("role demo-reader, policies demo-reader, valid 30 min", r.stdout)

    def test_xclip_when_there_is_no_wayland(self):
        self.write("xclip", FAKE_COPY)
        r = self.run_script(env={"DISPLAY": ":0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.dir / "clipboard").read_text(), TOKEN)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_no_clipboard_tool_mints_nothing(self):
        r = self.run_script(env={"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("no clipboard tool", r.stderr)
        self.assertFalse((self.dir / "oc.log").exists())

    def test_print_into_a_pipe(self):
        r = self.run_script("--print")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, TOKEN + "\n")
        self.assertNotIn(TOKEN, r.stderr)

    def test_print_on_a_terminal_is_refused_before_anything_runs(self):
        leader, follower = pty.openpty()
        try:
            r = subprocess.run([str(SCRIPT), "--print"], env=self.env, stdout=follower, stderr=subprocess.PIPE,
                               text=True)
        finally:
            os.close(follower)
            os.close(leader)
        self.assertEqual(r.returncode, 2)
        self.assertIn("stdout is a terminal", r.stderr)
        self.assertFalse((self.dir / "oc.log").exists())


if __name__ == "__main__":
    unittest.main()
