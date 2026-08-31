#!/usr/bin/env bash
# Start a Claude Code session in a new Herdr tab, Remote Control on.
#
#   handover.sh <name> [brief-file]
#
# The tab sits beside this one in Herdr, in this directory, and answers from
# the Claude app as well as from the keyboard.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $(basename "$0") <name> [brief-file]" >&2
  exit 2
fi

if [ "${HERDR_ENV:-}" != 1 ]; then
  echo "not inside Herdr, so there is no session to open a tab in" >&2
  exit 1
fi

name="$1"
brief="${2:-}"

# Herdr's own rule for an agent name, checked here so the failure names itself
# rather than arriving as a rejected API call.
if ! printf '%s' "$name" | grep -qE '^[a-z][a-z0-9_-]{0,31}$'; then
  echo "\"$name\" is not a Herdr agent name: lowercase, 32 characters, starts with a letter" >&2
  exit 2
fi

if [ -n "$brief" ] && [ ! -r "$brief" ]; then
  echo "no brief at $brief" >&2
  exit 2
fi

pane="$(herdr tab create --cwd "$PWD" --label "$name" --focus |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')"

if [ -z "$pane" ]; then
  echo "the tab was created but its pane id did not come back" >&2
  exit 1
fi

herdr agent start "$name" --kind claude --pane "$pane" -- --remote-control "$name" >/dev/null

if [ -n "$brief" ]; then
  herdr agent prompt "$name" "$(cat "$brief")" >/dev/null
fi

echo "$name is running in $pane, in $PWD"
echo "  herdr agent read $name      what it has said"
echo "  herdr agent focus $name     bring the tab up"
echo "Remote Control connects as \"$name\"; the app lists it once it is up."
