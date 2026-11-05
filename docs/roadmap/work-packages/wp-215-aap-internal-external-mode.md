# WP-215: Ansible Automation Platform (with aap_config) internal/external mode

- **State:** Not started
- **ADRs:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- **Depends on:** WP-143, WP-213
- **Related:** [WP-143](wp-143-mariadb-internal-external-pilot.md) (the pilot, whose pattern this follows), [ADR-0557](../../adr/0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md)
- **Target:** v0.16
- **Estimated files touched:** ~10: the component's `ansible/roles/<role>/tasks/{install,precheck,uninstall}.yml`, `ansible/confidential.example.yml`, a new endpoint-resolution task, the consumer charts, the d1 check

> Why: ADR-0352 clause 9 lands the internal/external mode contract one component per work package. MariaDB is done (WP-143). This one is next in the ADR's order: keycloak, vault, postgresql, redis, aap, external_secrets, cert_manager, argocd. Ansible Automation Platform (with aap_config): AAP and its configuration role. The external mode must keep the Fernet encryption key persistent (an AAP reinstall with a new key loses its secrets).
>
> This is a short brief: expand it from WP-143 and the ADR's clauses 5 to 11 before starting.

## Goal

`zuno_aap_mode: internal | external` works end to end, internal mode is unchanged, and external mode is proven live with a simulated external instance and a full there-and-back.

## Steps

1. **Mode key and payload.** Add `zuno_aap_mode: internal | external` (absent means internal, today's behaviour bit for bit) and the `zuno_aap_external_*` payload, with the vocabulary of ADR-0352 reused verbatim.
2. **Symmetric verb gating.** In external mode `install`, `uninstall` and `reconcile` do not deploy or remove the built-in instance; the role validates the payload and asserts the external endpoint (clause 7).
3. **Seams, not mode reads.** Every consumer reaches the component through Vault and ExternalSecrets for secrets and Helm values for non-secrets (clause 11); no component reads this one's mode key. Replace the endpoint literals in the consumer charts.
4. **Rehearse the there-and-back** on a cluster (see WP-143), then run `make d1 check` green at the internal end state.
5. **Gate and check.** The component stays in the Day-0 vital gate (clause 10) and its functional assertion passes in both modes.

## Acceptance

- Internal mode renders and behaves exactly as before (no diff on a nominal cluster).
- External mode runs the consumers unchanged against the external endpoint, with the data intact both ways, and `make d1 check` is green in both modes.
