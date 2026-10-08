# agent-kit

My coding-agent setup, versioned: the global instructions every project loads,
the preferences and hooks behind them, the tools that get wired in where a
machine has them, and the skills I want to keep editing.

Two hosts read it, Claude Code and Codex, off one `config/` rather than a
parallel one. A skill is the same `SKILL.md` for both and a hook is the same
schema, so what differs is only where each lands and which events exist.

Instructions and skills install by symlink, so editing a file here changes what
the agent reads immediately, and `git pull` on another machine is the whole
update. `settings.json` is the exception. It holds credentials and per-machine
config that must never reach a remote, so the installer merges in the slice this
repo owns and records what it touched. That record is what makes a second run a
no-op and an uninstall able to put the old values back.

```sh
./install.sh              # symlink, merge settings, wire the tools present
./install.sh --dry-run    # print the diff, change nothing
./install.sh --doctor     # report what is wired and what is missing
./install.sh --uninstall  # undo
```

Python 3.11 or newer, for `tomllib`. Nothing else.

## What is in here

| Path | Installs to | What it is |
| --- | --- | --- |
| `CLAUDE.md` | `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` | Global instructions, loaded on every turn of every project |
| `config/preferences.json` | merged into `~/.claude/settings.json` | The settings this repo owns |
| `config/tools.toml` | hooks and MCP servers for both hosts | Every optional tool, and how each is wired |
| `config/private-names.example.json` | copied by hand to `~/.claude/private-names.json` | The shape of the `--private` list, never the list |
| `tools/docs/*.md` | `tools.local.md`, linked from `CLAUDE.md` | Notes on a tool, loaded only where that tool exists |
| `tools/mylint.py` | `~/.claude/mylint.py` | Checks a draft, a commit message, or a PR body |
| `tools/statusline.sh` | `~/.claude/statusline.sh`, named by `statusLine` | The status line, wired only where `jq` exists |
| `tools/install.py` | stays here | The installer `install.sh` runs |
| `skills/*` | `~/.claude/skills/*` and `~/.codex/skills/*` | See the attribution table |
| `vendor-licenses/` | stays here | Licences of the vendored skills |

## Tools

| Tool | Where it comes from | Wired as |
| --- | --- | --- |
| `rtk` | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | `PreToolUse` hook on `Bash`, plus notes in `CLAUDE.md` |
| `caveman` | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | its own installers: a Claude plugin, and skills for Codex |
| `ferridriver` | [salamaashoush/ferridriver](https://github.com/salamaashoush/ferridriver) | MCP server in `~/.claude.json`, plus notes in `CLAUDE.md` |
| `statusline` | this repo | `statusLine` in `settings.json`, needing `jq` |

Adding one is a block in `config/tools.toml`:

```toml
[mockpit]
what = "What it does, one line, shown by --doctor."
probe = "mockpit"                 # the binary to look for
source = "cargo install mockpit"  # what --doctor suggests when it is missing
doc = "tools/docs/mockpit.md"     # always-on notes, imported only where it exists

[mockpit.mcp]
command = "mockpit"
args = ["mcp"]
```

A `statusline = "tools/x.sh"` key is the third thing a block can wire: the script
is symlinked next to the settings that name it, so the path in `settings.json`
survives this clone moving, the same way the herd hooks do.

A tool that ships its own installer is wired by running it: `setup` lists the
commands for Claude and `codex_setup` those for Codex, each run on every
install, so they have to be safe to repeat. `{home}` works in them as it does in
a hook. `teardown` and `codex_teardown` are recorded when the install runs,
which is what lets `--uninstall`, or deleting the block, undo a tool whose
definition is gone; an uninstall runs them before it removes any link.

`probe` is the whole conditional. No binary means no hook, no MCP server, and no
notes in the context, so the same clone installs cleanly on a machine that has
none of these. Hook order inside one event follows this file, and deleting a
block unwires its hooks on the next install.

`{home}` in a hook command is the host's own config directory, so each host
runs the copy belonging to it and uninstalling one takes nothing of the other's
with it. A hook goes to both hosts under the same event name, and two keys say
otherwise: `codex_event` renames it, which is what `herd`'s `Notification` needs
because Codex has no such event and `PermissionRequest` is the half that
matters; `codex = false` withholds it entirely. `codex_command` gives Codex a
different command, which is how `rtk` runs `rtk hook codex` there, and a
tool's `codex_requires` is a command that must succeed before Codex gets any of
it, since an rtk older than that subcommand would block every shell command.
A hook's `timeout`, in seconds, reaches Claude's settings: the `rtk` hook sits in
front of every Bash call, so it gets ten seconds rather than the default
minute.

## Codex

Codex is wired where `codex` is on `PATH`, off the same `config/`, and
`--doctor` reports it beside Claude's half. What lands where:

| | Claude Code | Codex |
| --- | --- | --- |
| Instructions | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` |
| Skills | `~/.claude/skills/*` | `~/.codex/skills/*` |
| Hooks | `settings.json` | `~/.codex/hooks.json`, plus `features.hooks` |
| MCP servers | `~/.claude.json` | `config.toml`, written by `codex mcp add` |
| Status line | `statusLine` | nothing, see below |

Both instruction files are symlinks to the one `CLAUDE.md`. Tool notes are
rendered into `tools.local.md` and linked beside both instruction files. The
shared instructions tell each agent to read those notes before using a tool;
neither host needs to expand an `@` import. The installer also adds `CLAUDE.md`
to `project_doc_fallback_filenames`, preserving existing fallback filenames,
so Codex reads project instructions in repositories that only have `CLAUDE.md`.
Start a new Codex session after installing to load the updated instructions.

**`config.toml` is Codex's own file.** MCP and feature changes go through
`codex mcp add` and `codex features enable hooks`. Instruction fallbacks use
Codex's local app-server configuration API with an expected version, so a
concurrent configuration edit rejects the write. Existing hook trust, project
settings and custom MCP servers are preserved. Repeated installs leave
unchanged configuration files and their timestamps alone.

**Codex asks before it runs a hook**, once each, and records the hash it
approved in `config.toml`. The installer does not forge those. Review new or
changed definitions with `/hooks`. `--doctor` queries the local app server to
check that managed hooks are enabled and trusted and that skills actually
loaded. It exits nonzero when a required check fails. These checks make no
model requests.


Run `python3 -m unittest discover -s tests` for installer and hook regression
tests. The integration tests require Codex on `PATH`; they exercise its local
configuration protocol without model requests.

**Two things do not port.** Codex's status line is a list of segments it renders
itself rather than a script it runs, so `tools/statusline.sh` stays Claude's.
And `codex features disable hooks` writes `hooks = false` rather than removing
the key, so an uninstall on a machine that never had the key leaves that one
line behind. Everything else round-trips: against a Codex home already carrying
a hook and a project trust level of its own, install then uninstall returned
`config.toml` byte for byte and `hooks.json` to its prior content, gaining only
the trailing newline every file this installer writes ends with.

A symlink someone else put in `~/.codex/skills` is left alone, the way one in
`~/.claude/skills` is. Omarchy's `diagnose-crash` and `omarchy` sit beside these
nine here and neither install nor uninstall touches them.

## What the installer will not do

**Clobber something of yours.** Existing real files and symlinks pointing
outside this repo are kept and reported. Configuration files are copied to
`.bak-<date>` before the first edit of the day, and the only symlinks the
installer removes are ones pointing into this repo. `--dry-run` prints the
settings diff without writing.

**Keep a key it does not name.** The merge touches the keys in
`config/preferences.json`, and the hooks, MCP servers and status line named in
`config/tools.toml`. Nothing else, so servers and plugins from other work stay
where they are. An `[x.mcp]` block lands in `~/.claude.json` rather than
`settings.json`, because that is where Claude Code reads user-scope servers
from; a run also clears out entries an earlier version of this installer left
in `settings.json`, where they did nothing. A list, `permissions.deny` in practice, is joined rather than
replaced.

**Forget what it replaced.** `~/.claude/agent-kit.state.json` holds the previous
value of every key, hook and server it changed on either host, and `--uninstall`
reads that back. A round trip on this machine's settings returns the file byte
for byte. One state file rather than one per host, so one `--uninstall` undoes
both and neither can be left half wired.

**Version anything private.** Credentials, work config, the `--private`
names and the generated `tools.local.md` all stay out of git.

## The status line

```
󰉋 ~/Workspace/agent-kit  󰘬 main +2 ~1 ?3  󰙅 fix-login  󱙺 Opus 5  󰾆 ━━━━━━━━━━  37%  󰆼 4.1M · sub 743K  󰓅 5h 42% · 7d 18%  $4.62 · $1.12/M  󰥔 25m
```

Folder, branch with working-tree counts, the worktree, model, context bar, tokens,
rate limits, cost and session length. Every segment past the folder appears only
when it has something to say, which the worktree takes literally: its name is
usually also the branch name or the last thing in the path, and it drops out in
both cases rather than printing a third copy.

The context bar is what fits in the window right now; the token count is what the
session has spent getting there, input, output and both halves of the cache added
up, with the share a subagent burned broken out beside it once one has run. That
number is not in the payload the status line is handed, which stops at dollars, so
it is summed out of the transcript, where a subagent turn is written alongside the
main thread's. Two things make a naive sum wrong. An assistant entry repeats
its whole usage object once per content block, so the message id has to carry
across renders. And a tool input can contain the literal text of a usage field,
so the numbers come from the last `"usage":{` on the line rather than the first
match anywhere in it.

`$4.62 · $1.12/M` is the session's cost and what a million tokens came to across
it. The pair earns its place because the two disagree so wildly. A cache read
bills at a tenth of the input rate and a one-hour cache write at twice it, so
almost none of a long session is charged at the headline number, and 4.1M tokens
for $4.62 reads as an arithmetic error until the rate is next to it. It is also
the only thing on the line that says whether the cache is working. It sits near a
fifth of list while the prefix holds and climbs towards list when something
invalidates it every turn, so it is coloured against the model's own list rate,
green below a third and red past two thirds. That table is read but never
printed: the rates it holds are reconciled against a transcript's cost-state,
which reproduces to the cent, and a model it has never heard of leaves the rate
uncoloured rather than judging it against the wrong band.

It renders on every update, so it is written to fork twice. One `jq` call reads
the whole payload and one `awk` reads the transcript. The branch and the worktree
come from reading `.git` and `.git/HEAD` directly rather than from `git
rev-parse`, and the bar, the percentages, the durations, the token counts and the
blended rate are `printf -v` and shell arithmetic. The rate reaches the one float
it needs through `printf`'s exponent. The working-tree counts sit
behind a five-second cache keyed on session and directory, with its timestamp
inside the file so reading it back costs no `stat` either, and the token sum
behind a running total keyed on session, so a render parses only the lines the
transcript grew since the last one. Measured against the version this replaced,
seven external commands a render became one, and 80ms became 18ms, of which 11ms
is bash starting up. Adding the tokens put a millisecond back.

Colour is Tokyo Night Storm, in truecolor where `COLORTERM` claims it and 256
otherwise. The glyphs need a Nerd Font; `TERM=linux`, `TERM=dumb` or
`CLAUDE_STATUSLINE_ASCII=1` drops to plain text rather than a row of boxes.

## mylint

Four modes, all exiting non-zero when they find something:

```sh
python3 ~/.claude/mylint.py draft.md                        # spelling and run-ons
python3 ~/.claude/mylint.py --commit msg.txt                # commit-message shape
python3 ~/.claude/mylint.py --pr body.md                    # PR-description shape
python3 ~/.claude/mylint.py --private                       # private names
git show -s --format=%B HEAD | python3 ~/.claude/mylint.py --commit
pbpaste | python3 ~/.claude/mylint.py
```

The thresholds come from measurement rather than taste. Seven misspellings
account for 96% of the spelling errors in 22k words of my own review comments,
and 4% of segments run past 60 words. The PR checks come from 27 of my own
merged pull requests against 85 an agent drafted: I have never used a markdown
table or an em-dash in a description, and I average 1.3 headings to the agent's
3.1, at 112 words to its 181. Bullets and bold are identical across both, so
those are not the tell.

Rerun the numbers against a fresh sample before trusting them on someone else's
writing. They describe one person.

`--private` reads its patterns from `~/.claude/private-names.json`, which this
repo does not carry and must not: writing those names here in order to catch
them would publish them. `config/private-names.example.json` shows the shape
with `acme` stand-ins. Without that file `--private` exits 2 and says where it
looked, rather than reporting a repo clean because it had nothing to look for.

The AI-tell and structure checks come from unslop's scanners, read from the
vendored copy in `skills/unslop/scripts`. They used to be read from a second
checkout by absolute path, which meant that on any other machine a draft came
back clean because the scanners were never there. A scanner that cannot run now
says so on stderr.

## Skills, and where each came from

Third-party skills are **vendored rather than submoduled**, so I can change them
without waiting on upstream or losing the change to a pull. Every one is
attributed below, with its licence in `vendor-licenses/`. The cost is that a
fix upstream will not arrive on its own; re-sync by diffing against the source
repo. Checked on 2026-08-29 against mattpocock/skills `6654f6b` and unslop
`d81f519`: every vendored file matches byte for byte except where the table
says otherwise.

| Skill | Origin | Licence | Changed from upstream |
| --- | --- | --- | --- |
| `writing-for-agents` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `diagnosing-bugs` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `resolving-merge-conflicts` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `grill-me` / `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `spec-review` | [mattpocock/skills](https://github.com/mattpocock/skills) `code-review` | MIT | renamed, so it stops colliding with the built-in `/code-review`, which its description now points at for correctness passes |
| `unslop` | [theclaymethod/unslop](https://github.com/theclaymethod/unslop) | MIT (declared in its frontmatter; the repo ships no LICENSE file) | runtime only: `SKILL.md`, `references/`, `presets/`, `scripts/`. Its `evals/` and `plans/` stay upstream |

## What is deliberately not here

**Skills another tool installs.** Those are versioned in the repo that ships
them and written to `~/.claude/skills` on install. A copy here would fork them.

**Credentials, and any setting this repo does not name.** `--doctor` reports
what is wired without printing the file.

**Any name from private or client work, in any file.** Not in a fixture, not
in a doc example, and not in the pattern that exists to catch it. `--private`
is the gate and `--doctor` runs it.
