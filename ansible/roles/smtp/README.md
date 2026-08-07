# smtp

A Day 0 component (ADR-0056, `make d0 install smtp`). Applies
`gitops/apps/smtp/application-d0.yaml`/`application-d1.yaml`
(`gitops/charts/smtp` - see `gitops/apps/README.md`), registering an
`ExternalSecret` exposing the technical mail identity
(`secret/zuno/smtp/technical`, seeded as an empty placeholder by
`ansible/roles/vault`) as `smtp-technical-credentials` in `zuno-ai-run`.
An operator must populate the real value; building whichever service
actually sends mail with it (e.g. Comage's weekly report) is out of scope
for this role.
