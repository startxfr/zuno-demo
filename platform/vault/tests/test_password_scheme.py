"""ADR-0595 acceptance tests for the demo password scheme.

Renders ansible/inventories/demo/group_vars/all/passwords.yml with ansible itself
and checks what must hold for the scheme to be safe in a public repository:

  * no weak literal is committed: with no shared variable every password is a
    generated 22-character hex value;
  * the generated value is stable across runs and differs between seeds;
  * the shared variable reaches every component, and an empty one falls back;
  * a per-component override wins without moving any other component.

ADR-0602 clause 3 / WP-223 adds the `hardened` profile (zuno_security_profile):

  * the demo profile (the default) keeps everything above unchanged;
  * hardened leaves every infra variable UNDEFINED - no shared value, no md5 -
    so the consumers' random defaults apply, even when zuno_admin_mainpwd is set;
  * hardened fails, with a hint, wherever the md5 fallback would be needed;
  * hardened keeps the personas on their one shared value;
  * an explicit per-component value still wins in hardened.

Standalone script, same convention as platform/keycloak/tests - not pytest.
Run from the repository root:

    python3 platform/vault/tests/test_password_scheme.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY = REPO_ROOT / "ansible/inventories/demo/hosts.yml"
PASSWORDS = REPO_ROOT / "ansible/inventories/demo/group_vars/all/passwords.yml"

ADMIN_VARS = [
    "zuno_admin_password",
    "zuno_admin_keycloak_root_password",
    "zuno_admin_keycloak_console_password",
    "zuno_admin_keycloak_automation_password",
    "zuno_admin_aap_root_password",
    "zuno_admin_postgresql_root_password",
    "zuno_admin_keycloak_postgresql_root_password",
    "zuno_admin_maas_postgresql_root_password",
    "zuno_admin_mlflow_postgresql_root_password",
    "zuno_admin_dify_postgresql_root_password",
    "zuno_admin_kagent_postgresql_root_password",
    "zuno_admin_ogx_postgresql_root_password",
    "zuno_admin_aap_postgresql_root_password",
    "zuno_admin_aap_controller_postgresql_root_password",
    "zuno_admin_aap_hub_postgresql_root_password",
    "zuno_admin_aap_eda_postgresql_root_password",
    "zuno_admin_aap_metrics_postgresql_root_password",
    "zuno_admin_aap_metrics_readonly_postgresql_password",
    "zuno_admin_mariadb_root_password",
    "zuno_admin_mlops_pipeline_db_password",
    "zuno_admin_rhtas_trillian_db_password",
    "zuno_admin_redis_session_store_password",
]
PERSONA_VARS = [
    "zuno_personas_password",
    "zuno_personas_humans_password",
    "zuno_personas_openclaw_ui_password",
    "zuno_admin_demo_personas_root_password",
]
ALL_VARS = ADMIN_VARS + PERSONA_VARS
# WP-223: undefined in the hardened profile. zuno_admin_password itself is not an
# infra credential (nothing consumes it in hardened) but loses its md5 fallback;
# the Dify admin and the OpenClaw Control UI password go random there too.
INFRA_VARS = [v for v in ADMIN_VARS if v != "zuno_admin_password"] + [
    "zuno_admin_dify_admin_password",
    "zuno_personas_openclaw_ui_password",
]
SHARED_PERSONA_VARS = [
    "zuno_personas_password",
    "zuno_personas_humans_password",
    "zuno_admin_demo_personas_root_password",
]
UNDEFINED = "__UNDEFINED__"
HARDENED = {"zuno_security_profile": "hardened"}

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS" if ok else "FAIL"), name, ("- " + detail) if detail and not ok else "")
    if not ok:
        _failures.append(name)


def _run(names: list[str], extra: dict[str, str], undefined_ok: bool):
    """Render `names` with ansible-playbook. With undefined_ok, an undefined
    variable renders as UNDEFINED instead of failing the play (the consumers'
    `default(...)` sees exactly that)."""
    expr = (lambda v: f"{v} | default('{UNDEFINED}')") if undefined_ok else (lambda v: v)
    msg = "{{ {" + ", ".join(f"'{v}': {expr(v)}" for v in names) + "} }}"
    play = (
        "- hosts: localhost\n  gather_facts: false\n  tasks:\n"
        "    - ansible.builtin.debug:\n        msg: \"" + msg + "\"\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        pb = Path(tmp) / "render.yml"
        pb.write_text(play)
        cmd = ["ansible-playbook", "-i", str(INVENTORY), str(pb)]
        for key, value in extra.items():
            cmd += ["-e", f"{key}={value}"]
        env = {**os.environ, "ANSIBLE_STDOUT_CALLBACK": "json", "ANSIBLE_LOAD_CALLBACK_PLUGINS": "1"}
        return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=env)


def render(extra: dict[str, str], names: list[str] | None = None, undefined_ok: bool = False) -> dict[str, str]:
    """Render every scheme variable with ansible, `extra` as extra variables."""
    out = _run(names or ALL_VARS, extra, undefined_ok)
    if out.returncode != 0:
        raise SystemExit(f"ansible-playbook failed:\n{out.stdout}\n{out.stderr}")
    result = json.loads(out.stdout)
    return result["plays"][0]["tasks"][0]["hosts"]["localhost"]["msg"]


def render_fails(extra: dict[str, str], name: str, needle: str) -> bool:
    """True when rendering `name` fails and the output carries `needle`."""
    out = _run([name], extra, undefined_ok=False)
    return out.returncode != 0 and needle in (out.stdout + out.stderr)


def main() -> int:
    body = PASSWORDS.read_text()
    check("no_literal_default_in_passwords_yml", "default('" not in body.replace("default('')", ""))

    bare = render({})
    again = render({})
    check("generated_values_are_22_hex", all(re.fullmatch(r"[0-9a-f]{22}", bare[v]) for v in ALL_VARS),
          str({v: bare[v] for v in ALL_VARS if not re.fullmatch(r"[0-9a-f]{22}", bare[v])}))
    check("generated_values_are_stable", bare == again)
    check("admin_and_persona_series_differ", bare["zuno_admin_password"] != bare["zuno_personas_password"])

    shifted = render({"zuno_password_seed_extra": "other"})
    check("seed_extra_moves_the_series", shifted["zuno_admin_password"] != bare["zuno_admin_password"])

    shared = render({"zuno_admin_mainpwd": "demo-pw", "zuno_personas_mainpwd": "persona-pw"})
    check("shared_admin_reaches_every_component", all(shared[v] == "demo-pw" for v in ADMIN_VARS),
          str({v: shared[v] for v in ADMIN_VARS if shared[v] != "demo-pw"}))
    check("shared_persona_reaches_every_family", all(shared[v] == "persona-pw" for v in PERSONA_VARS),
          str({v: shared[v] for v in PERSONA_VARS if shared[v] != "persona-pw"}))

    empty = render({"zuno_admin_mainpwd": ""})
    check("empty_shared_falls_back_to_generated", empty["zuno_admin_password"] == bare["zuno_admin_password"])

    one = render({"zuno_admin_mainpwd": "demo-pw", "zuno_admin_aap_root_password": "aap-only"})
    others_ok = all(one[v] == "demo-pw" for v in ADMIN_VARS if v != "zuno_admin_aap_root_password")
    check("override_wins_for_one_component_only", one["zuno_admin_aap_root_password"] == "aap-only" and others_ok)

    # --- demo profile, explicitly: identical to the default -------------------
    demo = render({"zuno_security_profile": "demo"})
    check("demo_profile_is_the_default", demo == bare)

    # --- hardened profile (ADR-0602 clause 3 / WP-223) ------------------------
    hard_names = sorted(set(ALL_VARS + INFRA_VARS))
    shared_pw = {"zuno_admin_mainpwd": "demo-pw", "zuno_personas_mainpwd": "persona-pw-12"}
    hard = render({**HARDENED, **shared_pw}, hard_names, undefined_ok=True)
    check("hardened_infra_vars_are_undefined", all(hard[v] == UNDEFINED for v in INFRA_VARS),
          str({v: hard[v] for v in INFRA_VARS if hard[v] != UNDEFINED}))
    check("hardened_shared_admin_never_reaches_infra", "demo-pw" not in [hard[v] for v in INFRA_VARS])
    check("hardened_personas_keep_the_shared_value",
          all(hard[v] == "persona-pw-12" for v in SHARED_PERSONA_VARS),
          str({v: hard[v] for v in SHARED_PERSONA_VARS}))

    hard_bare = render(HARDENED, hard_names, undefined_ok=True)
    md5_values = set(bare.values())
    check("hardened_yields_no_md5_value",
          not any(hard_bare[v] in md5_values or re.fullmatch(r"[0-9a-f]{22}", hard_bare[v]) for v in hard_names),
          str({v: hard_bare[v] for v in hard_names if hard_bare[v] != UNDEFINED}))
    check("hardened_persona_md5_fallback_fails",
          render_fails(HARDENED, "zuno_personas_humans_password", "md5 fallback is disabled"))
    check("hardened_admin_md5_fallback_fails",
          render_fails(HARDENED, "zuno_admin_password", "no md5 fallback"))
    check("hardened_infra_without_default_fails_with_a_hint",
          render_fails({**HARDENED, **shared_pw}, "zuno_admin_keycloak_console_password", "deliberately undefined"))

    hard_one = render({**HARDENED, **shared_pw, "zuno_admin_aap_root_password": "aap-only"}, hard_names, undefined_ok=True)
    check("hardened_explicit_override_still_wins",
          hard_one["zuno_admin_aap_root_password"] == "aap-only"
          and all(hard_one[v] == UNDEFINED for v in INFRA_VARS if v != "zuno_admin_aap_root_password"))

    if _failures:
        print(f"\n{len(_failures)} check(s) failed: {', '.join(_failures)}")
        return 1
    print("\nAll password scheme checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
