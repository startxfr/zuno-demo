#!/usr/bin/env bash
# ADR-0628 / WP-331: mint a read-only, 30-minute Vault token for the presenter
# of the vault-pki demo, who then signs in to the Vault web UI with it.
#
#   platform/vault/demo_token.sh           token copied to the clipboard
#   platform/vault/demo_token.sh --print   token on stdout, only into a pipe or
#                                          a file (refused on a terminal): the
#                                          GIF's browser take reads it this way
#
# 1. `oc create token vault-demo-reader` (zuno-vault, 10 minutes): a
#    ServiceAccount JWT that only Vault's Kubernetes auth uses; the account
#    has no Kubernetes RBAC.
# 2. Vault login, role demo-reader, run by the vault CLI inside the Vault pod
#    (its own VAULT_ADDR and VAULT_CACERT), the JWT on stdin - the same
#    pattern as ansible/tasks/vault_login.yml, never on a command line.
# 3. The client token goes to the clipboard (wl-copy, else xclip) through
#    stdin. The script prints the role, the policies and the TTL, never the
#    token. Policy demo-reader (ansible/roles/vault/kustomize/configure/
#    vault-demo-reader.hcl): read and list on names, versions and metadata,
#    no secret value, no write, no sudo; the token cannot be renewed past
#    30 minutes.
#
# Needs: oc logged in with the right to create a token for that
# ServiceAccount and to exec into the Vault pod (paas-ops-01 has both),
# python3, and wl-copy or xclip unless --print.
set -euo pipefail

NS=zuno-vault
SA=vault-demo-reader
ROLE=demo-reader

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

mode=clipboard
case "${1:-}" in
  "") ;;
  --print) mode=print ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [[ $mode == print && -t 1 ]]; then
  echo "demo_token: --print writes the token to stdout; stdout is a terminal, so it would be on screen. Pipe it or capture it: VAR=\$($0 --print)" >&2
  exit 2
fi

copy_cmd=()
if [[ $mode == clipboard ]]; then
  if command -v wl-copy >/dev/null 2>&1 && [[ -n ${WAYLAND_DISPLAY:-} ]]; then
    copy_cmd=(wl-copy)
  elif command -v xclip >/dev/null 2>&1 && [[ -n ${DISPLAY:-} ]]; then
    copy_cmd=(xclip -selection clipboard)
  else
    echo "demo_token: no clipboard tool for this session (wl-copy with WAYLAND_DISPLAY, or xclip with DISPLAY). Install wl-clipboard or xclip; nothing was minted." >&2
    exit 1
  fi
fi

pod="$(oc get pods -n "$NS" -l app.kubernetes.io/name=vault,component=server \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z $pod ]]; then
  echo "demo_token: no Running Vault server pod in $NS." >&2
  exit 1
fi

jwt="$(oc create token "$SA" -n "$NS" --duration=10m)"
login="$(printf '%s' "$jwt" | oc exec -i -n "$NS" "$pod" -c vault -- \
  vault write -format=json auth/kubernetes/login role="$ROLE" jwt=-)"
unset jwt

# One python3 pass splits the login answer: line 1 the token, line 2 what may be shown.
parsed="$(printf '%s' "$login" | python3 -c '
import json, sys
auth = json.load(sys.stdin)["auth"]
policies = ",".join(p for p in auth.get("token_policies") or auth.get("policies") or [] if p != "default")
print(auth["client_token"])
print("role %s, policies %s, valid %d min" % ((auth.get("metadata") or {}).get("role") or sys.argv[1],
                                             policies or "-", int(auth.get("lease_duration", 0)) // 60))
' "$ROLE")"
unset login
token="${parsed%%$'\n'*}"
summary="${parsed#*$'\n'}"
unset parsed

if [[ -z $token || $token == "$summary" ]]; then
  echo "demo_token: the Vault login answered without a token." >&2
  exit 1
fi

if [[ $mode == print ]]; then
  printf '%s\n' "$token"
  echo "demo_token: $summary (token written to stdout)" >&2
else
  printf '%s' "$token" | "${copy_cmd[@]}"
  echo "Vault token copied to the clipboard: $summary."
  echo "Vault UI: sign in with the method Token, paste it in the masked field."
fi
unset token
