# supply_chain

Day 2 `check`-only component (ADR-0420/WP-070, `make day2|d2 check supply-chain`).
Verifies every first-party image's signature against the committed Vault
Transit public key (`agents/zuno-platform-signer.pub`)
- see `ansible/tasks/verify_image_signatures.yml` for the mechanism (an
in-cluster Job, since `cosign verify`'s registry pull needs network access
to the internal registry that the ansible controller itself doesn't have).

No `install`/`build`/`precheck` - this component has no chart, no
Deployment, nothing to install. `ansible/playbooks/day2_check.yml`'s
`tasks_from` conditional routes it (alongside `agents`) to `check`
directly, the same asymmetric-verb carve-out `mlops` already has in that
same playbook for a different reason (no `precheck.yml` yet there).
