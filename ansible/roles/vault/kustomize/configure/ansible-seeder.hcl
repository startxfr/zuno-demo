# ADR-0602 clause 1 / WP-223: policy of the ansible-seeder Kubernetes auth
# role (ServiceAccount ansible-seeder in zuno-vault). Every Ansible task that
# seeds or reads a platform secret logs in with it through
# ansible/tasks/vault_login.yml - the root token they all used before is
# revoked after bootstrap.
#
# create/read/update only: seed tasks write-if-missing (`vault kv put`) and
# read back (`vault kv get`); nothing in ansible/ deletes a secret, so the
# identity cannot either. pki/cert/ca is the public root certificate the
# vault role publishes to the vault-pki-root-ca ConfigMap.
path "zuno/data/*" {
  capabilities = ["create", "read", "update"]
}
path "zuno/metadata/*" {
  capabilities = ["create", "read", "update", "list"]
}
path "pki/cert/ca" {
  capabilities = ["read"]
}
