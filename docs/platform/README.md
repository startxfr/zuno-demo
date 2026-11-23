# Platform documentation

Last reviewed: 2026-11-19

Installation, operation and release runbooks for demo333. What the platform is and why is in [architecture](../architecture/README.md) and
the [ADRs](../adr/README.md); this directory says how to install, change and run it. Every cluster change needs the owner's go.

## Install and configure

| Page | What it covers |
|---|---|
| [prerequisites.md](prerequisites.md) | What must be true and decided before the first `make day0 install` on a new cluster. |
| [installation.md](installation.md) | The installation workflow, starting from `ansible/inventories/<cluster>/confidential.yml`. |
| [configuration.md](configuration.md) | The component names each Makefile verb accepts, validated against the Makefile. |
| [release-sequence.md](release-sequence.md) | The steps of a platform release on demo333, including an agents release. |

## Run and change

| Page | What it covers |
|---|---|
| [operations.md](operations.md) | Day-to-day operations: UnifAI image admission and release, security profiles, node pools, PostgreSQL traps. |
| [agents-release-integration.md](agents-release-integration.md) | How the signed agents release is promoted, admitted, mirrored and rolled. |
| [saas-provider-key-rotation.md](saas-provider-key-rotation.md) | Rotating a SaaS provider key; symptoms of a failing SaaS model. |
| [shared-password-rotation.md](shared-password-rotation.md) | Rotating the shared demo password. |
| [test-accounts.md](test-accounts.md) | The `test-<type>-<name>` accounts, their marker groups and quota classes. |
| [vault-kms-raft-migration.md](vault-kms-raft-migration.md) | Vault with KMS auto-unseal, Raft storage and TLS. |
| [pre-ga-upgrade.md](pre-ga-upgrade.md) | Upgrading a pre-GA dependency. |
| [canary-rehearsal.md](canary-rehearsal.md) | Rehearsing a change in a canary namespace. |
| [wp-224-unifai-firewall-rehearsal-plan.md](wp-224-unifai-firewall-rehearsal-plan.md) | The rehearsal plan of the UnifAI egress firewall (record). |

## Resilience and incidents

| Page | What it covers |
|---|---|
| [backup-recovery.md](backup-recovery.md) | Backup and recovery objectives (RPO 24 h, RTO 4 h for the demo profile) and restore drills. |
| [agent-revocation-runbook.md](agent-revocation-runbook.md) | Withdrawing an agent after an incident. |
| [troubleshooting.md](troubleshooting.md) | Diagnostic entry points and known symptoms with their fixes. |
| [slo.md](slo.md) | The availability objective and the measured failover. |

## Testing the platform

| Page | What it covers |
|---|---|
| [stresstest.md](stresstest.md) | The profile-driven stress campaign and how to read its report. |
| [../demo/golden-path.md](../demo/golden-path.md) | The automated probes before a live demonstration. |

## Working with others

[parallel-sessions.md](parallel-sessions.md): the rules for several people and coding agents acting on the repository and on demo333 at the same time.
