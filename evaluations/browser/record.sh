#!/usr/bin/env bash
# WP-284 / ADR-0617: record a demo's walkthrough in the Playwright image (browsers matching playwright@1.48.0).
# Needs podman and `oc` logged in. Only the persona password is read (with oc), passed through the environment, never
# printed and never on a command line. A live action: it signs in as the walkthrough's persona and spends its budget.
#   evaluations/browser/record.sh <id> [OUT_DIR]
#   evaluations/browser/record.sh <id> [OUT_DIR] --scout     (or RECORD_SCOUT=1)
# --scout only signs in and opens the menus the walkthrough uses: no prompt sent, no chat, no model call, no video.
# It leaves scout.json and scout-<step>.png; last line `SCOUT: done` (exit 0) or `SCOUT: failed <steps>` (exit 1).
# OUT_DIR defaults to ~/.cache/zuno/demo/recordings/<id>-<YYYYmmdd-HHMMSS>/ (created, mode 700). It receives
# recording.webm, markers.json and one PNG per marker; its path is printed first, so also when the take fails.
# Exit code: 0 pass, 1 the walkthrough or its cleanup failed, 2 usage or environment.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
scout="${RECORD_SCOUT:-0}"
args=()
for arg in "$@"; do
  if [[ "$arg" == "--scout" ]]; then scout=1; else args+=("$arg"); fi
done
set -- "${args[@]+"${args[@]}"}"
[[ "$scout" == "1" ]] || scout=0
id="${1:-}"
if [[ ! "$id" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "usage: evaluations/browser/record.sh <id> [OUT_DIR] [--scout]" >&2
  exit 2
fi
if [[ ! -f "$here/walkthroughs/$id.mjs" ]]; then
  echo "no walkthrough for $id: evaluations/browser/walkthroughs/$id.mjs is missing" >&2
  exit 2
fi
for tool in oc podman; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is not on PATH" >&2; exit 2; }
done
out="${2:-${XDG_CACHE_HOME:-$HOME/.cache}/zuno/demo/recordings/$id-$(date +%Y%m%d-%H%M%S)$([[ $scout == 1 ]] && echo -scout)}"
mkdir -p "$out" && chmod 700 "$out" || { echo "cannot create $out" >&2; exit 2; }
out="$(cd "$out" && pwd)"
echo "recording: $out"   # printed first, so a failed take still says where its files are; RESULT stays the last line
domain="$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}' 2>/dev/null)"
if [[ -z "$domain" ]]; then
  echo "the cluster domain could not be read: is oc logged in?" >&2
  exit 2
fi
PERSONA_PASSWORD="$(oc -n zuno-ai-run get secret acceptance-gate-credentials -o jsonpath='{.data.demo-persona-password}' 2>/dev/null | base64 -d 2>/dev/null)"
if [[ -z "$PERSONA_PASSWORD" ]]; then
  echo "the persona password could not be read (Secret acceptance-gate-credentials in zuno-ai-run)" >&2
  exit 2
fi
export PERSONA_PASSWORD
podman run --rm -e DEMO="$id" -e RECORD_SCOUT="$scout" -e APPS_DOMAIN="$domain" -e PERSONA_PASSWORD -e OUT=/out \
  -v "$here:/work:Z" -v "$out:/out:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
  sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; node record.mjs'
rc=$?
if [[ $rc -ne 0 && $rc -ne 1 ]]; then
  # node could not run the recorder at all (125-127 from podman, a crash): the contract's last line all the same.
  if [[ $scout == 1 ]]; then echo "SCOUT: failed the recorder did not run to its end (exit $rc)"
  else echo "RESULT: FAIL the recorder did not run to its end (exit $rc)"; fi
  rc=$([[ $rc -eq 2 ]] && echo 2 || echo 1)
fi
exit $rc
