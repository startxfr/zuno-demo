# smtp

PREP_COMPONENT only (`make prepare smtp`) - no CONFIG_SCOPE. Registers an
`ExternalSecret` exposing the technical mail identity
(`secret/zuno/smtp/technical`, seeded as an empty placeholder by
`ansible/roles/vault`) as `smtp-technical-credentials` in `zuno-platform`.
An operator must populate the real value; building whichever service
actually sends mail with it (e.g. Comage's weekly report) is out of scope
for this role.
