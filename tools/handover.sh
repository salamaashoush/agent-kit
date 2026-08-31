#!/usr/bin/env bash
# Hand a piece of work to a background Claude session, briefed and followable.
#
#   handover.sh <name> <brief-file>
#   handover.sh <name> -            # brief on stdin
#
# Prints the session id and how to reach it. The brief is the whole job: the
# session has none of the conversation that produced it.
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $(basename "$0") <name> <brief-file|->" >&2
  exit 2
fi

name="$1"
source="$2"

if [ "$source" = "-" ]; then
  brief="$(cat)"
elif [ -r "$source" ]; then
  brief="$(cat "$source")"
else
  echo "no brief at $source" >&2
  exit 2
fi

if [ -z "${brief//[[:space:]]/}" ]; then
  echo "the brief is empty; a session with no brief does nothing useful" >&2
  exit 2
fi

# `--bg` isolates the session in its own git worktree, so the current tree and
# branch are untouched and the work arrives as a branch to merge.
started="$(claude --bg --remote-control "$name" "$brief" 2>&1)"
id="$(printf '%s\n' "$started" | grep -oE 'backgrounded · [0-9a-f]+' | awk '{print $3}')"

if [ -z "$id" ]; then
  printf '%s\n' "$started" >&2
  echo "could not read a session id from that; nothing to follow" >&2
  exit 1
fi

printf 'session %s\n' "$id"

# The worktree appears once the session has started; it is where the work lands.
for _ in $(seq 20); do
  tree="$(git worktree list 2>/dev/null | grep -F '.claude/worktrees/' | tail -1 || true)"
  [ -n "$tree" ] && break
  sleep 1
done
[ -n "${tree:-}" ] && printf 'worktree %s\n' "$tree"

cat <<EOF

  claude attach $id    open it here
  claude logs $id      what it has said
  claude stop $id      stop it

Remote Control was asked for as "$name". If it does not appear in the Claude
app, attach and run /rc: that path connects for certain.
EOF
