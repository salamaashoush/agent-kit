#!/usr/bin/env python3
"""Run other Claude sessions from this one, over Herdr.

    herd                      what is running
    herd start <name> …       start a session, optionally in its own worktree
    herd watch [name …]       block until they stop working, then say what happened
    herd tell <who> <text>    send a follow-up
    herd read <who>           the tail of what one said
    herd stop <who>           stop one

Written for a phone: every command answers in a few lines, `who` is whatever
you remember of a session rather than its exact name, and anything that
destroys work asks first.
"""

import argparse
import difflib
import json
import os
import subprocess
import sys

FUZZY = 0.6
NAME = "abcdefghijklmnopqrstuvwxyz0123456789_-"


def herdr(*command: str) -> dict:
    """A Herdr API call, as the `result` it answers with."""
    done = subprocess.run(["herdr", *command], capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise SystemExit((done.stderr or done.stdout).strip() or f"herdr {' '.join(command)} failed")
    try:
        return json.loads(done.stdout)["result"]
    except (ValueError, KeyError):
        return {}


def inside() -> None:
    if os.environ.get("HERDR_ENV") != "1":
        raise SystemExit("not inside Herdr, so there are no sessions to run")


class Session:
    def __init__(self, row: dict):
        self.name = row.get("name") or ""
        self.pane = row.get("pane_id") or ""
        self.tab = row.get("tab_id") or ""
        self.workspace = row.get("workspace_id") or ""
        self.status = row.get("agent_status") or "unknown"
        self.doing = row.get("terminal_title_stripped") or ""
        self.cwd = row.get("cwd") or ""

    @property
    def label(self) -> str:
        return self.name or self.pane

    @property
    def keys(self) -> list:
        return [k for k in (self.name, self.pane, self.tab, self.doing, self.cwd) if k]

    def line(self) -> str:
        mark = {"working": "·", "idle": "✓", "done": "✓", "blocked": "!", "unknown": "?"}
        where = self.cwd.replace(os.path.expanduser("~"), "~")
        return f"{mark.get(self.status, '?')} {self.label:22s} {self.status:8s} {self.doing or where}"


def sessions() -> list:
    inside()
    mine = os.environ.get("HERDR_PANE_ID")
    return [Session(row) for row in herdr("agent", "list").get("agents", []) if row.get("pane_id") != mine]


def resolve(query: str) -> Session:
    """The one session someone meant, or an error naming the choices.

    Generous in finding and strict in acting: a name, part of one, a
    misspelling and a few words of what a session is doing all land, but two
    matches stop rather than guess, because the cost of the wrong one is its
    whole conversation."""
    live = sessions()
    if not live:
        raise SystemExit("nothing is running")

    lowered = query.lower().strip()
    for pick in (
        [s for s in live if any(lowered == k.lower() for k in s.keys)],
        [s for s in live if any(lowered in k.lower() for k in s.keys)],
    ):
        if len(pick) == 1:
            return pick[0]
        if pick:
            raise SystemExit(
                f'"{query}" matches {len(pick)}:\n'
                + "\n".join("  " + s.line() for s in pick)
                + "\nname one exactly."
            )

    scored = sorted(
        (
            (max(difflib.SequenceMatcher(None, lowered, k.lower()).ratio() for k in s.keys), s)
            for s in live
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if scored and scored[0][0] >= FUZZY:
        return scored[0][1]

    raise SystemExit(
        f'nothing matches "{query}". Running now:\n' + "\n".join("  " + s.line() for s in live)
    )


def show(live: list) -> None:
    if not live:
        print("nothing running")
        return
    for session in live:
        print(session.line())


def start(args) -> None:
    inside()
    if not args.name or set(args.name) - set(NAME) or args.name[0] not in NAME[:26]:
        raise SystemExit(f'"{args.name}" is not a name: lowercase, starts with a letter')
    if any(s.name == args.name for s in sessions()):
        raise SystemExit(f'"{args.name}" is already running')

    brief = ""
    if args.brief:
        try:
            brief = open(args.brief).read()
        except OSError as problem:
            raise SystemExit(str(problem))
        if not brief.strip():
            raise SystemExit("the brief is empty")

    where = os.path.abspath(args.cwd or os.getcwd())
    if args.worktree:
        # A worktree per session, because two sessions in one checkout edit the
        # same files, build over each other, and commit each other's work.
        made = herdr(
            "worktree", "create", "--cwd", where,
            "--branch", args.worktree if isinstance(args.worktree, str) else f"work/{args.name}",
            "--label", args.name, "--no-focus",
        )
        pane = made["root_pane"]["pane_id"]
        where = made["root_pane"]["cwd"]
    else:
        made = herdr("tab", "create", "--cwd", where, "--label", args.name, "--no-focus")
        pane = made["root_pane"]["pane_id"]

    herdr("agent", "start", args.name, "--kind", "claude", "--pane", pane,
          "--", "--remote-control", args.name)
    if brief:
        herdr("agent", "prompt", args.name, brief)

    print(f"{args.name} started in {where.replace(os.path.expanduser('~'), '~')}")
    if not brief:
        print(f"  herd tell {args.name} '…'   to give it something to do")


def watch(args) -> None:
    live = [resolve(q) for q in args.who] if args.who else sessions()
    if not live:
        raise SystemExit("nothing is running")

    for session in live:
        try:
            herdr("agent", "wait", session.label, "--until", "idle", "--until", "done",
                  "--until", "blocked", "--timeout", str(args.timeout))
        except SystemExit:
            pass  # A timeout is an answer too; the status below is the truth.

    names = {s.label for s in live}
    after = [s for s in sessions() if s.label in names]
    show(after)
    blocked = [s.label for s in after if s.status == "blocked"]
    if blocked:
        print(f"\nwaiting on you: {', '.join(blocked)}")
        print(f"  herd read {blocked[0]}   to see what it is asking")


def tell(args) -> None:
    session = resolve(args.who)
    herdr("agent", "prompt", session.label, " ".join(args.text))
    print(f"sent to {session.label}")


def read(args) -> None:
    session = resolve(args.who)
    done = subprocess.run(["herdr", "agent", "read", session.label], capture_output=True, text=True)
    text = done.stdout
    try:
        payload = json.loads(text)["result"]
        text = payload.get("output") or payload.get("text") or text
    except (ValueError, KeyError, TypeError):
        pass
    # The pane holds the agent's words and the interface drawn around them.
    # On a phone the chrome is most of the screen, so it goes.
    chrome = ("─", "╭", "╰", "│", "❯", "⏵", "\ue0b0", "\uf07b", "\uf1d3")
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(chrome)
    ]
    print(f"{session.line()}\n")
    print("\n".join(lines[-args.lines :]))


def stop(args) -> None:
    session = resolve(args.who)
    if not args.yes:
        print("would stop:")
        print("  " + session.line())
        print("\nrun again with --yes.")
        return
    if session.tab:
        herdr("tab", "close", session.tab)
    else:
        herdr("pane", "close", session.pane)
    print(f"stopped {session.label}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="herd", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    begin = sub.add_parser("start", help="start a session")
    begin.add_argument("name")
    begin.add_argument("brief", nargs="?", help="a file holding what it should do")
    begin.add_argument("--worktree", nargs="?", const=True, metavar="BRANCH",
                       help="give it a git worktree of its own")
    begin.add_argument("--cwd")
    begin.set_defaults(run=start)

    waiting = sub.add_parser("watch", help="block until they stop working")
    waiting.add_argument("who", nargs="*")
    waiting.add_argument("--timeout", type=int, default=1800000)
    waiting.set_defaults(run=watch)

    saying = sub.add_parser("tell", help="send a follow-up")
    saying.add_argument("who")
    saying.add_argument("text", nargs="+")
    saying.set_defaults(run=tell)

    reading = sub.add_parser("read", help="the tail of what one said")
    reading.add_argument("who")
    reading.add_argument("--lines", type=int, default=25)
    reading.set_defaults(run=read)

    stopping = sub.add_parser("stop", help="stop one")
    stopping.add_argument("who")
    stopping.add_argument("--yes", "-y", action="store_true")
    stopping.set_defaults(run=stop)

    sub.add_parser("list", help="what is running").set_defaults(run=lambda _: show(sessions()))

    args = parser.parse_args()
    if not args.command:
        show(sessions())
        return 0
    args.run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
