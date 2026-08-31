#!/usr/bin/env python3
"""Stop the session someone described, or refuse and say why.

    handover-stop.py                 what is running
    handover-stop.py <query>         what it would stop, and the command
    handover-stop.py <query> --yes   stop it

The query is whatever the person said: a name, part of one, a misspelling, a
directory, or a few words of what the session is working on. Killing the wrong
session costs its whole conversation, so this acts only when exactly one thing
matches, and never on the session it is called from.
"""

import difflib
import json
import os
import subprocess
import sys

FUZZY = 0.6


def run(*command: str) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


class Target:
    def __init__(self, kind: str, label: str, doing: str, where: str, keys: list, stop: list):
        self.kind = kind
        self.label = label
        self.doing = doing
        self.where = where
        # Every string this target answers to, matched longest first.
        self.keys = [k for k in keys if k]
        self.stop = stop

    def __str__(self) -> str:
        doing = f"  {self.doing}" if self.doing else ""
        return f"  {self.kind:6s} {self.label:24s} {self.where}{doing}"


def herdr_targets() -> list:
    if os.environ.get("HERDR_ENV") != "1":
        return []
    try:
        agents = json.loads(run("herdr", "agent", "list") or "{}")["result"]["agents"]
    except (ValueError, KeyError):
        return []

    mine = os.environ.get("HERDR_PANE_ID")
    out = []
    for agent in agents:
        pane = agent.get("pane_id")
        if pane == mine:
            continue
        name = agent.get("name") or ""
        title = agent.get("terminal_title_stripped") or ""
        tab = agent.get("tab_id")
        out.append(
            Target(
                kind="herdr",
                label=name or pane or "?",
                doing=title,
                where=agent.get("cwd") or "",
                keys=[name, pane, tab, title, agent.get("cwd")],
                stop=["herdr", "tab", "close", tab] if tab else ["herdr", "pane", "close", pane],
            )
        )
    return out


def claude_targets() -> list:
    try:
        rows = json.loads(run("claude", "agents", "--json") or "[]")
    except ValueError:
        return []

    mine = os.environ.get("CLAUDE_CODE_SESSION_ID")
    out = []
    for row in rows:
        session = row.get("sessionId") or ""
        short = row.get("id") or ""
        if mine and (session == mine or (short and mine.startswith(short))):
            continue
        # An interactive session is somebody's terminal; `claude stop` is for
        # the backgrounded ones, and there is nothing to stop about the rest.
        if not short:
            continue
        out.append(
            Target(
                kind="bg",
                label=row.get("name") or short,
                doing=f"({row.get('status', '?')})",
                where=row.get("cwd") or "",
                keys=[row.get("name"), short, session, row.get("cwd")],
                stop=["claude", "stop", short],
            )
        )
    return out


def matches(query: str, targets: list) -> list:
    lowered = query.lower().strip()
    if not lowered:
        return []

    exact = [t for t in targets if any(lowered == k.lower() for k in t.keys)]
    if exact:
        return exact

    part = [t for t in targets if any(lowered in k.lower() for k in t.keys)]
    if part:
        return part

    # A misspelling: the closest key on each target, kept if it is close enough.
    scored = []
    for target in targets:
        best = max(
            (difflib.SequenceMatcher(None, lowered, k.lower()).ratio() for k in target.keys),
            default=0.0,
        )
        if best >= FUZZY:
            scored.append((best, target))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [target for _, target in scored]


def main() -> int:
    arguments = [a for a in sys.argv[1:] if a not in ("--yes", "-y")]
    confirmed = len(arguments) != len(sys.argv[1:])
    query = " ".join(arguments)

    targets = herdr_targets() + claude_targets()
    if not targets:
        print("nothing running that this can stop")
        return 1

    if not query:
        print("running now, this session excluded:")
        for target in targets:
            print(target)
        print("\nname one to stop it.")
        return 0

    found = matches(query, targets)

    if not found:
        print(f'nothing matches "{query}". Running now:')
        for target in targets:
            print(target)
        return 1

    if len(found) > 1:
        print(f'"{query}" matches {len(found)} of them, so nothing was stopped:')
        for target in found:
            print(target)
        print("\nname one exactly.")
        return 1

    target = found[0]
    if not confirmed:
        print("would stop:")
        print(target)
        print(f"\n  {' '.join(target.stop)}\n\nrun again with --yes.")
        return 0

    print("stopping:")
    print(target)
    result = subprocess.run(target.stop, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    print(f"stopped {target.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
