#!/usr/bin/env bash
# Symlink this repo's instructions and skills into ~/.claude.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

link() {
  local src="$1" dest="$2"
  if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
    printf '  ok       %s\n' "${dest#"$HOME"/}"
    return
  fi
  # A real file here is the user's own, so back it up rather than clobber it.
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    printf '  backup   %s -> %s.bak-%s\n' "${dest#"$HOME"/}" "${dest#"$HOME"/}" "$(date +%F)"
    $DRY_RUN || mv "$dest" "$dest.bak-$(date +%F)"
  fi
  printf '  link     %s\n' "${dest#"$HOME"/}"
  $DRY_RUN || ln -sfn "$src" "$dest"
}

$DRY_RUN && echo "dry run, nothing will change"
echo "installing into $CLAUDE"

$DRY_RUN || mkdir -p "$CLAUDE"

for f in CLAUDE.md RTK.md; do
  link "$REPO/$f" "$CLAUDE/$f"
done

echo
echo "mylint stays in the repo:"
echo "  python3 $REPO/tools/mylint.py --pr <file>"
