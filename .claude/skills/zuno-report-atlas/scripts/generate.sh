#!/usr/bin/env bash
# Usage: generate.sh [REPO_ROOT] [OUT_HTML]
# Builds the self-contained Zuno Atlas HTML from the repo docs + a live read-only cluster snapshot.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export SKILL_DIR REPO="$(cd "${1:-$(git rev-parse --show-toplevel)}" && pwd)"
WORK="$(mktemp -d)"; OUT="${2:-$WORK/zuno-atlas.html}"
cd "$WORK"
python3 "$SKILL_DIR/../_zuno-report-common/parse_roadmap.py"
bash "$SKILL_DIR/scripts/collect_cluster.sh"
python3 "$SKILL_DIR/scripts/build_comps.py"      # prints pods that match no component: add them to assets/components.py
python3 "$SKILL_DIR/scripts/build_data.py"
python3 - "$SKILL_DIR" "$OUT" <<'PY'
import sys
s,o=sys.argv[1:]
open(o,'w').write(open(s+'/assets/template.html').read().replace('/*DATA*/null',open('data.json').read()))
PY
echo "$OUT"
