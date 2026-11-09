#!/usr/bin/env bash
# Installs the latest Zuno 3D add-on from origin/devel into every Blender user add-on folder found on this machine
# (Flatpak and native), without touching the working tree or the current branch of the checkout it runs in.
#
#   bash evaluations/blender/install_addon.sh            # fetch, install, show version and checksum
#   bash evaluations/blender/install_addon.sh --dry-run  # same, but copy nothing
#
# After an update: close Blender completely and reopen it (a running Blender keeps the old module in memory), then
# tick "Zuno 3D generator (demo)" in Edit > Preferences > Add-ons if it is not ticked.
# The add-on settings (Cluster domain, Gateway override, Issuer override) live in the SCENE, not in the preferences:
# a new Blender session starts with the defaults (empty overrides) unless a saved .blend carries other values.
set -euo pipefail

BRANCH=${ZUNO_ADDON_BRANCH:-devel}
FILE=evaluations/blender/zuno_3d_generator.py
dry=0; [ "${1:-}" = "--dry-run" ] && dry=1

repo=$(git rev-parse --show-toplevel)
git -C "$repo" fetch -q origin "$BRANCH"
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
git -C "$repo" show "origin/$BRANCH:$FILE" > "$tmp"
want=$(md5sum "$tmp" | cut -d' ' -f1)
ver=$(grep -m1 -o '"version": ([0-9, ]*)' "$tmp" || true)
echo "origin/$BRANCH $(git -C "$repo" rev-parse --short "origin/$BRANCH"): add-on $ver, md5 $want"

# Update the copies that already exist; if there is none, install into the first folder found (newest Flatpak first).
dirs=()
for dir in "$HOME"/.var/app/org.blender.Blender/config/blender/*/scripts/addons \
           "$HOME"/.config/blender/*/scripts/addons; do
  [ -d "$dir" ] && dirs+=("$dir")
done
[ "${#dirs[@]}" -gt 0 ] || { echo "No Blender user add-on folder found (start Blender once, or create .../scripts/addons)."; exit 1; }
targets=()
for dir in "${dirs[@]}"; do [ -f "$dir/zuno_3d_generator.py" ] && targets+=("$dir"); done
[ "${#targets[@]}" -gt 0 ] || { targets=("${dirs[-1]}"); echo "no installed copy found, installing into ${targets[0]}"; }
for dir in "${targets[@]}"; do
  dest="$dir/zuno_3d_generator.py"
  have=$( [ -f "$dest" ] && md5sum "$dest" | cut -d' ' -f1 || echo none )
  if [ "$have" = "$want" ]; then
    echo "up to date : $dest"
  elif [ "$dry" = 1 ]; then
    echo "would update: $dest (md5 $have)"
  else
    cp "$tmp" "$dest" && echo "updated    : $dest (was md5 $have)"
  fi
done
[ "$dry" = 1 ] || echo "Now close Blender completely and reopen it."
