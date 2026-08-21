# agent-kit

My coding-agent setup, versioned. Global instructions, the writing lint, and the
skills that are not tied to one job or one codebase.

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
| `tools/mylint.py` | stays here | Checks a draft, a commit message, or a PR body |
| `skills/code-review` | `~/.claude/skills/code-review` | Correctness first, then reuse, simplification, efficiency, altitude, prose |
| `skills/address-review` | `~/.claude/skills/address-review` | Work through reviewer feedback on your own PR and reply per thread |

## mylint

Three modes, all exiting non-zero when they find something:

```sh
python3 tools/mylint.py draft.md                        # spelling and run-ons
python3 tools/mylint.py --commit msg.txt                # commit-message shape
python3 tools/mylint.py --pr body.md                    # PR-description shape
git show -s --format=%B HEAD | python3 tools/mylint.py --commit
pbpaste | python3 tools/mylint.py
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

## What is deliberately not here

Work-specific skills, credentials, and `settings.json`. The first belong
with the codebase they serve, and the last two should never reach a remote.

## Third-party skills

Installed separately, symlinked from their own clones so upstream keeps
updating them:

- [`mattpocock/skills`](https://github.com/mattpocock/skills): `writing-for-agents`,
  `diagnosing-bugs`, `resolving-merge-conflicts`
- [`no-session/pstack`](https://github.com/no-session/pstack): `careful`, a
  `PreToolUse` hook that stops `rm -rf`, `git reset --hard`, and force-pushes
- [`theclaymethod/unslop`](https://github.com/theclaymethod/unslop): removes AI
  writing patterns from prose

`careful` ships a portability bug worth knowing about: `check-careful.sh` uses
GNU `\s` inside `sed -E`, which BSD sed on macOS does not understand, so the
safe-exception list silently fails and it warns on every `rm -rf node_modules`.
Replace `\s` with `[[:space:]]` after cloning.
