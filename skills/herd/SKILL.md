---
name: herd
description: Run other Claude sessions from this one, over Herdr.
disable-model-invocation: true
---

```
~/.claude/herd.py                          what is running
~/.claude/herd.py on <repo> [brief]        start work on a repo
~/.claude/herd.py start <name> [brief]     start one; brief is a FILE, after the name
~/.claude/herd.py watch [name …]           block until they stop working
~/.claude/herd.py verify <who>              run what that repo checks itself with
~/.claude/herd.py land <who>                push it and open a pull request
~/.claude/herd.py events                    what the hooks recorded
~/.claude/herd.py tidy                      remove the worktrees nobody is in
~/.claude/herd.py done <who> [note]         close this session, work handed on
~/.claude/herd.py tell <who> <text>        send a follow-up
~/.claude/herd.py read <who>               the tail of what one said
~/.claude/herd.py stop <who>               stop one
```

`who` is whatever the person remembers: a name, part of one, a misspelling, a
directory, or a few words of what the session is doing. Pass it across
unchanged rather than guessing which was meant. Two matches is a refusal
carrying the list, and that list is the answer to relay.

## The session that runs the others

This is the shape it is for: one session driven from a phone, starting work on
a machine left awake, checking on it later from somewhere else. Every command
answers in a few lines, because the screen is small and the reply is the whole
interface.

`watch` is the one that makes it orchestration rather than polling. It blocks
until each session is idle, done or **blocked**, then prints where they all
got to. A blocked session is sitting on a question; `read` it, and `tell` it
the answer.

`--worktree` is not optional when two sessions share a repo. Without it they
edit the same files, build over each other, and commit each other's work.

**The brief is a file and it goes after the name.** `--worktree` takes an
optional branch, so `herd start x --worktree brief.md` reads the brief as a
branch name and starts a session with nothing to do; it prints "give it
something to do" and looks like one that was simply never told. Both shapes
that cannot have been meant are refused now, with the line that would have
worked, and `--branch` is the spelling with no ambiguity in it:

    herd start modules brief.md --repo tsllvm      # the brief, after the name
    herd start modules brief.md --worktree         # a worktree, default branch
    herd start modules brief.md --branch work/x    # and a branch of your own

`--repo` makes the worktree itself, so `--worktree` beside it is refused rather
than ignored. Use `--branch` there.

## A background session is a session too

`claude --bg` starts a session with no pane, so herdr never lists it and an
earlier version of this tool could not see it at all. Someone asking why their
session is missing from the listing has usually found one of these. The listing
now merges both sources, herdr's panes and `claude agents --json`, and tags the
background ones `bg`.

The CLI is what limits them, not this tool:

- `read` works on both. `claude logs` replays a screen rather than a
  transcript, so the cursor moves are played back into words first.
- `stop` works on both. A background session keeps its conversation, so
  `claude attach <id>` picks it up again afterwards.
- `tell` does not reach one. Nothing prompts a background session from
  outside; attach to it instead.
- `watch` cannot block on one, because there is no pane for herdr to wait on.
  It is listed with its status and skipped.

## Starting on a repo that may not be here yet

`herd on <repo>` is the phone-sized form: find the repo, get a checkout, start
a session in it, all from one word.

- Already at `~/Workspace/<repo>`: it fetches, and leaves that checkout alone.
- Not there: `gh` looks for the name under your own account first, then each
  organisation you belong to, and clones the one match into `~/Workspace`. Two
  matches refuse and print both, the rule `who` already follows.
- Either way the session works in a worktree of its own at
  `~/.herdr/worktrees/<repo>/<name>`, on a branch `work/<name>` **cut from
  wherever that checkout currently is**, not from the remote's default branch.
  A successor cut from a stale main starts without the work that produced it.
  Nothing pulls, resets or checks out over your own checkout.

A worktree carries commits and nothing else, so an uncommitted file would not
travel. Rather than start a successor from a state its predecessor cannot see,
this refuses and names the files: commit them, and the successor inherits them
with the branch.

The session takes the repo's name unless `--name` says otherwise, and that name
is what every other command answers to. `herd start <name> --repo <repo>` is the
same thing when the session should not be called after the repo.

## Finishing, rather than stopping

Three commands exist because a session that has stopped is not a session that
has delivered.

`verify` runs what the repo checks itself with, looked for in this order: a
`justfile` carrying a `ready` recipe, then a `ready`, `verify`, `ci`, `check`
or `test` script in `package.json` through whichever runner the nearest
lockfile implies, then `cargo test`. Pass the command yourself when the repo
says nothing. The exit code is the verdict, never a grep over the output, and a
failure prints its own tail.

`land` pushes what a session committed and opens a pull request from its
branch. It refuses while a file is uncommitted, because a push carries commits
and would leave the rest in a checkout nobody opens again, and it refuses when
nothing is committed at all. Like `stop`, it prints the plan first and needs
`--yes`.

`tidy` removes worktrees no session is in, and only ones it can prove are
finished with: nothing uncommitted, and nothing committed that the default
branch does not already have. Everything else is listed and left alone.
Branches are never deleted.

## Closing itself, once the work has moved

`herd done <successor> [note]` is how a session that has handed its work on
closes its own pane. The order that makes it safe:

1. Start the successor and give it the brief.
2. Commit what is on disk.
3. `herd done <successor> --yes "what the next reader needs"`.

Hand over while the successor is working, because a session that is working is
a session that took the brief. `done` makes that check itself and says so when
it fails, so the handover happens at the moment the work moves rather than when
it finishes.

The note is the part that lasts. Closing the pane ends the conversation that
knows what was handed over and why, and what survives is one line in
`~/.herdr/events.jsonl` that `herd events` prints. Write the note for someone
who has only that line.

Every refusal is the same message, that the work has not moved yet. A successor
that has said nothing was never prompted. A modified file is something no
session would be left to explain, so commit it. And the person can always close
a pane themselves, so a session in any doubt keeps working and says why.

## Waiting without polling

`watch` waits on every session at once. One after another meant the first slow
one hid every later one that had already stopped, so the whole answer arrived
when the slowest did. `--first` returns as soon as any one of them stops.

A background session has no pane to wait on, so it is watched through what its
hooks record instead. Two user-level hooks in `~/.claude/settings.json` write
one JSON line per event to `~/.herdr/events.jsonl`:

```json
"Notification": [{"hooks": [{"type": "command",
  "command": "python3 ~/Workspace/agent-kit/tools/herd-event.py", "async": true}]}],
"Stop": [{"hooks": [{"type": "command",
  "command": "python3 ~/Workspace/agent-kit/tools/herd-event.py", "async": true}]}]
```

`Notification` fires the moment a session blocks on a question or a permission
prompt, so `watch` hears it rather than finding it on some later poll. `herd
events` is the tail of that file. Nothing breaks without the hooks: every
command falls back to waiting.

## The brief is the whole job

A started session has none of the conversation that produced it. Everything it
needs is in the file, and the difference between a brief that works and one
that wastes an afternoon is whether it carries these six.

**Where to read first.** Name the files, in order, with what each is for.
Point rather than summarise: a repo's own notes beat anything restated here.
Fix the stale ones before starting. A session that reads a document describing
a mechanism the code no longer has will build on it.

**The work, numbered, in value order.** Each item says what is wrong, what it
costs, and the shape of the fix. Numbers rather than a list, so the session
knows what to do first when it cannot do everything.

**The measurements.** State each with its number. Re-deriving them costs the
session its first hour, over a different sample, for a different answer.

**What was already rejected, and why.** The options you measured and turned
down are the ones a fresh session will reach for first. Name each with its cost
and the reason it lost, or you will read the same dead end back in its report.

**How it verifies.** Every suite, generator and lint, as commands it can run,
and then the bar: which number has to hold. Without this you get code that
compiles.

**The traps.** The things that cost an hour each: the cache that has to be
rebuilt, the assertion that changed shape, the two implementations that must
agree. These are invisible from the code and the session will hit every one.

Close with the rules that bound it: commit in logical units, do not push, do
not touch main.

## Reach for a browser where the bug lives in a browser

A session working on anything with a rendered result should be told the method,
not just told to check: dump `getComputedStyle` for every element that matters,
diff it against a `git worktree` of the previous commit serving on another
port, and hold zero differences as the bar. Driving a component is not checking
it, and a headless DOM has no opinion about position, focus or geometry.
