#!/usr/bin/env bash
# check-careful.sh — PreToolUse hook for /careful skill
# Reads JSON from stdin, checks Bash command for destructive patterns.
# Returns {"permissionDecision":"ask","message":"..."} to warn, or {} to allow.
#
# This hook runs on EVERY Bash tool call — a median session makes ~290 of them,
# so a fork costs ~30s over a session. Everything on the allow path is therefore
# a bash builtin: `[[ =~ ]]` rather than `grep -E`, `nocasematch` rather than
# `tr`, parameter expansion rather than `sed`. Subprocesses are confined to the
# warn path, which fires rarely. Constructs stay bash 3.2-compatible because the
# hook's PATH may resolve to /bin/bash rather than a newer one.
set -euo pipefail

# Read all of stdin without forking a `cat`. `read -d ''` returns non-zero at
# EOF with no NUL seen, which is the normal case here, so the status is ignored.
IFS= read -r -d '' INPUT || true

# Extract tool_input.command. The regex handles the 99% case; the Python
# fallback below covers commands carrying escaped quotes.
CMD=""
cmd_re='"command"[[:space:]]*:[[:space:]]*"([^"]*)"'
if [[ $INPUT =~ $cmd_re ]]; then
  CMD="${BASH_REMATCH[1]}"
fi

if [ -z "$CMD" ]; then
  CMD=$(printf '%s' "$INPUT" | python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("tool_input",{}).get("command",""))' 2>/dev/null || true)
fi

# If we still couldn't extract a command, allow
if [ -z "$CMD" ]; then
  echo '{}'
  exit 0
fi

allow() { echo '{}'; exit 0; }

# --- Check for safe exceptions (rm -rf of build artifacts) ---
rm_recursive_re='(^|[[:space:]])rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*[[:space:]]+|--recursive[[:space:]]+)'
if [[ $CMD =~ $rm_recursive_re ]]; then
  # Walk the words after `rm`, skipping flags. Every remaining target must be a
  # known build artifact for the command to bypass the warning; anything else,
  # including an unparseable target, falls through to the destructive checks.
  read -ra WORDS <<<"$CMD"
  SAFE_ONLY=false
  seen_rm=false
  for target in "${WORDS[@]}"; do
    if [ "$seen_rm" = false ]; then
      case "$target" in
        rm | */rm) seen_rm=true; SAFE_ONLY=true ;;
      esac
      continue
    fi
    case "$target" in
      -* | --recursive) ;; # flag, skip
      */node_modules | node_modules | */.next | .next | */dist | dist | */__pycache__ | __pycache__ | */.cache | .cache | */build | build | */.turbo | .turbo | */coverage | coverage)
        ;; # safe target
      *)
        SAFE_ONLY=false
        break
        ;;
    esac
  done
  if [ "$SAFE_ONLY" = true ]; then
    allow
  fi
fi

# --- Destructive pattern checks ---
WARN=""
PATTERN=""

# rm -rf / rm -r / rm --recursive
re='(^|[[:space:]])rm[[:space:]]+(-[a-zA-Z]*r|--recursive)'
if [[ $CMD =~ $re ]]; then
  WARN="Destructive: recursive delete (rm -r). This permanently removes files."
  PATTERN="rm_recursive"
fi

# SQL keywords are matched case-insensitively, as `tr` did before.
shopt -s nocasematch

# DROP TABLE / DROP DATABASE
re='drop[[:space:]]+(table|database)'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: SQL DROP detected. This permanently deletes database objects."
  PATTERN="drop_table"
fi

# TRUNCATE
re='(^|[^a-zA-Z0-9_])truncate([^a-zA-Z0-9_]|$)'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: SQL TRUNCATE detected. This deletes all rows from a table."
  PATTERN="truncate"
fi

shopt -u nocasematch

# git push --force / git push -f
re='git[[:space:]]+push[[:space:]]+.*(-f([^a-zA-Z0-9_]|$)|--force)'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: git force-push rewrites remote history. Other contributors may lose work."
  PATTERN="git_force_push"
fi

# git reset --hard
re='git[[:space:]]+reset[[:space:]]+--hard'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: git reset --hard discards all uncommitted changes."
  PATTERN="git_reset_hard"
fi

# git checkout . / git restore .
re='git[[:space:]]+(checkout|restore)[[:space:]]+\.'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: discards all uncommitted changes in the working tree."
  PATTERN="git_discard"
fi

# kubectl delete
re='kubectl[[:space:]]+delete'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: kubectl delete removes Kubernetes resources. May impact production."
  PATTERN="kubectl_delete"
fi

# docker rm -f / docker system prune
re='docker[[:space:]]+(rm[[:space:]]+-f|system[[:space:]]+prune)'
if [ -z "$WARN" ] && [[ $CMD =~ $re ]]; then
  WARN="Destructive: Docker force-remove or prune. May delete running containers or cached images."
  PATTERN="docker_destructive"
fi

# --- Output ---
if [ -n "$WARN" ]; then
  # Log hook fire event (pattern name only, never command content)
  mkdir -p ~/.pstack/analytics 2>/dev/null || true
  echo '{"event":"hook_fire","skill":"careful","pattern":"'"$PATTERN"'","ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","repo":"'$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")'"}' >>~/.pstack/analytics/skill-usage.jsonl 2>/dev/null || true

  WARN_ESCAPED="${WARN//\"/\\\"}"
  printf '{"permissionDecision":"ask","message":"[careful] %s"}\n' "$WARN_ESCAPED"
else
  echo '{}'
fi
