# supply_chain

Day 2 `check`-only component (ADR-0420/WP-070, `make day2|d2 check supply-chain`).
Verifies every first-party image's signature keyless via RHTAS
(ADR-0535/WP-111 - superseded the Vault Transit `--key hashivault://`
mode this role originally used)
- see `ansible/tasks/verify_image_signatures.yml` for the mechanism (an
in-cluster Job, since `cosign verify`'s registry pull needs network access
to the internal registry that the ansible controller itself doesn't have).

Also validates `platform/supply-chain/pinned-releases.yaml`'s structural
integrity (`platform/supply-chain/check_release_ledger.py`, ADR-0111/
ADR-0549/WP-134) - the in-cluster, no-GitHub-Actions gate that closed
ADR-0111's last remaining SecNumCloud gap. No cluster access needed for
this part; runs straight from the controller.

No `install`/`build`/`precheck` - this component has no chart, no
Deployment, nothing to install. `ansible/playbooks/day2_check.yml`'s
`tasks_from` conditional routes it (alongside `agents`) to `check`
directly, the same asymmetric-verb carve-out `mlops` already has in that
same playbook for a different reason (no `precheck.yml` yet there).
