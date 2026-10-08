#!/usr/bin/env python3
"""Keep the rtk rewrites that change what a command means out of the hook.

    rtk-excludes.py add      put the patterns below into rtk's exclude_commands
    rtk-excludes.py remove   take them back out

rtk's grep leaves clap's `-h` as its help flag, so a rewritten `grep -h` (no
file names) printed rtk's usage instead of any match. `rtk ls` drops the owner
and the dates that `ls -l` was asked for. rtk skips a command matching
`[hooks] exclude_commands` in its own config; only that one key is edited, and
every other setting in the file is left as it is.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib

# A leading ^ makes rtk read the pattern as a regex rather than a command name.
PATTERNS = [
    r"^grep\s(.*\s)?-[a-zA-Z]*h",
    r"^ls\s(.*\s)?-[a-zA-Z]*l",
]


def config_path():
    """Where this rtk reads its config: ~/.config on Linux, Application Support
    on macOS. Asked of rtk rather than guessed."""
    try:
        shown = subprocess.run(["rtk", "config"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in shown.stdout.splitlines():
        if line.startswith("Config: "):
            return pathlib.Path(line[len("Config: "):].strip())
    return None


def array_end(text: str, start: int) -> int:
    """Index just past the `]` closing the array that opens at text[start]."""
    depth, index, quote = 0, start, None
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            index = text.find("\n", index)
            if index < 0:
                break
            continue
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError("unterminated exclude_commands array")


def with_excludes(text: str, wanted: list) -> str:
    line = "exclude_commands = [" + ", ".join(json.dumps(p) for p in wanted) + "]"
    header = re.search(r"(?m)^\[hooks\][ \t]*$", text)
    if not header:
        return text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"[hooks]\n{line}\n"

    following = re.search(r"(?m)^\[", text[header.end():])
    section_end = header.end() + (following.start() if following else len(text) - header.end())
    key = re.search(r"(?m)^exclude_commands[ \t]*=[ \t]*", text[header.end():section_end])
    if not key:
        return text[:header.end()] + "\n" + line + text[header.end():]
    start = header.end() + key.start()
    opening = header.end() + key.end()
    if text[opening:opening + 1] != "[":
        raise ValueError("exclude_commands is not an inline array")
    return text[:start] + line + text[array_end(text, opening):]


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in ("add", "remove"):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2

    path = config_path()
    if path is None:
        # No rtk left to configure, which on remove is the expected case.
        return 0 if action == "remove" else 1

    text = path.read_text() if path.exists() else ""
    current = tomllib.loads(text).get("hooks", {}).get("exclude_commands", [])
    if action == "add":
        wanted = current + [p for p in PATTERNS if p not in current]
    else:
        wanted = [p for p in current if p not in PATTERNS]
    if wanted == current:
        return 0

    updated = with_excludes(text, wanted)
    # Written only when the result parses back to exactly what was meant.
    if tomllib.loads(updated).get("hooks", {}).get("exclude_commands") != wanted:
        raise SystemExit(f"rtk-excludes: could not edit {path} safely; left it unchanged")

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".config.toml.")
    with os.fdopen(handle, "w") as out:
        out.write(updated)
    if path.exists():
        os.chmod(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
