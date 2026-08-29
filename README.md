# agent-kit

My coding-agent setup, versioned: the global instructions every project loads,
the Claude Code preferences and hooks behind them, the tools that get wired in
where a machine has them, and the skills I want to keep editing.

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
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Global instructions, loaded on every turn of every project |
| `config/preferences.json` | merged into `~/.claude/settings.json` | The settings this repo owns |
| `config/tools.toml` | hooks and MCP servers in the same file | Every optional tool, and how each is wired |
| `config/private-names.example.json` | copied by hand to `~/.claude/private-names.json` | The shape of the `--private` list, never the list |
| `tools/docs/*.md` | `tools.local.md`, which `CLAUDE.md` imports | Notes on a tool, loaded only where that tool exists |
| `tools/mylint.py` | `~/.claude/mylint.py` | Checks a draft, a commit message, or a PR body |
| `tools/install.py` | stays here | The installer `install.sh` runs |
| `skills/*` | `~/.claude/skills/*` | See the attribution table |
| `vendor-licenses/` | stays here | Licences of the vendored skills |

## Tools

| Tool | Where it comes from | Wired as |
| --- | --- | --- |
| `careful` | this repo | `PreToolUse` hook on `Bash` |
| `rtk` | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | `PreToolUse` hook on `Bash`, plus notes in `CLAUDE.md` |
| `ferridriver` | [salamaashoush/ferridriver](https://github.com/salamaashoush/ferridriver) | MCP server, plus notes in `CLAUDE.md` |

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

`probe` is the whole conditional. No binary means no hook, no MCP server, and no
notes in the context, so the same clone installs cleanly on a machine that has
none of these. Hook order inside one event follows this file, which is why
`careful` sits first: it has to read the command as typed, before rtk rewrites
it.

## What the installer will not do

**Clobber something of yours.** A real file where a symlink belongs is renamed
to `.bak-<date>` first, `settings.json` is copied to `settings.json.bak-<date>`
before the first edit of the day, and the only symlinks it ever removes are ones
pointing into this repo. `--dry-run` prints the settings diff without writing.

**Keep a key it does not name.** The merge touches the keys in
`config/preferences.json`, the hooks and MCP servers in `config/tools.toml`, and
nothing else, so servers, plugins and status line from other work stay where they
are. A list, `permissions.deny` in practice, is joined rather than replaced.

**Forget what it replaced.** `~/.claude/agent-kit.state.json` holds the previous
value of every key, hook and server it changed, and `--uninstall` reads that
back. A round trip on this machine's settings returns the file byte for byte.

**Version anything private.** Credentials, work config, the `--private`
patterns and the generated `tools.local.md` all stay out of git.

## mylint

Four modes, all exiting non-zero when they find something:

```sh
python3 ~/.claude/mylint.py draft.md                        # spelling and run-ons
python3 ~/.claude/mylint.py --commit msg.txt                # commit-message shape
python3 ~/.claude/mylint.py --pr body.md                    # PR-description shape
python3 ~/.claude/mylint.py --private                          # private names
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

`--private` reads its patterns from `~/.claude/private-names.json`, which this repo
does not carry and must not: writing those names here in order to catch
them would publish them. `config/private-names.example.json` shows the shape with
`acme` stand-ins. Without that file `--private` exits 2 and says where it looked,
rather than reporting a repo clean because it had nothing to look for.

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
repo. Checked on 2026-08-29 against pstack `9a24d14`, mattpocock/skills
`6654f6b` and unslop `d81f519`: every vendored file matches byte for byte except
the two below, both deliberate.

| Skill | Origin | Licence | Changed from upstream |
| --- | --- | --- | --- |
| `writing-for-agents` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `diagnosing-bugs` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `resolving-merge-conflicts` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `grill-me` / `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `spec-review` | [mattpocock/skills](https://github.com/mattpocock/skills) `code-review` | MIT | renamed, so it stops colliding with the built-in `/code-review`, which its description now points at for correctness passes |
| `careful` | [no-session/pstack](https://github.com/no-session/pstack) | MIT | BSD `sed` fix, then a rewrite onto bash builtins, see below |
| `unslop` | [theclaymethod/unslop](https://github.com/theclaymethod/unslop) | MIT (declared in its frontmatter; the repo ships no LICENSE file) | runtime only: `SKILL.md`, `references/`, `presets/`, `scripts/`. Its `evals/` and `plans/` stay upstream |

`careful` needed a fix to work on macOS at all. `check-careful.sh` used GNU `\s`
inside `sed -E`, which BSD sed does not understand, so the argument extraction
returned the whole command, every target looked unsafe, and it warned on every
`rm -rf node_modules` despite documenting that as an exception. Eighteen
occurrences are now `[[:space:]]`. Worth upstreaming: it affects every macOS
user.

The second change is the hook's cost. It fires on every Bash tool call, and
`cat`, `grep`, `sed` and `tr` meant four forks a call, roughly 30s across a
median session of 290 of them. Matching is now `[[ =~ ]]`, `nocasematch` and
parameter expansion, with subprocesses left on the warn path, which fires
rarely. That one stays here: it is a rewrite of the file, not a portability fix,
and upstream may not want it.

It runs as an always-on hook rather than a session-scoped skill, installed by
`install.sh` and named through `~/.claude/skills/careful`, so moving this clone
does not break it. Note it returns `permissionDecision: "ask"`, which may not
stop anything under bypass-permissions mode; `"deny"` is the stronger setting if
that turns out to matter.

## What is deliberately not here

**Skills another tool installs.** Those are versioned in the repo that ships
them and written to `~/.claude/skills` on install. A copy here would fork them.

**Credentials, and any setting this repo does not name.** `--doctor` reports
what is wired without printing the file.

**Any name from private or client work, in any file.** Not in a fixture, not in a doc example,
and not in the pattern that exists to catch it. `--private` is the gate and
`--doctor` runs it.
