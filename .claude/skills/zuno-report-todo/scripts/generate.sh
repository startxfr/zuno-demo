#!/usr/bin/env bash
# Usage: generate.sh [REPO_ROOT] [OUT_HTML] [--write-priorities]
# Builds the Zuno Todo HTML from the repo docs only (no cluster access).
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export SKILL_DIR REPO="$(cd "${1:-$(git rev-parse --show-toplevel)}" && pwd)"
WORK="$(mktemp -d)"; OUT="${2:-$WORK/zuno-todo.html}"; cd "$WORK"
python3 "$SKILL_DIR/../_zuno-report-common/parse_roadmap.py" >/dev/null
python3 "$SKILL_DIR/scripts/build_todo.py" ${3:-}
python3 - "$SKILL_DIR" "$OUT" <<'PY'
import sys
s,o=sys.argv[1:]
open(o,'w').write(open(s+'/assets/template.html').read().replace('/*DATA*/null',open('data.json').read()))
PY
echo "$OUT"
