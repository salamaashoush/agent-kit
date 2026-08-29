#!/usr/bin/env python3
"""Install this repo into ~/.claude.

    ./install.sh              symlink, merge settings, wire the tools present
    ./install.sh --dry-run    print the diff, change nothing
    ./install.sh --doctor     report what is wired and what is missing
    ./install.sh --uninstall  undo, restoring the settings values it replaced

Instructions and skills install by symlink, so editing a file here changes what
the agent reads immediately. Settings are different: `~/.claude/settings.json`
holds credentials and per-machine config that must never reach a remote, so the
installer merges in the managed slice named by `config/` and records what it
touched in a state file, which is what makes a re-run idempotent and an
uninstall able to put the old values back.
"""

import argparse
import difflib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tomllib
from datetime import date

REPO = pathlib.Path(__file__).resolve().parent.parent
CLAUDE = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
SETTINGS = CLAUDE / "settings.json"
STATE = CLAUDE / "agent-kit.state.json"
TOOLS_LOCAL = REPO / "tools.local.md"

MISSING = object()


# --- reading what is configured ------------------------------------------------

def registry() -> dict:
    return tomllib.loads((REPO / "config" / "tools.toml").read_text())


def preferences() -> dict:
    return json.loads((REPO / "config" / "preferences.json").read_text())


def state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def located(tool: dict):
    """Where the tool's binary is, or None. A tool with no probe ships here."""
    probe = tool.get("probe")
    if not probe:
        return str(REPO)
    return shutil.which(probe)


def plan() -> dict:
    """Everything this machine should end up with, tools it lacks excluded."""
    links = [(REPO / "CLAUDE.md", CLAUDE / "CLAUDE.md"),
             (REPO / "tools" / "mylint.py", CLAUDE / "mylint.py")]
    for skill in sorted(p for p in (REPO / "skills").iterdir() if p.is_dir()):
        links.append((skill, CLAUDE / "skills" / skill.name))

    hooks, mcp, docs, present = [], {}, [], {}
    for name, tool in registry().items():
        where = located(tool)
        if not where:
            continue
        present[name] = where
        for hook in tool.get("hooks", []):
            hooks.append({
                "event": hook["event"],
                "matcher": hook["matcher"],
                "command": hook["command"].format(claude=shlex.quote(str(CLAUDE))),
                "replaces": hook.get("replaces", []),
                "tool": name,
            })
        if "mcp" in tool:
            mcp[name] = tool["mcp"]
        if "doc" in tool:
            docs.append(tool["doc"])
    return {"links": links, "hooks": hooks, "mcp": mcp, "docs": docs, "present": present}


# --- settings.json -------------------------------------------------------------

def read_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text())
    except FileNotFoundError:
        return {}
    except ValueError as err:
        sys.exit(f"{SETTINGS} is not valid JSON ({err}). Fix it before installing.")


def get_path(data, path):
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return MISSING
        cur = cur[key]
    return cur


def set_path(data, path, value):
    cur = data
    for key in path[:-1]:
        node = cur.get(key)
        if not isinstance(node, dict):
            node = {}
            cur[key] = node
        cur = node
    cur[path[-1]] = value


def drop_path(data, path):
    """Remove a key, then any container left empty behind it. A container that
    still holds something else is left alone."""
    parent = get_path(data, path[:-1])
    if isinstance(parent, dict):
        parent.pop(path[-1], None)
    for depth in range(len(path) - 1, 0, -1):
        node = get_path(data, path[:depth])
        owner = get_path(data, path[:depth - 1])
        if isinstance(node, dict) and not node and isinstance(owner, dict):
            owner.pop(path[depth - 1], None)


def leaves(node, prefix=()):
    for key, value in node.items():
        if isinstance(value, dict):
            yield from leaves(value, prefix + (key,))
        else:
            yield prefix + (key,), value


def merge_preferences(settings: dict, prefs: dict):
    """This repo owns the value of every key it names. A list is joined rather
    than replaced, so a deny entry added on one machine survives."""
    record, changes = [], []
    for path, value in leaves(prefs):
        dotted = ".".join(path)
        existing = get_path(settings, list(path))
        if isinstance(value, list):
            current = existing if isinstance(existing, list) else []
            added = [item for item in value if item not in current]
            record.append({"path": list(path), "kind": "list", "added": added,
                           "had": existing is not MISSING})
            if added:
                set_path(settings, list(path), current + added)
                changes.append(f"{dotted} += {added}")
        else:
            record.append({"path": list(path), "kind": "scalar",
                           "had": existing is not MISSING,
                           "was": None if existing is MISSING else existing})
            if existing != value:
                set_path(settings, list(path), value)
                was = "unset" if existing is MISSING else json.dumps(existing)
                changes.append(f"{dotted}: {was} -> {json.dumps(value)}")
    return record, changes


def merge_hooks(settings: dict, hooks: list):
    """Managed hooks run first, in the order `config/tools.toml` lists them. The
    entry a managed hook displaces is remembered whole, so an uninstall puts back
    what was there rather than leaving a gap."""
    record, changes = [], []
    groups = {}
    for hook in hooks:
        groups.setdefault((hook["event"], hook["matcher"]), []).append(hook)

    for (event, matcher), wanted in groups.items():
        listeners = settings.setdefault("hooks", {}).setdefault(event, [])
        group = next((g for g in listeners if g.get("matcher") == matcher), None)
        if group is None:
            group = {"matcher": matcher, "hooks": []}
            listeners.append(group)
        entries = group.setdefault("hooks", [])
        before = list(entries)

        displaced = []
        for hook in wanted:
            prior, index = None, None
            for position, entry in enumerate(before):
                if entry in displaced:
                    continue
                command = entry.get("command", "")
                if command == hook["command"] or any(p in command for p in hook["replaces"]):
                    prior, index = entry, position
                    displaced.append(entry)
                    break
            record.append({"event": event, "matcher": matcher, "command": hook["command"],
                           "had": prior is not None, "was": prior, "index": index})
            if prior is not None and prior.get("command") != hook["command"]:
                changes.append(f"{event}/{matcher}: replaced {prior.get('command')}")

        entries[:] = [entry for entry in before if entry not in displaced]
        entries[:0] = [{"type": "command", "command": hook["command"]} for hook in wanted]
        if entries != before:
            changes += [f"{event}/{matcher}: {hook['command']}  [{hook['tool']}]" for hook in wanted]
    return record, changes


def prune_hooks(settings: dict):
    events = settings.get("hooks", {})
    for event in list(events):
        events[event] = [group for group in events[event] if group.get("hooks")]
        if not events[event]:
            del events[event]
    if not events:
        settings.pop("hooks", None)


def merge_mcp(settings: dict, servers: dict):
    record, changes = [], []
    if not servers:
        return record, changes
    configured = settings.setdefault("mcpServers", {})
    for name, entry in servers.items():
        existing = configured.get(name, MISSING)
        if existing == entry:
            record.append({"name": name, "had": True, "was": entry})
            continue
        record.append({"name": name, "had": existing is not MISSING,
                       "was": None if existing is MISSING else existing})
        configured[name] = entry
        changes.append(f"mcp {name}: {entry['command']} {' '.join(entry.get('args', []))}")
    return record, changes


def write_settings(settings: dict, dry_run: bool):
    body = json.dumps(settings, indent=2) + "\n"
    if SETTINGS.exists() and SETTINGS.read_text() == body:
        return False
    if dry_run:
        return True
    backup = SETTINGS.with_name(f"settings.json.bak-{date.today():%F}")
    if SETTINGS.exists() and not backup.exists():
        shutil.copy2(SETTINGS, backup)
        print(f"  backup   {short(backup)}")
    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(body)
    tmp.replace(SETTINGS)
    return True


# --- symlinks ------------------------------------------------------------------

def short(path) -> str:
    text = str(path)
    home = str(pathlib.Path.home())
    return text.replace(home + "/", "~/") if text.startswith(home + "/") else text


def link(src: pathlib.Path, dest: pathlib.Path, dry_run: bool):
    if dest.is_symlink() and os.readlink(dest) == str(src):
        return "ok"
    if dest.exists() and not dest.is_symlink():
        backup = dest.with_name(f"{dest.name}.bak-{date.today():%F}")
        print(f"  backup   {short(dest)} -> {backup.name}")
        if not dry_run:
            dest.rename(backup)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(src)
    return "link"


def prune_stale_links(keep: set, dry_run: bool):
    """A symlink into this repo that nothing installs any more is left over from
    an older layout. Only symlinks are ever removed, never a real file."""
    removed = []
    for parent in (CLAUDE, CLAUDE / "skills"):
        if not parent.is_dir():
            continue
        for entry in sorted(parent.iterdir()):
            if not entry.is_symlink() or entry in keep:
                continue
            target = pathlib.Path(os.readlink(entry))
            if REPO in target.parents:
                removed.append(entry)
                if not dry_run:
                    entry.unlink()
    return removed


def write_tools_local(docs: list, dry_run: bool):
    lines = ["<!-- Generated by install.sh: the tool notes this machine has.",
             "     Edit config/tools.toml or tools/docs/, not this file. -->", ""]
    lines += [f"@{doc}" for doc in docs]
    body = "\n".join(lines) + "\n"
    if TOOLS_LOCAL.exists() and TOOLS_LOCAL.read_text() == body:
        return False
    if not dry_run:
        TOOLS_LOCAL.write_text(body)
    return True


def remembered(previous: dict, hooks: list, prefs: list, mcp: list):
    """Only the first install saw the values that predate this repo. A later run
    displaces the installer's own entries, so it inherits that memory instead of
    recording itself as the thing to put back."""
    by_command = {entry["command"]: entry for entry in previous.get("hooks", [])}
    for record in hooks:
        displaced = record.get("was") or {}
        source = by_command.get(record["command"]) or by_command.get(displaced.get("command"))
        if source:
            record.update({"had": source["had"], "was": source["was"],
                           "index": source.get("index")})

    by_path = {tuple(entry["path"]): entry for entry in previous.get("preferences", [])}
    for record in prefs:
        source = by_path.get(tuple(record["path"]))
        if source and source["kind"] == record["kind"]:
            record.update(source)

    by_name = {entry["name"]: entry for entry in previous.get("mcpServers", [])}
    for record in mcp:
        source = by_name.get(record["name"])
        if source:
            record.update({"had": source["had"], "was": source["was"]})


# --- commands ------------------------------------------------------------------

def install(dry_run: bool):
    steps = plan()
    if dry_run:
        print("dry run, nothing will change\n")
    print(f"installing into {short(CLAUDE)}\n")

    if not dry_run:
        (CLAUDE / "skills").mkdir(parents=True, exist_ok=True)
    for src, dest in steps["links"]:
        print(f"  {link(src, dest, dry_run):8} {short(dest)}")
    for stale in prune_stale_links({dest for _, dest in steps["links"]}, dry_run):
        print(f"  remove   {short(stale)} (stale link into this repo)")
    if write_tools_local(steps["docs"], dry_run):
        print(f"  write    {short(TOOLS_LOCAL)}")

    settings = read_settings()
    before_this_run = state()
    prefs_record, prefs_changes = merge_preferences(settings, preferences())
    hooks_record, hooks_changes = merge_hooks(settings, steps["hooks"])
    mcp_record, mcp_changes = merge_mcp(settings, steps["mcp"])

    print(f"\nsettings ({short(SETTINGS)})")
    for change in prefs_changes + hooks_changes + mcp_changes:
        print(f"  {change}")
    if not (prefs_changes or hooks_changes or mcp_changes):
        print("  already current")

    before = SETTINGS.read_text() if SETTINGS.exists() else ""
    if write_settings(settings, dry_run) and dry_run:
        after = json.dumps(settings, indent=2) + "\n"
        print()
        for row in difflib.unified_diff(before.splitlines(), after.splitlines(),
                                        "settings.json", "settings.json (after)", lineterm=""):
            print(f"  {row}")

    remembered(before_this_run, hooks_record, prefs_record, mcp_record)
    if not dry_run:
        STATE.write_text(json.dumps({
            "version": 1,
            "repo": str(REPO),
            "installed": f"{date.today():%F}",
            "links": [str(dest) for _, dest in steps["links"]],
            "preferences": prefs_record,
            "hooks": hooks_record,
            "mcpServers": mcp_record,
        }, indent=2) + "\n")
        print()
        doctor()


def uninstall(dry_run: bool):
    saved = state()
    if not saved:
        sys.exit(f"no install recorded in {short(STATE)}")
    if dry_run:
        print("dry run, nothing will change\n")

    for path in saved.get("links", []):
        dest = pathlib.Path(path)
        if dest.is_symlink() and REPO in pathlib.Path(os.readlink(dest)).parents:
            print(f"  remove   {short(dest)}")
            if not dry_run:
                dest.unlink()

    settings = read_settings()
    for entry in saved.get("preferences", []):
        path = entry["path"]
        if entry["kind"] == "list":
            current = get_path(settings, path)
            kept = [x for x in current if x not in entry["added"]] if isinstance(current, list) else []
            if kept or entry.get("had"):
                set_path(settings, path, kept)
            else:
                drop_path(settings, path)
        elif entry["had"]:
            set_path(settings, path, entry["was"])
        else:
            drop_path(settings, path)
        print(f"  restore  {'.'.join(path)}")

    for entry in reversed(saved.get("hooks", [])):
        for group in settings.get("hooks", {}).get(entry["event"], []):
            if group.get("matcher") != entry["matcher"]:
                continue
            kept = [h for h in group.get("hooks", []) if h.get("command") != entry["command"]]
            if entry.get("was"):
                kept.insert(min(entry.get("index") or 0, len(kept)), entry["was"])
            group["hooks"] = kept
        prior = entry.get("was")
        verb, shown = ("restore ", prior.get("command")) if prior else ("remove  ", entry["command"])
        print(f"  {verb} hook {shown}")
    prune_hooks(settings)

    for entry in saved.get("mcpServers", []):
        servers = settings.get("mcpServers", {})
        if entry["had"]:
            servers[entry["name"]] = entry["was"]
            print(f"  restore  mcp {entry['name']}")
        else:
            servers.pop(entry["name"], None)
            print(f"  remove   mcp {entry['name']}")
        if not servers:
            settings.pop("mcpServers", None)

    write_settings(settings, dry_run)
    if TOOLS_LOCAL.exists():
        print(f"  remove   {short(TOOLS_LOCAL)}")
        if not dry_run:
            TOOLS_LOCAL.unlink()
    if not dry_run:
        STATE.unlink(missing_ok=True)
    print("\nBackups of settings.json and of any file this replaced are kept alongside them.")


def doctor():
    steps = plan()
    settings = read_settings()
    print("tools")
    for name, tool in registry().items():
        where = steps["present"].get(name)
        if where:
            wired = []
            if tool.get("hooks"):
                wired.append("hook")
            if tool.get("mcp"):
                wired.append("mcp")
            if tool.get("doc"):
                wired.append("doc")
            print(f"  ok       {name:14} {', '.join(wired) or 'skill'}")
        else:
            hint = tool.get("source", "")
            print(f"  missing  {name:14} {hint}")

    print("\nchecks")
    scanners = REPO / "skills" / "unslop" / "scripts" / "banned_phrase_scan.py"
    report("mylint scanners", scanners.exists(), short(scanners))
    report("CLAUDE.md linked", (CLAUDE / "CLAUDE.md").is_symlink(), short(CLAUDE / "CLAUDE.md"))
    report("tool notes generated", TOOLS_LOCAL.exists(), short(TOOLS_LOCAL))

    installed_hooks = {h.get("command")
                       for groups in settings.get("hooks", {}).values()
                       for group in groups for h in group.get("hooks", [])}
    for hook in steps["hooks"]:
        report(f"hook {hook['tool']}", hook["command"] in installed_hooks, hook["command"])

    for name in steps["mcp"]:
        here = name in settings.get("mcpServers", {})
        report(f"mcp {name}", here, "settings.json")
        if here and name in user_scoped_mcp():
            print(f"    also defined in ~/.claude.json: claude mcp remove {name} -s user")

    found = subprocess.run([sys.executable, str(REPO / "tools" / "mylint.py"), "--private"],
                           cwd=REPO, capture_output=True, text=True)
    if found.returncode == 2:
        report("private names list", False, "none here, see config/private-names.example.json")
    else:
        counted = [line for line in found.stdout.splitlines() if "private name" in line]
        report("no private names", found.returncode == 0, counted[-1] if counted else "")


def user_scoped_mcp() -> set:
    try:
        data = json.loads((pathlib.Path.home() / ".claude.json").read_text())
    except (OSError, ValueError):
        return set()
    return set(data.get("mcpServers", {}))


def report(label: str, good: bool, detail: str = ""):
    print(f"  {'ok      ' if good else 'missing '} {label:22} {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print what would change")
    parser.add_argument("--doctor", action="store_true", help="report only")
    parser.add_argument("--uninstall", action="store_true", help="undo the install")
    args = parser.parse_args()

    if args.doctor:
        doctor()
    elif args.uninstall:
        uninstall(args.dry_run)
    else:
        install(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
