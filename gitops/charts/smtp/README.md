# smtp

Referenced by `gitops/apps/smtp/application-d0.yaml` (namespace.enabled:
`zuno-ai-run` Namespace) and `application-d1.yaml` (credentials.enabled:
the `smtp-technical-credentials` ExternalSecret) - see
`gitops/apps/README.md`.

No SMTP server is installed here (ADR-0056) - only the technical mail
identity's credential, seeded as an empty placeholder at
`zuno/smtp/technical` by `ansible/roles/vault/tasks/install.yml`.
An operator must populate it before whichever service sends mail can
actually do so - see `ansible/roles/smtp/README.md`.
