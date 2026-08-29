#!/usr/bin/env bash
# Install this repo into ~/.claude. See tools/install.py for what that means.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (the installer parses and merges JSON)" >&2
  exit 1
fi
# tomllib, for config/tools.toml.
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "python3 3.11 or newer is required, found $(python3 -V)" >&2
  exit 1
fi

exec python3 "$REPO/tools/install.py" "$@"
