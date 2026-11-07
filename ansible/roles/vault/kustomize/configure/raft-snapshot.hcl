# ADR-0602 clause 1 / WP-223: policy of the raft-snapshot Kubernetes auth
# role (ServiceAccount vault-raft-snapshot in zuno-vault), the identity of
# gitops/charts/vault's raft snapshot CronJob. `vault operator raft snapshot
# save` is a read of this one endpoint.
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
