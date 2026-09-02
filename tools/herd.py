#!/usr/bin/env python3
"""Run other Claude sessions from this one, over Herdr.

    herd                      what is running
    herd on <repo> [brief]    start work on a repo, cloning it if it is not here
    herd verify <who>         run what that repo checks itself with
    herd land <who>           push what it committed and open a pull request
    herd tidy                 remove the worktrees nobody is in
    herd done <who> [note]    close this session, having handed the work on
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
import time

FUZZY = 0.6
NAME = "abcdefghijklmnopqrstuvwxyz0123456789_-"
ASCII_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
WORKSPACE = os.path.expanduser("~/Workspace")
WORKTREES = os.path.expanduser("~/.herdr/worktrees")
EVENTS = os.path.expanduser("~/.herdr/events.jsonl")


def herdr(*command: str) -> dict:
    """A Herdr API call, as the `result` it answers with."""
    done = subprocess.run(["herdr", *command], capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise SystemExit((done.stderr or done.stdout).strip() or f"herdr {' '.join(command)} failed")
    try:
        return json.loads(done.stdout)["result"]
    except (ValueError, KeyError):
        return {}


def claude(*command: str) -> str:
    """A `claude` CLI call, as the text it printed."""
    done = subprocess.run(["claude", *command], capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise SystemExit((done.stderr or done.stdout).strip() or f"claude {' '.join(command)} failed")
    return done.stdout


def git(where: str, *command: str) -> str:
    done = subprocess.run(["git", "-C", where, *command], capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise SystemExit((done.stderr or done.stdout).strip() or f"git {' '.join(command)} failed")
    return done.stdout.strip()


def gh(*command: str, where: str = None) -> str:
    done = subprocess.run(["gh", *command], capture_output=True, text=True, timeout=120, cwd=where)
    return done.stdout.strip() if done.returncode == 0 else ""


def base_of(where: str) -> str:
    """What the remote calls its default branch, as origin/<name>.

    `land` wants this one, opening its pull request against the remote."""
    head = git(where, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    return (head or "refs/remotes/origin/main").replace("refs/remotes/", "")


def landed_in(where: str) -> str:
    """Where a finished worktree's commits have to be for it to be finished.

    The local default branch where there is one, and the remote's otherwise.
    `tidy` asked for `origin/main` and every brief here says not to push, so a
    session that landed by fast-forwarding a local `main` stayed "unmerged" for
    ever and nothing was ever tidyable.

    Removing on the local test loses no commit: a worktree carries none of its
    own, and `tidy` never deletes a branch."""
    remote = base_of(where)
    local = remote.rsplit("/", 1)[-1]
    try:
        git(where, "rev-parse", "--verify", f"refs/heads/{local}")
        return local
    except SystemExit:
        return remote


def owners() -> list:
    """You, then every organisation you belong to."""
    me = gh("api", "user", "--jq", ".login")
    if not me:
        raise SystemExit("gh is not logged in, so no repo can be found. gh auth login")
    return [me] + [o for o in gh("api", "user/orgs", "--jq", ".[].login").splitlines() if o]


def find(repo: str) -> str:
    """The one repo someone meant, as owner/name.

    Your own account answers first, because it nearly always has it. The wider
    search is for what an organisation owns, and two matches refuse rather than
    clone the wrong one."""
    accounts = owners()
    for owner in accounts:
        if gh("repo", "view", f"{owner}/{repo}", "--json", "name", "--jq", ".name"):
            return f"{owner}/{repo}"

    found = [
        line
        for owner in accounts
        for line in gh("search", "repos", repo, "--owner", owner, "--limit", "5",
                       "--json", "fullName", "--jq", ".[].fullName").splitlines()
    ]
    if len(found) == 1:
        return found[0]
    if found:
        raise SystemExit(
            f'"{repo}" matches {len(found)}:\n' + "\n".join("  " + f for f in found)
            + "\nname one as owner/repo."
        )
    raise SystemExit(f'no repo called "{repo}" under {", ".join(accounts)}')


def checkout(repo: str) -> str:
    """The repo on disk under ~/Workspace, cloned from your account if absent."""
    where = os.path.join(WORKSPACE, os.path.basename(repo))
    if os.path.isdir(os.path.join(where, ".git")):
        git(where, "fetch", "origin", "--prune")
        return where

    full = repo if "/" in repo else find(repo)
    where = os.path.join(WORKSPACE, full.split("/")[-1])
    if not os.path.isdir(os.path.join(where, ".git")):
        os.makedirs(WORKSPACE, exist_ok=True)
        done = subprocess.run(["gh", "repo", "clone", full, where],
                              capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise SystemExit((done.stderr or done.stdout).strip() or f"cloning {full} failed")
    return where


def worktree(where: str, name: str, branch: str = "") -> str:
    """A checkout of its own, cut from where this one actually is.

    Not from the remote's default branch. A session hands over from the branch
    it is on, and a worktree cut from a stale main starts the successor without
    the work that produced it.

    A worktree carries commits and nothing else, so an uncommitted file would
    not travel. Rather than start the successor from a state its predecessor
    cannot see, this refuses and names the files."""
    path = os.path.join(WORKTREES, os.path.basename(where), name)
    if os.path.isdir(path):
        return path

    changed = [line for line in git(where, "status", "--porcelain").splitlines()
               if not line.startswith("??")]
    if changed:
        raise SystemExit(
            f"a worktree carries commits, so these would not reach {name}:\n"
            + "\n".join("  " + line for line in changed)
            + "\ncommit them first."
        )
    # The commit rather than the branch name, because a branch already checked
    # out here cannot be checked out again in the new worktree.
    base = git(where, "rev-parse", "HEAD")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    branch = branch or f"work/{name}"
    known = git(where, "branch", "--list", branch)
    git(where, "worktree", "add", path, *([branch] if known else ["-b", branch, base]))
    return path


def inside() -> None:
    if os.environ.get("HERDR_ENV") != "1":
        raise SystemExit("not inside Herdr, so there is nowhere to start a session")


class Session:
    def __init__(self, row: dict):
        self.name = row.get("name") or ""
        self.pane = row.get("pane_id") or ""
        self.tab = row.get("tab_id") or ""
        self.workspace = row.get("workspace_id") or ""
        self.status = row.get("agent_status") or "unknown"
        self.doing = row.get("terminal_title_stripped") or ""
        self.cwd = row.get("cwd") or ""
        self.id = ""
        self.kind = "pane"

    @property
    def label(self) -> str:
        return self.name or self.pane

    @property
    def keys(self) -> list:
        return [k for k in (self.name, self.pane, self.tab, self.doing, self.cwd) if k]

    def line(self) -> str:
        mark = {"working": "·", "idle": "✓", "done": "✓", "blocked": "!", "unknown": "?"}
        where = self.cwd.replace(os.path.expanduser("~"), "~")
        tag = "bg " if self.kind == "bg" else ""
        # A name wider than the column pushes every line after it out of
        # alignment, and the screen this is read on is a phone.
        label = self.label if len(self.label) <= 22 else self.label[:21] + "…"
        return f"{mark.get(self.status, '?')} {label:22s} {self.status:8s} {tag}{self.doing or where}"


class Background(Session):
    """A `claude --bg` session. It owns no pane, so herdr cannot see it at all,
    and the only listing it appears in is `claude agents --json`."""

    def __init__(self, row: dict):
        super().__init__({})
        self.kind = "bg"
        self.id = row.get("id") or ""
        self.name = row.get("name") or ""
        self.cwd = row.get("cwd") or ""
        self.status = "working" if row.get("status") == "busy" else "idle"

    @property
    def label(self) -> str:
        return self.name or self.id

    @property
    def keys(self) -> list:
        return [k for k in (self.name, self.id, self.cwd) if k]


def panes() -> list:
    """The sessions herdr is running, minus the one asking."""
    if os.environ.get("HERDR_ENV") != "1":
        return []
    mine = os.environ.get("HERDR_PANE_ID")
    return [Session(row) for row in herdr("agent", "list").get("agents", []) if row.get("pane_id") != mine]


def detached() -> list:
    """The `claude --bg` sessions, which have no pane for herdr to list.

    Their interactive siblings are the panes above under a different name, so
    listing those too would show every session twice."""
    try:
        rows = json.loads(claude("agents", "--json"))
    except (OSError, ValueError, SystemExit, subprocess.SubprocessError):
        return []
    mine = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return [
        Background(row)
        for row in rows
        if row.get("kind") == "background" and row.get("sessionId") != mine
    ]


def sessions() -> list:
    return panes() + detached()


def events(after: int = 0) -> tuple:
    """What the hooks recorded past `after`, and where the file now ends.

    A session with no pane cannot be waited on, and one that blocks says so
    through its Notification hook long before a poll would notice. Missing file
    means the hook is not installed, which is not an error: everything here
    falls back to waiting."""
    try:
        size = os.path.getsize(EVENTS)
    except OSError:
        return [], 0
    if size <= after:
        return [], size

    seen = []
    with open(EVENTS) as recorded:
        recorded.seek(after)
        for line in recorded.read().splitlines():
            try:
                seen.append(json.loads(line))
            except ValueError:
                continue  # A line still being written is not a broken log.
    return seen, size


def record(event: dict) -> None:
    """Put one event in the log, where it outlives the pane that wrote it."""
    try:
        os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
        with open(EVENTS, "a") as events:
            events.write(json.dumps({"at": time.time(), **event}) + "\n")
    except OSError:
        pass


def show_events(args) -> None:
    seen, _ = events()
    if not seen:
        raise SystemExit(f"nothing recorded in {EVENTS.replace(os.path.expanduser('~'), '~')}")
    for event in seen[-args.lines :]:
        when = time.strftime("%H:%M:%S", time.localtime(event.get("at", 0)))
        where = str(event.get("cwd", "")).replace(os.path.expanduser("~"), "~")
        what = event.get("notification_type") or event.get("hook_event_name") or "?"
        print(f"{when}  {what:18s} {where}  {event.get('message', '')}".rstrip())


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

    # `--worktree` takes an optional branch, so `--worktree brief.md` binds the
    # brief to it and the session starts with nothing to do. It printed "give
    # it something to do" and looked like a session that had simply not been
    # told, which is a whole handover lost quietly.
    #
    # Neither of the two shapes below is a branch anybody meant, so each is
    # refused with the line that would have worked. `--branch` is the spelling
    # with no ambiguity in it and is what a script should use.
    if isinstance(args.worktree, str):
        if not args.brief and os.path.isfile(os.path.expanduser(args.worktree)):
            raise SystemExit(
                f"--worktree took `{args.worktree}` as a branch name and it is a file.\n"
                f"the brief goes after the name:\n"
                f"  herd start {args.name} {args.worktree} --worktree")
        if args.repo:
            raise SystemExit(
                f"--repo makes the worktree itself, so --worktree {args.worktree} "
                f"would be ignored.\nuse --branch to name the branch, or drop it.")
    if getattr(args, "branch", None):
        args.worktree = args.branch

    brief = ""
    if args.brief:
        try:
            brief = open(os.path.expanduser(args.brief)).read()
        except OSError as problem:
            raise SystemExit(str(problem))
        if not brief.strip():
            raise SystemExit("the brief is empty")

    if args.repo:
        where = worktree(checkout(args.repo), args.name,
                         getattr(args, "branch", None))
    else:
        where = os.path.abspath(args.cwd or os.getcwd())
    if args.worktree and not args.repo:
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
        # A --repo session arrives with a checkout of its own already, so this
        # is a tab in it rather than a worktree of a worktree.
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

    # One wait after another means the first slow session hides every later one
    # that already stopped, so the whole answer arrives when the slowest does.
    # herdr has no pane to wait on for a background session, so it is reported
    # with whatever status it holds rather than waited for.
    waits = {
        s.label: subprocess.Popen(
            ["herdr", "agent", "wait", s.label, "--until", "idle", "--until", "done",
             "--until", "blocked", "--timeout", str(args.timeout)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for s in live
        if s.kind != "bg"
    }
    # A background session has no pane to wait on, so it is watched through
    # what its hooks record instead.
    detached_homes = {s.cwd for s in live if s.kind == "bg" and s.cwd}
    _, mark = events()
    deadline = time.time() + args.timeout / 1000

    def stop_waiting() -> None:
        for running in waits.values():
            running.terminate()
        waits.clear()
        detached_homes.clear()

    while (waits or detached_homes) and time.time() < deadline:
        for label, running in list(waits.items()):
            if running.poll() is None:
                continue
            del waits[label]
            if args.first:
                stop_waiting()

        fresh, mark = events(mark)
        for event in fresh:
            if event.get("cwd") in detached_homes:
                detached_homes.discard(event["cwd"])
                if args.first:
                    stop_waiting()

        if waits or detached_homes:
            time.sleep(0.5)

    names = {s.label for s in live}
    after = [s for s in sessions() if s.label in names]
    show(after)
    blocked = [s.label for s in after if s.status == "blocked"]
    if blocked:
        print(f"\nwaiting on you: {', '.join(blocked)}")
        print(f"  herd read {blocked[0]}   to see what it is asking")


def land(args) -> None:
    """Push what a session committed and open a pull request for it."""
    session = resolve(args.who)
    where = session.cwd
    branch = git(where, "rev-parse", "--abbrev-ref", "HEAD")
    base = base_of(where)
    if branch in ("HEAD", base.split("/")[-1]):
        raise SystemExit(f"{session.label} is on {branch}, which is not a branch to open one from")

    git(where, "fetch", "origin", "--prune")
    commits = git(where, "log", "--oneline", f"{base}..HEAD")
    if not commits:
        raise SystemExit(f"{session.label} has committed nothing on {branch}")

    dirty = git(where, "status", "--porcelain")
    if dirty:
        # A push carries commits and nothing else, so this would leave the rest
        # behind in a checkout nobody looks at again.
        raise SystemExit(
            f"{branch} has uncommitted work a push would leave behind:\n"
            + "\n".join("  " + line for line in dirty.splitlines())
            + "\ncommit it, or tell the session to."
        )

    if not args.yes:
        print(f"would push {branch} and open a pull request against {base}:")
        print("\n".join("  " + line for line in commits.splitlines()))
        print("\nrun again with --yes.")
        return

    git(where, "push", "--set-upstream", "origin", branch)
    url = gh("pr", "create", "--head", branch, "--base", base.split("/")[-1], "--fill", where=where)
    print(url or f"pushed {branch}, but opening the pull request failed")


def runner_of(where: str) -> str:
    """What runs a script here.

    The lockfile sits at the root of a workspace and the package being checked
    is usually a directory or two under it, so this walks up rather than
    calling every monorepo package an npm one."""
    locks = {"bun.lock": "bun", "bun.lockb": "bun", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn"}
    path = os.path.abspath(where)
    while True:
        for lock, runner in locks.items():
            if os.path.isfile(os.path.join(path, lock)):
                return runner
        parent = os.path.dirname(path)
        if parent == path:
            return "npm"
        path = parent


def bar(where: str) -> list:
    """The command this repo checks itself with, or nothing if it has none."""
    justfile = os.path.join(where, "justfile")
    if os.path.isfile(justfile) and "\nready" in open(justfile).read():
        return ["just", "ready"]

    package = os.path.join(where, "package.json")
    if os.path.isfile(package):
        try:
            scripts = json.load(open(package)).get("scripts", {})
        except ValueError:
            scripts = {}
        runner = runner_of(where)
        for name in ("ready", "verify", "ci", "check", "test"):
            if name in scripts:
                return [runner, "run", name]

    if os.path.isfile(os.path.join(where, "Cargo.toml")):
        return ["cargo", "test"]
    return []


def verify(args) -> None:
    session = resolve(args.who)
    where = session.cwd
    command = args.command or bar(where)
    if not command:
        raise SystemExit(f"nothing in {where} says how it verifies. Pass the command after --")

    done = subprocess.run(command, cwd=where, capture_output=True, text=True)
    said = " ".join(command)
    # The exit code is the verdict. A grep over the output is not, because a
    # pipe hides a failure behind the exit code of the grep.
    if done.returncode == 0:
        print(f"{session.label}: {said} passed")
        return
    print(f"{session.label}: {said} failed ({done.returncode})\n")
    print("\n".join((done.stdout + done.stderr).strip().splitlines()[-args.lines :]))
    raise SystemExit(done.returncode)


def tidy(args) -> None:
    """The worktrees no session is in any more.

    Removes only what it can prove is finished with: nothing uncommitted, and
    nothing committed that the default branch does not already have. Anything
    else is someone's work and is listed rather than touched.

    The default branch is the **local** one where there is one; see
    `landed_in` for why the remote's was the wrong question."""
    busy = {s.cwd for s in sessions()}
    spent, held = [], []
    for repo in sorted(os.listdir(WORKTREES)) if os.path.isdir(WORKTREES) else []:
        for name in sorted(os.listdir(os.path.join(WORKTREES, repo))):
            path = os.path.join(WORKTREES, repo, name)
            if path in busy or not os.path.isdir(path):
                continue
            try:
                keeping = git(path, "status", "--porcelain").splitlines()
                keeping += git(path, "log", "--oneline", f"{landed_in(path)}..HEAD").splitlines()
            except SystemExit:
                continue  # Not a worktree of ours, so not ours to remove.
            (held if keeping else spent).append((path, keeping))

    for path, keeping in held:
        print(f"! {path.replace(os.path.expanduser('~'), '~')}  {len(keeping)} unmerged or uncommitted")
    if not spent:
        print("nothing to tidy" if not held else "\nnothing safe to remove")
        return
    for path, _ in spent:
        print(f"{'removed' if args.yes else 'would remove'} {path.replace(os.path.expanduser('~'), '~')}")
        if args.yes:
            main = os.path.dirname(os.path.abspath(git(path, "rev-parse", "--git-common-dir")))
            git(main, "worktree", "remove", path)
    if not args.yes:
        print("\nrun again with --yes. Branches are left alone either way.")


def tell(args) -> None:
    session = resolve(args.who)
    if session.kind == "bg":
        raise SystemExit(
            f"{session.label} runs in the background and takes no follow-up.\n"
            f"  claude attach {session.id}   to pick it up in this terminal"
        )
    herdr("agent", "prompt", session.label, " ".join(args.text))
    print(f"sent to {session.label}")


def plain(text: str) -> str:
    """Terminal output as the words it drew.

    `claude logs` replays what the screen received, which is mostly cursor
    moves: dropping them outright runs the words together, because the spacing
    between two columns *is* the escape. So the moves are played back onto a
    line instead."""
    out = []
    for raw in text.splitlines():
        line, column, index = [], 0, 0
        while index < len(raw):
            char = raw[index]
            if char == "\x1b" and raw[index + 1 : index + 2] == "[":
                end = index + 2
                while end < len(raw) and raw[end] not in ASCII_LETTERS:
                    end += 1
                digits = "".join(c for c in raw[index + 2 : end] if c.isdigit() or c == ";")
                first = int(digits.split(";")[0] or 1) if digits.split(";")[0] else 1
                verb = raw[end : end + 1]
                if verb == "G":
                    column = max(first - 1, 0)
                elif verb == "C":
                    column += first
                elif verb == "K":
                    del line[column:]
                index = end + 1
                continue
            if char == "\r":
                column, index = 0, index + 1
                continue
            line.extend(" " * (column - len(line)))
            if column < len(line):
                line[column] = char
            else:
                line.append(char)
            column += 1
            index += 1
        out.append("".join(line).rstrip())
    return "\n".join(out)


def transcript(session: Session) -> list:
    """What a session has said, without the interface drawn around it."""
    if session.kind == "bg":
        text = plain(claude("logs", session.id))
    else:
        done = subprocess.run(["herdr", "agent", "read", session.label], capture_output=True, text=True)
        text = done.stdout
        try:
            payload = json.loads(text)["result"]
            text = payload.get("output") or payload.get("text") or text
        except (ValueError, KeyError, TypeError):
            pass
    # The pane holds the agent's words and the chrome around them. On a phone
    # the chrome is most of the screen, so it goes.
    chrome = ("─", "╭", "╰", "│", "❯", "⏵", "\ue0b0", "\uf07b", "\uf1d3")
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(chrome)
    ]


def read(args) -> None:
    session = resolve(args.who)
    print(f"{session.line()}\n")
    print("\n".join(transcript(session)[-args.lines :]))


def stop(args) -> None:
    session = resolve(args.who)
    if not args.yes:
        print("would stop:")
        print("  " + session.line())
        print("\nrun again with --yes.")
        return
    if session.kind == "bg":
        claude("stop", session.id)
    elif session.tab:
        herdr("tab", "close", session.tab)
    else:
        herdr("pane", "close", session.pane)
    print(f"stopped {session.label}")


def done(args) -> None:
    """Close this session, once the work has demonstrably moved to another one.

    A session's own conversation is the only record of what it handed over and
    why, and closing the pane ends it. So the work has to be somewhere else
    first: a successor that is running and has already spoken, no modified file
    left behind unexplained, and the handover written to the event log, which
    outlives the pane."""
    mine = os.environ.get("HERDR_PANE_ID")
    if not mine:
        raise SystemExit("not running in a Herdr pane, so there is nothing to close")

    # resolve() never returns the caller, so this cannot name itself.
    successor = resolve(args.to)
    if not transcript(successor):
        raise SystemExit(
            f"{successor.label} has not said anything yet, so the work has not moved.\n"
            f"  herd tell {successor.label} '…'   and wait for it to start"
        )

    here = os.getcwd()
    try:
        changed = [line for line in git(here, "status", "--porcelain").splitlines()
                   if not line.startswith("??")]
    except SystemExit:
        changed = []  # Not a checkout, so there is nothing to have left behind.
    if changed:
        raise SystemExit(
            "these are modified and nothing would be left to explain them:\n"
            + "\n".join("  " + line for line in changed)
            + "\ncommit them first."
        )

    handover = {
        "hook_event_name": "Handover",
        "to": successor.label,
        "cwd": here,
        "pane": mine,
        "message": args.note or "",
    }
    if not args.yes:
        print(f"would hand over to {successor.label} and close this pane:")
        print("  " + successor.line())
        if args.note:
            print(f"  note: {args.note}")
        print("\nrun again with --yes.")
        return

    record(handover)
    print(f"handed over to {successor.label}, closing this pane")
    herdr("pane", "close", mine)


def main() -> int:
    parser = argparse.ArgumentParser(prog="herd", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    begin = sub.add_parser("start", help="start a session")
    begin.add_argument("name")
    begin.add_argument("brief", nargs="?", help="a file holding what it should do")
    begin.add_argument("--worktree", nargs="?", const=True, metavar="BRANCH",
                       help="give it a git worktree of its own")
    # The unambiguous spelling of the same thing. `--worktree`'s optional value
    # swallows the brief that follows it, which is a mistake with no symptom.
    begin.add_argument("--branch", help="what to call its branch")
    begin.add_argument("--cwd")
    begin.add_argument("--repo", help="a repo under ~/Workspace, cloned from your account if absent")
    begin.set_defaults(run=start)

    onto = sub.add_parser("on", help="start work on a repo")
    onto.add_argument("repo")
    onto.add_argument("brief", nargs="?", help="a file holding what it should do")
    onto.add_argument("--name", help="what to call the session (default: the repo)")
    onto.add_argument("--branch", help="what to call its branch")
    onto.set_defaults(run=lambda a: start(argparse.Namespace(
        name=a.name or "".join(c if c in NAME else "-" for c in os.path.basename(a.repo).lower()),
        brief=a.brief, worktree=False, branch=a.branch, cwd=None, repo=a.repo,
    )))

    waiting = sub.add_parser("watch", help="block until they stop working")
    waiting.add_argument("who", nargs="*")
    waiting.add_argument("--timeout", type=int, default=1800000)
    waiting.add_argument("--first", action="store_true", help="answer as soon as one stops")
    waiting.set_defaults(run=watch)

    landing = sub.add_parser("land", help="push what one committed and open a pull request")
    landing.add_argument("who")
    landing.add_argument("--yes", "-y", action="store_true")
    landing.set_defaults(run=land)

    checking = sub.add_parser("verify", help="run what the repo checks itself with")
    checking.add_argument("who")
    checking.add_argument("command", nargs="*", help="the command, if the repo does not say")
    checking.add_argument("--lines", type=int, default=25)
    checking.set_defaults(run=verify)

    finished = sub.add_parser("done", help="close this session, having handed the work on")
    finished.add_argument("to", help="the session the work moved to")
    finished.add_argument("note", nargs="?", help="what the next person should know")
    finished.add_argument("--yes", "-y", action="store_true")
    finished.set_defaults(run=done)

    recorded = sub.add_parser("events", help="what the hooks recorded")
    recorded.add_argument("--lines", type=int, default=20)
    recorded.set_defaults(run=show_events)

    tidying = sub.add_parser("tidy", help="remove worktrees no session is in")
    tidying.add_argument("--yes", "-y", action="store_true")
    tidying.set_defaults(run=tidy)

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
