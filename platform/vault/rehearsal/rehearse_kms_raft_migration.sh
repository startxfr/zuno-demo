#!/usr/bin/env bash
# WP-223 rehearsal: replays the Vault commands of ansible/playbooks/vault_migrate_kms_raft.yml
# on a local podman Vault 1.17.2 (no cluster): file storage + Shamir 1/1 (the pre-WP-223 install),
# file -> raft, Shamir -> awskms, auto-unseal on restart, root revocation, generate-root with the
# recovery key, rekey recovery to 3/2. Needs AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, KMS_KEY_ID
# and KMS_REGION in the environment (the IAM user of docs/platform/vault-kms-raft-migration.md).
# Prints no secret. Run: platform/vault/rehearsal/rehearse_kms_raft_migration.sh
set -euo pipefail
D=${REHEARSAL_DIR:-$(mktemp -d)/run}
IMG=docker.io/hashicorp/vault:1.17.2
podman unshare rm -rf "$D"; mkdir -p "$D/data" "$D/config"; chmod -R 777 "$D"
step() { echo; echo "=== $*"; }
v() { podman exec -e VAULT_ADDR=http://127.0.0.1:8200 ${VTOKEN:+-e VAULT_TOKEN=$VTOKEN} rh-vault vault "$@"; }
start() { # $1 = config file name
  podman rm -f rh-vault >/dev/null 2>&1 || true
  podman run -d --name rh-vault --cap-add IPC_LOCK \
    -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
    -v "$D/data:/vault/data:Z" -v "$D/config:/config:Z" "$IMG" server -config=/config/$1 >/dev/null
  for i in $(seq 1 30); do rc=0; v status >/dev/null 2>&1 || rc=$?; [ $rc -ne 1 ] && break; sleep 1; done
  sleep 2
}
status_field() { { v status -format=json 2>/dev/null || true; } | python3 -c "import json,sys;print(json.load(sys.stdin)['$1'])"; }

cat > "$D/config/file.hcl" <<EOF
disable_mlock = true
listener "tcp" { address = "0.0.0.0:8200"  tls_disable = true }
storage "file" { path = "/vault/data" }
EOF
cat > "$D/config/raft-shamir.hcl" <<EOF
disable_mlock = true
listener "tcp" { address = "0.0.0.0:8200"  tls_disable = true }
storage "raft" { path = "/vault/data/raft"  node_id = "rh-vault-0" }
api_addr = "http://127.0.0.1:8200"
cluster_addr = "http://127.0.0.1:8201"
EOF
chmod 644 "$D"/config/*.hcl 2>/dev/null || true
sed "\$a seal \"awskms\" {\n  region = \"$KMS_REGION\"\n  kms_key_id = \"$KMS_KEY_ID\"\n}" "$D/config/raft-shamir.hcl" > "$D/config/raft-kms.hcl"
cat > "$D/config/migrate.hcl" <<EOF
storage_source "file" { path = "/vault/data/file-legacy" }
storage_destination "raft" { path = "/vault/data/raft"  node_id = "rh-vault-0" }
cluster_addr = "http://127.0.0.1:8201"
EOF

chmod 644 "$D"/config/*.hcl
step "0. legacy Vault: file storage, Shamir 1/1 (today's install.yml)"
start file.hcl
INIT=$(v operator init -key-shares=1 -key-threshold=1 -format=json)
UNSEAL=$(echo "$INIT" | python3 -c "import json,sys;print(json.load(sys.stdin)['unseal_keys_b64'][0])")
ROOT=$(echo "$INIT" | python3 -c "import json,sys;print(json.load(sys.stdin)['root_token'])")
v operator unseal "$UNSEAL" >/dev/null
VTOKEN=$ROOT v secrets enable -path=zuno kv-v2 >/dev/null
for i in 1 2 3; do VTOKEN=$ROOT v kv put zuno/rehearsal/key$i value=secret-$i >/dev/null; done
echo "seeded 3 keys; sealed=$(status_field sealed) storage=$(status_field storage_type)"

step "2-3. stop, move file entries to file-legacy/, vault operator migrate file -> raft"
podman rm -f rh-vault >/dev/null
podman run --rm -v "$D/data:/vault/data:Z" --entrypoint sh "$IMG" -c \
  'cd /vault/data && mkdir -p file-legacy raft && for e in * ; do case "$e" in raft|file-legacy) ;; *) mv "$e" file-legacy/ ;; esac; done; chown -R vault:vault /vault/data'
podman run --rm -v "$D/data:/vault/data:Z" -v "$D/config:/config:Z" "$IMG" operator migrate -config=/config/migrate.hcl | tail -2

step "4. start on raft (still Shamir), unseal, verify data"
start raft-shamir.hcl
v operator unseal "$UNSEAL" >/dev/null
echo "sealed=$(status_field sealed) storage=$(status_field storage_type)"
for i in 1 2 3; do VTOKEN=$ROOT v kv get -field=value zuno/rehearsal/key$i; done

step "5. seal migration Shamir -> awskms (unseal -migrate)"
start raft-kms.hcl
v operator unseal -migrate "$UNSEAL" >/dev/null
echo "sealed=$(status_field sealed) type=$(status_field type) recovery_seal=$(status_field recovery_seal)"

step "6. restart: must unseal by itself through KMS"
podman restart rh-vault >/dev/null; sleep 6
echo "sealed=$(status_field sealed) type=$(status_field type)"
for i in 1 2 3; do VTOKEN=$ROOT v kv get -field=value zuno/rehearsal/key$i; done

step "7. revoke the root token"
VTOKEN=$ROOT v token revoke -self >/dev/null
if VTOKEN=$ROOT v kv get zuno/rehearsal/key1 >/dev/null 2>&1; then echo "FAIL: root still valid"; exit 1; else echo "root token revoked (403 as expected)"; fi

step "8. generate-root with the recovery key (the former unseal key), then rekey recovery to 3/2"
OTP=$(v operator generate-root -generate-otp)
NONCE=$(v operator generate-root -init -otp="$OTP" -format=json | python3 -c "import json,sys;print(json.load(sys.stdin)['nonce'])")
ENC=$(v operator generate-root -nonce="$NONCE" -format=json "$UNSEAL" | python3 -c "import json,sys;print(json.load(sys.stdin)['encoded_root_token'])")
NEWROOT=$(v operator generate-root -decode="$ENC" -otp="$OTP")
VTOKEN=$NEWROOT v kv get -field=value zuno/rehearsal/key1
RK=$(v operator rekey -target=recovery -init -key-shares=3 -key-threshold=2 -format=json | python3 -c "import json,sys;print(json.load(sys.stdin)['nonce'])")
OUT=$(v operator rekey -target=recovery -nonce="$RK" -format=json "$UNSEAL")
echo "rekey -> $(echo "$OUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d.get('keys_base64') or d.get('keys') or []),'recovery keys')")"
VTOKEN=$NEWROOT v token revoke -self >/dev/null
podman rm -f rh-vault >/dev/null
echo; echo "REHEARSAL OK"
