# agent-kit

My coding-agent setup, versioned: the global instructions every project loads,
the lint that checks what I write, and the skills I want to keep editing.

Third-party skills are **vendored rather than submoduled**, so I can change them
without waiting on upstream or losing the change to a pull. Every one is
attributed below, with its licence in `vendor-licenses/`. The cost is that a
fix upstream will not arrive on its own; re-sync by diffing against the source
repo.

Everything here installs by symlink, so editing a file in this repo changes what
the agent reads immediately, and `git pull` on another machine is the whole
update.

```sh
./install.sh          # symlink into ~/.claude
./install.sh --dry-run
```

## What is in here

| Path | Installs to | What it is |
| --- | --- | --- |
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Global instructions, loaded on every turn of every project |
| `RTK.md` | `~/.claude/RTK.md` | Imported by `CLAUDE.md` |
| `tools/mylint.py` | `~/.claude/mylint.py` | Checks a draft, a commit message, or a PR body |
| `skills/*` | `~/.claude/skills/*` | See the attribution table |
| `vendor-licenses/` | stays here | Licences of the vendored skills |

## mylint

Three modes, all exiting non-zero when they find something:

```sh
python3 ~/.claude/mylint.py draft.md                        # spelling and run-ons
python3 ~/.claude/mylint.py --commit msg.txt                # commit-message shape
python3 ~/.claude/mylint.py --pr body.md                    # PR-description shape
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

## Skills, and where each came from

| Skill | Origin | Licence | Changed from upstream |
| --- | --- | --- | --- |
| `writing-for-agents` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `diagnosing-bugs` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `resolving-merge-conflicts` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `grill-me` / `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | as-is |
| `spec-review` | [mattpocock/skills](https://github.com/mattpocock/skills) `code-review` | MIT | renamed, so it stops colliding with the built-in `/code-review`; description points at my own review skill for correctness passes |
| `careful` | [no-session/pstack](https://github.com/no-session/pstack) | MIT | `sed` portability fix, see below |
| `unslop` | [theclaymethod/unslop](https://github.com/theclaymethod/unslop) | MIT (declared in its frontmatter; the repo ships no LICENSE file) | runtime only: `SKILL.md`, `references/`, `presets/`, `scripts/`. Its `evals/` and `plans/` stay upstream |

`careful` needed a fix to work on macOS at all. `check-careful.sh` used GNU `\s`
inside `sed -E`, which BSD sed does not understand, so the argument extraction
returned the whole command, every target looked unsafe, and it warned on every
`rm -rf node_modules` despite documenting that as an exception. Eighteen
occurrences are now `[[:space:]]`. Worth upstreaming: it affects every macOS
user.

`careful` is also wired as an always-on `PreToolUse` hook in `settings.json`
rather than left session-scoped, and it sits ahead of any command-rewriting hook
so it reads what was actually typed. Note it returns `permissionDecision: "ask"`,
which may not stop anything under bypass-permissions mode; `"deny"` is the
stronger setting if that turns out to matter.

## What is deliberately not here

**Skills another tool installs.** Those are versioned in the repo that ships
them and written to `~/.claude/skills` on install. A copy here would fork them.

**Credentials and `settings.json`**, which should never reach a remote.
