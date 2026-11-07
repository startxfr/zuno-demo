# ADR-0602 clause 1 / WP-223: policy of the vault-configurator Kubernetes
# auth role (ServiceAccount vault-configure in zuno-vault), the identity of
# the configure Job (configure.sh). Written once by the root-token bootstrap
# (ansible/roles/vault/tasks/bootstrap_auth.yml), then re-applied by the Job
# itself on every run.
#
# Everything configure.sh does, and nothing it does not: no capability on
# zuno/data/* or zuno/metadata/* - the configurator never reads or writes a
# platform secret. Being able to write ACL policies and auth roles is
# root-equivalent in principle (it could grant itself more); that is
# inherent to "the Job that configures Vault" and is why the role is bound
# to one ServiceAccount in the admin-only zuno-vault namespace, with a
# 15-minute token.
path "sys/policies/acl/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "sys/auth" {
  capabilities = ["read"]
}
path "sys/auth/*" {
  capabilities = ["create", "read", "update", "delete", "sudo"]
}
path "auth/kubernetes/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "sys/mounts" {
  capabilities = ["read"]
}
path "sys/mounts/*" {
  capabilities = ["create", "read", "update"]
}
path "pki/*" {
  capabilities = ["create", "read", "update", "list"]
}
path "transit/keys/*" {
  capabilities = ["create", "read", "update", "list"]
}
path "sys/audit" {
  capabilities = ["read", "sudo"]
}
path "sys/audit/*" {
  capabilities = ["create", "read", "update", "sudo"]
}
