"""ansible/confidential.yml may be ansible-vault encrypted (ADR-0603 M22).

The Makefile reads zuno_make_aap_mode from it before any playbook runs. These tests extract the real shell
functions from the Makefile and run them on a plain file, an encrypted file, an encrypted file without its
passphrase and an invalid value: a failed read must stop the routing, never guess local or remote.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PASSPHRASE = "unit-test-passphrase"

pytestmark = pytest.mark.skipif(
    shutil.which("ansible-vault") is None or shutil.which("bash") is None,
    reason="ansible-vault and bash are required",
)


def _functions() -> str:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    body = text.split("define AAP_ROUTING_SHELL_FUNCS\n", 1)[1].split("\nendef", 1)[0]
    body = body.replace("$$", "$")
    body = body.replace("$(ANSIBLE_PLAYBOOK)", "true").replace("$(INVENTORY)", "x").replace("$(EXTRA_VARS)", "")
    return re.sub(r" \\\n", "\n", body)


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    (tmp_path / "ansible").mkdir()
    shutil.copy(REPO / "ansible" / "vault-pass.sh", tmp_path / "ansible" / "vault-pass.sh")
    (tmp_path / "ansible.cfg").write_text("[defaults]\nvault_password_file = ansible/vault-pass.sh\n")
    (tmp_path / "funcs.sh").write_text(_functions())
    (tmp_path / "pass").write_text(PASSPHRASE + "\n")
    return tmp_path


def _write(workdir: Path, content: str, encrypt: bool) -> None:
    target = workdir / "ansible" / "confidential.yml"
    target.write_text(content)
    if encrypt:
        subprocess.run(
            ["ansible-vault", "encrypt", str(target)],
            check=True, capture_output=True, cwd=workdir,
            env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "ZUNO_VAULT_PASS_FILE": str(workdir / "pass")},
        )


def _route(workdir: Path, passphrase_file: Path) -> tuple[str, int]:
    out = subprocess.run(
        ["bash", "-c", 'source funcs.sh; aap_route job t "{}"; echo "rc=$?"'],
        cwd=workdir, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "ZUNO_VAULT_PASS_FILE": str(passphrase_file)},
    )
    return out.stderr, int(re.search(r"rc=(\d+)", out.stdout).group(1))


def test_plain_file_local_mode_is_not_routed(workdir: Path) -> None:
    _write(workdir, "zuno_make_aap_mode: local\n", encrypt=False)
    assert _route(workdir, workdir / "pass")[1] == 99


def test_encrypted_file_is_read_through_ansible_vault(workdir: Path) -> None:
    _write(workdir, "zuno_make_aap_mode: local\nsecret: x\n", encrypt=True)
    assert (workdir / "ansible" / "confidential.yml").read_text().startswith("$ANSIBLE_VAULT;")
    assert _route(workdir, workdir / "pass")[1] == 99


def test_encrypted_remote_mode_launches(workdir: Path) -> None:
    _write(workdir, "zuno_make_aap_mode: remote\n", encrypt=True)
    assert _route(workdir, workdir / "pass")[1] == 0


def test_encrypted_file_without_passphrase_stops(workdir: Path) -> None:
    _write(workdir, "zuno_make_aap_mode: local\n", encrypt=True)
    stderr, rc = _route(workdir, workdir / "missing")
    assert rc == 2
    assert "Cannot decrypt" in stderr


def test_invalid_mode_stops_instead_of_defaulting_to_remote(workdir: Path) -> None:
    _write(workdir, "zuno_make_aap_mode: bogus\n", encrypt=False)
    assert _route(workdir, workdir / "pass")[1] == 2


def test_vault_pass_script_never_fails_without_a_passphrase_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(REPO / "ansible" / "vault-pass.sh")], capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
    )
    assert result.returncode == 0 and result.stdout.strip()
