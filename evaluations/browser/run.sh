#!/usr/bin/env bash
# WP-243: run the browser checks in the Playwright image (browsers matching playwright@1.48.0). Needs podman and `oc`
# logged in; the persona password is read with oc and passed through the environment, never printed.
#   evaluations/browser/run.sh [OUT_DIR]        ONLY=open-webui,kagent evaluations/browser/run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$(mktemp -d)}"
mkdir -p "$out"
domain="$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}')"
PERSONA_PASSWORD="$(oc -n zuno-ai-run get secret acceptance-gate-credentials -o jsonpath='{.data.demo-persona-password}' | base64 -d)"
OPENCLAW_UI_PASSWORD="$(oc -n zuno-claw-sale-01 get secret openclaw-ui -o jsonpath='{.data.password}' | base64 -d)"
export PERSONA_PASSWORD OPENCLAW_UI_PASSWORD
podman run --rm -e APPS_DOMAIN="$domain" -e PERSONA_PASSWORD -e OPENCLAW_UI_PASSWORD -e ONLY="${ONLY:-}" -e OUT=/out \
  -v "$here:/work:Z" -v "$out:/out:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
  sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1 && node run.mjs'
rc=$?
echo "screenshots: $out"
exit $rc
