---
name: herd
description: Run other Claude sessions from this one, over Herdr.
disable-model-invocation: true
---

```
~/.claude/herd.py                          what is running
~/.claude/herd.py start <name> [brief]     start one
~/.claude/herd.py watch [name …]           block until they stop working
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
