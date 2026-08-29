# smtp

A Day 1 component (ADR-0056; moved here from Day 0 by ADR-0421,
`make d1 install smtp`). Applies
`gitops/apps/smtp/application-d0.yaml`/`application-d1.yaml`
(`gitops/charts/smtp` - see `gitops/apps/README.md`), registering an
`ExternalSecret` exposing the technical mail identity
(`zuno/smtp/technical`, seeded by `ansible/roles/vault` from
`ansible/confidential.yml`'s `zuno_smtp_host`/`_username`/`_password` -
falls back to an empty placeholder if those are still the "xxxxxx"
sentinel) as `smtp-technical-credentials` in `zuno-ai-run`. Building
whichever service actually sends mail with it (e.g. Comage's weekly
report) is out of scope for this role.
