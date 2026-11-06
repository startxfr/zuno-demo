#!/bin/sh
# Configures Vault: KV v2, Kubernetes auth, every policy/role the platform
# binds to, PKI, Transit and the audit device. Idempotent, safe to re-run.
#
# ADR-0602 clause 1 / WP-223: this script no longer unseals (AWS KMS
# auto-unseal does) and no longer runs with the root token. It logs in as
# its own ServiceAccount (vault-configure, zuno-vault) through the
# Kubernetes auth role vault-configurator, which ansible/roles/vault
# bootstraps ONCE with the init root token right before revoking it
# (tasks/bootstrap_auth.yml). The policy of that role
# (vault-configurator.hcl, mounted next to this script) can manage
# policies, auth, mounts, PKI, Transit keys and audit devices, and has no
# capability on zuno/data/* - this Job configures Vault, it never reads a
# platform secret.
set -eu

: "${VAULT_ADDR:?}" "${VAULT_CACERT:?}"
JWT_FILE=/var/run/secrets/kubernetes.io/serviceaccount/token
VAULT_TOKEN="$(vault write -field=token auth/kubernetes/login role=vault-configurator jwt=@"$JWT_FILE")"
export VAULT_TOKEN
echo "Logged in to $VAULT_ADDR as vault-configurator."

enable_if_new() {
  label="$1"; shift
  if err="$("$@" 2>&1 >/dev/null)"; then
    echo "$label: enabled"
  else
    case "$err" in
      # sys/mounts (secrets engines) and sys/audit (audit devices) word
      # their "already exists" error differently ("path is already in
      # use" vs "path already in use") - both must be tolerated here, or
      # a re-run past the first audit-device enable fails outright.
      *"path is already in use"*|*"path already in use"*) echo "$label: already enabled" ;;
      *) echo "$err" >&2; exit 1 ;;
    esac
  fi
}

enable_if_new "KV v2 secrets engine at zuno/" vault secrets enable -path=zuno -version=2 kv
enable_if_new "Kubernetes auth method" vault auth enable kubernetes

vault write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc:443

# The configurator re-applies its own policy from the mounted file, so a
# change to vault-configurator.hcl reaches Vault on the next run without
# another root token. (The bootstrap wrote the same file the first time.)
vault policy write vault-configurator /policies/vault-configurator.hcl
vault write auth/kubernetes/role/vault-configurator \
  bound_service_account_names=vault-configure \
  bound_service_account_namespaces=zuno-vault \
  policies=vault-configurator \
  ttl=15m

# ADR-0602 clause 1 / WP-223: the identity every Ansible seed task uses
# instead of the root token (ansible/tasks/vault_login.yml logs in as the
# ansible-seeder ServiceAccount). create/read/update on the KV data and
# metadata, read on the PKI root - nothing else, no delete.
vault policy write ansible-seeder /policies/ansible-seeder.hcl
vault write auth/kubernetes/role/ansible-seeder \
  bound_service_account_names=ansible-seeder \
  bound_service_account_namespaces=zuno-vault \
  policies=ansible-seeder \
  ttl=1h \
  max_ttl=2h

# gitops/charts/vault templates/cronjob-raft-snapshot.yaml.
vault policy write raft-snapshot /policies/raft-snapshot.hcl
vault write auth/kubernetes/role/raft-snapshot \
  bound_service_account_names=vault-raft-snapshot \
  bound_service_account_namespaces=zuno-vault \
  policies=raft-snapshot \
  ttl=15m

echo "Configurator, seeder and raft-snapshot identities configured."

# ADR-0602 clause 2 / WP-223: one policy and one role per namespace, from
# platform/vault/secret-access.yaml. ansible/roles/vault renders that file
# into the vault-configure-secret-access ConfigMap mounted at
# /secret-access: one ns-<namespace>.hcl per namespace (read on exactly
# its listed zuno/data/<key> paths). Each role is bound to the
# namespace's own vault-reader ServiceAccount, which its SecretStore
# (gitops/charts/external-secrets) authenticates as.
SECRET_ACCESS_DIR=/secret-access
found=0
for policy_file in "$SECRET_ACCESS_DIR"/ns-*.hcl; do
  [ -e "$policy_file" ] || continue
  found=$((found + 1))
  name="$(basename "$policy_file" .hcl)"
  namespace="${name#ns-}"
  vault policy write "$name" "$policy_file" >/dev/null
  vault write "auth/kubernetes/role/$name" \
    bound_service_account_names=vault-reader \
    bound_service_account_namespaces="$namespace" \
    policies="$name" \
    ttl=1h >/dev/null
  echo "$name: policy and role written"
done
echo "Per-namespace External Secrets roles: $found written."

# A namespace removed from secret-access.yaml loses its role and policy
# here, not whenever someone remembers: a stale grant is still a grant.
for role in $(vault list -format=json auth/kubernetes/role | tr -d '[]", ' | tr '\n' ' '); do
  case "$role" in
    ns-*)
      if [ ! -e "$SECRET_ACCESS_DIR/$role.hcl" ]; then
        vault delete "auth/kubernetes/role/$role" >/dev/null
        vault policy delete "$role" >/dev/null
        echo "$role: removed (no longer in secret-access.yaml)"
      fi
      ;;
  esac
done

# The single eso-reader role (read zuno/data/* for the ClusterSecretStore,
# usable by an ExternalSecret in ANY namespace) is what clause 2 retires.
# Deleted only once the per-namespace roles exist (RETIRE_ESO_READER is
# set by ansible/roles/vault when secret-access.yaml lists namespaces):
# deleting it first would break every ExternalSecret still on the old store.
if [ "${RETIRE_ESO_READER:-false}" = "true" ] && [ "$found" -gt 0 ]; then
  vault delete auth/kubernetes/role/eso-reader >/dev/null
  vault policy delete eso-reader >/dev/null
  echo "eso-reader role and policy: removed."
fi

echo "KV store and access policies configured."

# Prepares the pki/ engine + cert-manager-issuer role/policy consumed
# by cert_manager's ClusterIssuer (that role never writes to Vault itself).
enable_if_new "PKI secrets engine at pki/" vault secrets enable -path=pki pki
vault secrets tune -max-lease-ttl=87600h pki

if ! vault read pki/cert/ca >/dev/null 2>&1; then
  vault write -field=certificate pki/root/generate/internal \
    common_name="zuno-demo.internal" ttl=87600h >/dev/null
  echo "PKI root CA: generated"
else
  echo "PKI root CA: already generated"
fi

# AIA/CRL URLs embedded in every issued cert. $VAULT_ADDR is the https
# Service address since ADR-0602 clause 1 / WP-223 (the Job's env), so
# certs issued from here on point at https; certs issued before keep their
# http URLs until they renew (max_ttl 720h).
vault write pki/config/urls \
  issuing_certificates="$VAULT_ADDR/v1/pki/ca" \
  crl_distribution_points="$VAULT_ADDR/v1/pki/crl"

# ${CLUSTER_BASE_DOMAIN} (the OpenShift apps wildcard domain, e.g.
# apps.<cluster>.<base-domain>) is included so cert-manager can sign
# certs for externally-facing hostnames like keycloak.<domain> - see
# gitops/charts/keycloak/templates/ingress.yaml, the first real consumer
# of vault-issuer. allow_subdomains=true covers keycloak.<domain>.
# require_cn=false: ingress-shim generates Certificates from Ingress
# tls.hosts without a commonName (SANs only) unless the
# cert-manager.io/common-name annotation is set, which Vault rejects
# outright unless this is set - same issue as pki/roles/istio below.
# Bare "svc" (not just svc.cluster.local) is included for the same
# reason pki/roles/istio below needs it: Authorino's
# authorino-server-tls Certificate requests the short-form in-cluster
# SAN (authorino-authorino-authorization.kuadrant-system.svc), which
# svc.cluster.local's allow_subdomains doesn't cover - Vault rejects
# the sign request ("subject alternate name ... not allowed by this
# role") otherwise.
# key_type=any (not Vault's rsa-only default): mariadb-operator's
# cert-manager Certificate requests an ECDSA key for the MariaDB
# server cert (ADR: DSP components verify MySQL TLS against the ODH
# CA bundle, whose first entry is this PKI root) - Vault refuses
# ("role requires keys of type rsa") otherwise. "any" keeps every
# existing RSA consumer working and admits EC requesters.
vault write pki/roles/cert-manager \
  allowed_domains="zuno-demo.internal,svc.cluster.local,svc,${CLUSTER_BASE_DOMAIN}" \
  allow_subdomains=true \
  allow_bare_domains=true \
  require_cn=false \
  key_type=any \
  max_ttl=720h

printf 'path "pki/sign/cert-manager" {\n  capabilities = ["create","update"]\n}\n' | vault policy write cert-manager-issuer -

vault write auth/kubernetes/role/cert-manager-issuer \
  bound_service_account_names=cert-manager \
  bound_service_account_namespaces=cert-manager \
  policies=cert-manager-issuer \
  ttl=1h

echo "PKI engine and cert-manager-issuer role configured."

# Dedicated pki/roles/mariadb (same isolation rationale as
# pki/roles/istio below): mariadb-operator's server Certificate
# requests a FIXED wide SAN set (mariadb, mariadb.zuno-data,
# *.mariadb-internal..., mariadb-primary/-secondary variants,
# localhost) that pki/roles/cert-manager rightly refuses
# ("subject alternate name mariadb.zuno-data not allowed"). Widening
# the shared role to cover bare short names and localhost would loosen
# it for every consumer, so MariaDB gets its own scoped role instead,
# consumed by gitops/charts/mariadb's vault-issuer-mariadb
# ClusterIssuer. allow_wildcard_certificates is Vault's default true -
# required for the *.mariadb-internal SANs.
vault write pki/roles/mariadb \
  allowed_domains="zuno-data,mariadb,mariadb-internal,mariadb-primary,mariadb-secondary,localhost,svc.cluster.local,svc" \
  allow_subdomains=true \
  allow_bare_domains=true \
  require_cn=false \
  key_type=any \
  max_ttl=720h

printf 'path "pki/sign/mariadb" {\n  capabilities = ["create","update"]\n}\n' | vault policy write mariadb-issuer -

vault write auth/kubernetes/role/mariadb-issuer \
  bound_service_account_names=cert-manager \
  bound_service_account_namespaces=cert-manager \
  policies=mariadb-issuer \
  ttl=1h

echo "PKI mariadb role and mariadb-issuer configured."

# Dedicated pki/roles/istio + istio-issuer role/policy, separate from
# cert-manager's own role above, consumed by service_mesh's
# vault-issuer-istio ClusterIssuer (that role never writes to Vault
# itself). Isolated from pki/roles/cert-manager so the mesh's SPIFFE
# trust root has a different blast radius than general-purpose TLS certs.
# allowed_uri_sans: the mesh CA signs workload certs with SPIFFE identity
# URIs (spiffe://cluster.local/ns/<ns>/sa/<sa>) as the SAN, not DNS names.
# allowed_domains includes bare "svc" (not just svc.cluster.local) because
# cert-manager-istio-csr requests istiod's serving cert for the
# short-form in-cluster DNS name (istiod.<namespace>.svc), not only the
# fully-qualified one - allow_subdomains=true then covers it.
# require_cn=false: istio-csr's own serving cert CSR has no commonName
# (SANs only), which Vault rejects outright unless this is set.
vault write pki/roles/istio \
  allowed_domains="zuno-demo.internal,svc.cluster.local,cluster.local,svc" \
  allow_subdomains=true \
  allow_bare_domains=true \
  allowed_uri_sans="spiffe://cluster.local/*" \
  require_cn=false \
  max_ttl=24h

printf 'path "pki/sign/istio" {\n  capabilities = ["create","update"]\n}\n' | vault policy write istio-issuer -

# bound_service_account_names/namespaces=cert-manager/cert-manager: same
# identity as cert-manager-issuer's role above - cert-manager always
# authenticates to Vault as itself (TokenRequest for its own SA), never
# as the workload requesting a Certificate through the issuer. NOT
# cert-manager-istio-csr/zuno-mesh: that SA belongs to the istio-csr
# Deployment, not cert-manager's own controller pod.
vault write auth/kubernetes/role/istio-issuer \
  bound_service_account_names=cert-manager \
  bound_service_account_namespaces=cert-manager \
  policies=istio-issuer \
  ttl=1h

echo "istio-issuer role configured."

# ADR-0420/WP-068: Transit secrets engine backing in-cluster supply-chain
# signing (replaces GitHub-OIDC/Fulcio/Rekor keyless cosign - see the
# ADR for the full rationale). A single non-exportable ECDSA key signs
# server-side via cosign's native hashivault:// KMS mode; verifiers only
# ever need the key's public half (read from transit/keys, never
# exported into the repository since WP-165), never Vault signing
# access - smaller blast radius than the PKI engine above, whose
# pki/issue would hand back a private key that would then need to
# live in a Secret.
enable_if_new "Transit secrets engine at transit/" vault secrets enable -path=transit transit

if ! vault read transit/keys/zuno-platform-signer >/dev/null 2>&1; then
  vault write -f transit/keys/zuno-platform-signer type=ecdsa-p256 >/dev/null
  echo "Transit key zuno-platform-signer: generated"
else
  echo "Transit key zuno-platform-signer: already generated"
fi

# exportable=false/allow_plaintext_backup=false are Transit's own
# defaults, but set explicitly here so this key's non-exportability is a
# readable fact in this script, not an assumption about Vault's defaults.
vault write transit/keys/zuno-platform-signer/config \
  exportable=false \
  allow_plaintext_backup=false

# Both the bare path and the /* glob are needed: cosign's hashivault KMS
# client calls transit/sign/<key>/<hash-algorithm> (e.g.
# transit/sign/zuno-platform-signer/sha2-256), not the bare
# transit/sign/<key> path - Vault policy paths are exact-match, so the
# glob is required or every sign-blob call 403s. WP-165 removed the
# zuno/data/okf-signatures write the OKF signing Job needed (ADR-0578:
# OKF releases are signed keyless outside the cluster).
printf 'path "transit/sign/zuno-platform-signer" {\n  capabilities = ["update"]\n}\npath "transit/sign/zuno-platform-signer/*" {\n  capabilities = ["update"]\n}\npath "transit/keys/zuno-platform-signer" {\n  capabilities = ["read"]\n}\n' | vault policy write platform-signer -

# bound to the zuno-signer ServiceAccount in zuno-ai-build
# (ansible/roles/supply_chain_signer_build creates it) - the in-cluster
# signing Job/debug pod authenticates as this identity, never as a
# human or a GitHub Actions runner.
vault write auth/kubernetes/role/platform-signer \
  bound_service_account_names=zuno-signer \
  bound_service_account_namespaces=zuno-ai-build \
  policies=platform-signer \
  ttl=1h

echo "Transit engine and platform-signer role configured."

# In-cluster substitute for the Rekor transparency log this replaces:
# every transit/sign call is now an audited event instead of a public
# append-only log entry. Safe to re-run - "already enabled" is expected
# from the second run onward.
enable_if_new "File audit device (stdout)" vault audit enable file file_path=stdout
