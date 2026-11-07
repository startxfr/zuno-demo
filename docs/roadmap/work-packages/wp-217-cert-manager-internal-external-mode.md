# WP-217: cert-manager internal/external mode

- **State:** Done (2026-11-07) - external mode built and rehearsed live on demo333, both ways (see "Delivered (2026-11-07)")
- **ADRs:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- **Depends on:** WP-143
- **Related:** [WP-143](wp-143-mariadb-internal-external-pilot.md) (the pilot, whose pattern this follows), [ADR-0557](../../adr/0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md)
- **Target:** v0.16
- **Estimated files touched:** ~10: the component's `ansible/roles/<role>/tasks/{install,precheck,uninstall}.yml`, `ansible/confidential.example.yml`, a new endpoint-resolution task, the consumer charts, the d1 check

> Why: ADR-0352 clause 9 lands the internal/external mode contract one component per work package. MariaDB is done (WP-143). This one is next in the ADR's order: keycloak, vault, postgresql, redis, aap, external_secrets, cert_manager, argocd. cert-manager: the other Tier-A operator component: mostly documentation and check surgery. The ACME issuer settings and the Vault root CA are the seams to document.
>
> This is a short brief: expand it from WP-143 and the ADR's clauses 5 to 11 before starting.

## Goal

`zuno_cert_manager_mode: internal | external` works end to end, internal mode is unchanged, and external mode is proven live with a simulated external instance and a full there-and-back.

## Steps

1. **Mode key and payload.** Add `zuno_cert_manager_mode: internal | external` (absent means internal, today's behaviour bit for bit) and the `zuno_cert_manager_external_*` payload, with the vocabulary of ADR-0352 reused verbatim.
2. **Symmetric verb gating.** In external mode `install`, `uninstall` and `reconcile` do not deploy or remove the built-in instance; the role validates the payload and asserts the external endpoint (clause 7).
3. **Seams, not mode reads.** Every consumer reaches the component through Vault and ExternalSecrets for secrets and Helm values for non-secrets (clause 11); no component reads this one's mode key. Replace the endpoint literals in the consumer charts.
4. **Rehearse the there-and-back** on a cluster (see WP-143), then run `make d1 check` green at the internal end state.
5. **Gate and check.** The component stays in the Day-0 vital gate (clause 10) and its functional assertion passes in both modes.

## Acceptance

- Internal mode renders and behaves exactly as before (no diff on a nominal cluster).
- External mode runs the consumers unchanged against the external endpoint, with the data intact both ways, and `make d1 check` is green in both modes.

## Delivered (2026-11-07)

Tier A-operator contract of ADR-0352 (clauses 2, 4, 7): the mode key is the whole schema, no `_external_*` payload.

- `ansible/roles/cert_manager/tasks/mode.yml` resolves `zuno_cert_manager_mode` from `confidential.yml` (absent = internal) and is included by
  install, precheck and uninstall (symmetric gating, clause 4).
- External mode: `zuno-cert-manager-d0` (the OLM Subscription, CertManager CR) is not applied; the shared
  `ansible/tasks/assert_unmanaged_operator.yml` asserts the CRDs, a `Succeeded` CSV and the Ready controller instead,
  failing fast in install and record-only in precheck. `-d1` stays ours in both modes. Uninstall removes `-d1` only.
- `ansible/confidential.example.yml` carries the key; the role README has an "External mode" section with the
  unmanaged-install document and the flip procedure (a migration event: hand the Subscription over by deleting `-d0`
  without cascade).

Live rehearsal on demo333, with the user's go: `day0_install` external then internal, `day0_check` after each.
`changed=0` on every pass, the `-d0` apply skipped in external mode and re-applied in internal mode, `cert-manager is
installed` in all four states, `zuno-cert-manager-d0`/`-d1` Synced/Healthy at the end. After every pass: `vault-issuer-istio` and
`vault-issuer` Ready, istio-csr 2/2, ExternalSecrets 99/100 (the known `zuno-rhtas/rhtas-trillian-db`), 19/19 `vault`
SecretStores Ready, 11/11 Certificates Ready. A negative run of the assertion (missing CRD, CSV and
controller) reported all three and failed install with the expected message.

Not done, on purpose: no live uninstall (the external path removes `-d1` only; proven by reading, not run on the
cluster, where a mistake would remove a cluster-wide operator), and no orphaning of `-d0` (the real migration). The
clause-10 Day-1 vital gate is not built for any component yet; this role's functional assertion passes in both modes.
