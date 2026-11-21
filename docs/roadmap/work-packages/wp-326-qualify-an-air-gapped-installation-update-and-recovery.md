# WP-326: Qualify an air-gapped installation, update and recovery

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** WP-323, WP-325
- **Related:** [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md), [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)
- **Target:** v0.19
- **Estimated files touched:** ~12: the artifact inventory, an import procedure, an evidence file, this brief

## Goal

A complete offline artifact inventory, and a demonstration of disconnected installation, update, operation and recovery.

Horizon in the ADR's indicative roadmap: Day 90-180. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Build the offline artifact inventory: images, operators, charts, model weights.
2. Write the offline acquisition, verification and promotion procedure.
3. Demonstrate installation, normal operation, a controlled update and disaster recovery without Internet access.

## Existing work it builds on

- The internal Quay of [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) (finding F4), the catalog tolerance of [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md) and the offline verification of [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md).

## Acceptance

- The four demonstrations pass with no Internet access.
- The profile is tested against its declared dependency inventory, including failure and recovery cases.
