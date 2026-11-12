# WP-258: Write the UnifaiAgentBundle custom resource page in zuno-demo-agents

- **State:** Not started
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md),
  [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)
- **Depends on:** none (the operator documentation stays on disk until UnifAI moves it)
- **Related:** [WP-255](wp-255-okf-field-reference-in-the-agents-repository.md), [WP-257](wp-257-publish-verify-and-roll-back-an-okf-release-documented.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English); tracked here, landed there by pull request
- **Estimated files touched:** ~3 in zuno-demo-agents: `docs/unifaiagentbundle.md`, the README link, a rendered example

> Execute this brief as a standalone task. Documentation only. Opened 2026-11-13 (user's go).

## Why

The `UnifaiAgentBundle` custom resource is documented only in the UnifAI operator README and in `render_dev_bundles.py`. UnifAI is becoming
generic and will link here instead of keeping the text. The page must be complete on its own.

## Goal

One page explains the custom resource field by field, shows a working example and explains every condition and how to react to it.

## Content

1. **`source.oci.reference`** pinned by digest (tags refused), and `pullSecretRef`.
2. **`verify`:** `publicKeyRef`, or `keyless{issuer, subjectRegExp, trustedRootRef}`.
3. **`ceilings`, `entitlement` and `delegation{gatewayURL,...}`.**
4. **Revocation:** the ConfigMap `unifai-agent-revocations`, what it blocks and how to lift it.
5. **Conditions:** Verified, Valid, WithinCeilings, Emitted, Ready: when each turns false, and the first thing to check.
6. **The pipeline order** and the rule that a failed step emits nothing and keeps the previous good version.
7. **A full example** based on `examples/agent/agentbundle-tekos.yaml`, with no real digest or secret.

## Source

On disk: `/home/cl/ClaudeCode/startx-unifai/fork/unifai-operator/README.md`, sections "Zuno OKF agent bundles (fork-only)" (line 170),
"A2A delegation (zuno WP-173)" (line 337) and "Limits of a bundle's agents" (line 369); `examples/agent/agentbundle-tekos.yaml`; field
reference `api/v1alpha1/agentbundle_types.go`. A field is documented only if the Go types define it. The text is rewritten, not pasted, so
the page stays accurate for this repository.

## Proof

- The example applies in a dry run on a canary operator (server-side dry run, no live change).
- unifai-compare reads the page and confirms the field names against the types.

## Lots

| Lot | Content |
|---|---|
| 1 | Field inventory from the Go types, and the pipeline text |
| 2 | Conditions, revocation, example; dry run; pull request |

## Out of scope

- Changing the operator. The upcoming `contractNamespace` setting is added to the page when unifai-compare fixes the names.
