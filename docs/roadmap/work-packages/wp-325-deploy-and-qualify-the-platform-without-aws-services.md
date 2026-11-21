# WP-325: Deploy and qualify the platform without AWS services

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** WP-320
- **Related:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md), [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md), [ADR-0211](../../adr/0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md), [ADR-0024](../../adr/0024-use-vault-for-application-secrets.md), [ADR-0112](../../adr/0112-implement-production-grade-backup-and-recovery.md)
- **Target:** v0.19
- **Estimated files touched:** ~15: an inventory for the environment, storage and seal configuration, an evidence file, this brief

## Goal

One independently controlled environment (OpenShift bare metal or equivalent) with local object storage and key management.

Horizon in the ADR's indicative roadmap: Day 60-90. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Replace the S3 buckets with a local S3-compatible service (finding F1).
2. Replace the AWS KMS seal of Vault and the Route 53 challenge (finding F2).
3. Run backup and restore on infrastructure the organization controls, with an independent failure domain.

## Existing work it builds on

- The day-0 modes of [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), and [WP-212](wp-212-vault-internal-external-mode.md) (Vault in external mode, which already asks who unseals).
- The bucket convention of [ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md), the Quay storage of [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md), the certificate issuer of [ADR-0211](../../adr/0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md), Vault ([ADR-0024](../../adr/0024-use-vault-for-application-secrets.md)) and the backup drills of [ADR-0112](../../adr/0112-implement-production-grade-backup-and-recovery.md).

## Acceptance

- The platform installs and runs with no AWS endpoint in its dependency inventory.
- A restore drill passes on the local storage.
