# ADR-0628 / WP-331: policy of the demo-reader Kubernetes auth role
# (ServiceAccount vault-demo-reader in zuno-vault). The presenter mints a
# 30-minute token with platform/vault/demo_token.sh and signs in to the Vault
# web UI with it, on stage and in the vault-pki GIF.
#
# read and list only, on what the UI tour shows: secret NAMES, versions and
# metadata (never zuno/data/*, so no value can reach the screen), the engines
# and auth methods, the ACL policies, the Transit key list and public keys
# (never sign, encrypt, decrypt or export), the PKI root certificate and roles,
# and the Kubernetes auth roles. No sudo: sys/audit and the Raft configuration
# need it, so the page shows them from the terminal instead.
# platform/vault/tests/test_demo_reader_policy.py fails the build if a write
# capability, sudo or a zuno/data path appears here.
path "zuno/metadata" {
  capabilities = ["list"]
}
path "zuno/metadata/*" {
  capabilities = ["read", "list"]
}
path "sys/mounts" {
  capabilities = ["read"]
}
path "sys/auth" {
  capabilities = ["read"]
}
path "sys/policies/acl" {
  capabilities = ["list"]
}
path "sys/policies/acl/*" {
  capabilities = ["read"]
}
path "sys/internal/ui/mounts" {
  capabilities = ["read"]
}
path "sys/internal/ui/mounts/*" {
  capabilities = ["read"]
}
path "transit/keys" {
  capabilities = ["list"]
}
path "transit/keys/*" {
  capabilities = ["read"]
}
path "pki/cert/ca" {
  capabilities = ["read"]
}
path "pki/roles" {
  capabilities = ["list"]
}
path "pki/roles/*" {
  capabilities = ["read"]
}
path "auth/kubernetes/role" {
  capabilities = ["list"]
}
path "auth/kubernetes/role/*" {
  capabilities = ["read"]
}
