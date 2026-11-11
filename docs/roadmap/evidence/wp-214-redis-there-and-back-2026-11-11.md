# WP-214: Redis external mode, there and back on demo333 (2026-11-11)

Live rehearsal of [WP-214](../work-packages/wp-214-redis-internal-external-mode.md) with the user's go, by session
zuno-avancement. Window 19:59 to 20:30 UTC, announced to zuno-main and zuno-demo (no llm, namespaces or redis install, no
golden path from them meanwhile). `ansible/confidential.yml` was not touched: the mode and the payload were passed as
extra vars from a file outside the repository.

## Variant chosen by the user

The built-in Redis kept running during the window. The plan's first step, `make d1 uninstall redis` in internal mode, was
refused by the session's safety check, so the user chose to flip only the role and the consumer. What is proven: the
role's external mode (assertion, Vault seed, nothing deployed) and the consumer seam, there and back. What is not
proven: running with the built-in removed.

## Setup

- Canary `zuno-canary-wp-214` (ADR-0609 playbook), deleted at the end.
- A simulated external Redis in it: `quay.io/fedora/redis-7@sha256:0217e8a8…` (the digest pinned for UnifAI), with
  `--requirepass` set from a Secret, no persistence, and Service `zuno-redis-ext:6379`. A NetworkPolicy admits 6379 only
  from ai-gateway (zuno-ai-run) and the assertion Job (zuno-auth).
- Baseline: ai-gateway `QUOTA_LEDGER_STORE=redis`, `REDIS_ADDR=zuno-redis-master.zuno-auth...`; the built-in held
  40 `zuno:quota:*` keys; no ledger error in the gateway log; Vault `zuno/redis/session-store` at version 2.

## There (external)

| UTC | Step | Result |
|---|---|---|
| 20:09-20:11 | `make d1 install redis` in external mode | exit 0: "PING with AUTH ... OK, maxclients 10000 (floor 100)"; Vault path at version 3 (the external password); nothing deployed |
| 20:12 | `make d1 check redis` in external mode | `redis is installed` |
| 20:12 | ExternalSecret `ai-gateway-redis-credentials` force-synced | SecretSynced |
| 20:12-20:13 | `make d2 install namespaces`, `make d2 install llm` in external mode | the seam put the canary address in `zuno-ai-gateway-d1` and `redisExternal` in `zuno-namespaces-d1` (no EgressFirewall rule for a `.svc` name) |
| 20:15 | ai-gateway rolled | `REDIS_ADDR=zuno-redis-ext.zuno-canary-wp-214.svc.cluster.local:6379` |
| 20:16-20:17 | golden path | 13/13 PASS (world model shown as roadmap) |
| 20:17 | the canary Redis | 21 routing decisions and 12 `zuno:quota:*` keys written by the gateway; no ledger or Redis error in its log |

## Negative cases and the fixes they caused

- **A wrong password.** The first run failed as it should, but two defects showed:
  - The password was written to Vault before the endpoint was asserted. A wrong password would have reached ai-gateway
    through its ExternalSecret at the next refresh. **Fixed:** the assertion now runs first. It reads the payload
    through a short-lived Secret, not from Vault.
  - The printed log came from an earlier run's pod. A Job deleted without propagation leaves its pods behind, unowned,
    and the log lookup by `job-name` read the oldest one. **Fixed:** the Job deletes cascade (`propagationPolicy:
    Background`), and the log is read from the pod of the current run (`batch.kubernetes.io/controller-uid`).
- **Re-run after the fixes (20:19):** exit 2 with "FAIL: PING with AUTH ... WRONGPASS ... NOAUTH". The Vault seed was not
  reached, and Vault stayed at version 3.
- **Uninstall in external mode.** Not run live: the safety check refused the `make d1 uninstall redis` command. Read in
  the code: that branch only removes the assertion Job and Secret, and leaves the built-in Applications and the
  external Redis alone.

## Back (internal)

| UTC | Step | Result |
|---|---|---|
| 20:22 | `vault kv rollback -version=2 zuno/redis/session-store` | version 4 = the built-in password of 2026-11-03 |
| 20:23 | `make d1 install redis` in internal mode | exit 0 |
| 20:24 | ExternalSecrets `zuno-redis-auth` and `ai-gateway-redis-credentials` force-synced | SecretSynced; the Secret's password answers PONG on the built-in Redis |
| 20:25 | `make d2 install namespaces`, `make d2 install llm` in internal mode | both Applications lost the seam values (no canary reference left) |
| 20:26 | ai-gateway rolled | `REDIS_ADDR=zuno-redis-master.zuno-auth.svc.cluster.local:6379` |
| 20:27-20:28 | golden path | 13/13 PASS |
| 20:28 | the built-in Redis | its 40 quota keys kept, 20 new routing decisions; no error in the gateway log |
| 20:30 | canary deleted | |

## Data

No copy (the brief's option A): the external Redis started empty. The built-in kept its keys through the window, so the
way back lost nothing. The quota windows counted on the canary during the window were not carried back. That is the
expected cost of option A, and those counters expire after two windows.
