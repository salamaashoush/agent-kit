#!/usr/bin/env bash
# Open a Claude Code session in a new terminal window, Remote Control on.
#
#   handover.sh <name> [brief-file]
#
# The session runs here, in this directory, in a window you can watch, and
# answers from the Claude app as well as from the keyboard.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $(basename "$0") <name> [brief-file]" >&2
  exit 2
fi

name="$1"
brief="${2:-}"
here="$PWD"

if [ -n "$brief" ] && [ ! -r "$brief" ]; then
  echo "no brief at $brief" >&2
  exit 2
fi

# The prompt travels in a file, so a brief holding quotes, newlines and shell
# punctuation reaches the session as written.
if [ -n "$brief" ]; then
  run="cd $(printf %q "$here") && exec claude --remote-control $(printf %q "$name") \"\$(cat $(printf %q "$brief"))\""
else
  run="cd $(printf %q "$here") && exec claude --remote-control $(printf %q "$name")"
fi

for terminal in "${TERMINAL:-}" foot ghostty kitty alacritty wezterm; do
  [ -n "$terminal" ] && command -v "$terminal" >/dev/null 2>&1 || continue
  setsid "$terminal" -e bash -lc "$run" >/dev/null 2>&1 &
  disown
  echo "$name is starting in a new $terminal window, in $here"
  echo "Remote Control connects as \"$name\"; the app lists it once it is up."
  exit 0
done

echo "no terminal to open a window with; run it yourself:" >&2
echo "  claude --remote-control $name${brief:+ \"\$(cat $brief)\"}" >&2
exit 1
