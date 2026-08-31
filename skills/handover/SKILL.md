---
name: handover
description: Hand a piece of work to a background Claude session, briefed and followable.
disable-model-invocation: true
---

Write the brief, then launch:

```
~/.claude/handover.sh <name> [brief-file]
```

A new terminal window opens on this machine, in this directory, running
`claude --remote-control <name>`: a session to watch on the screen and answer
from the Claude app. The brief travels in a file rather than on the command
line, so quotes and newlines reach it as written.

A session with no brief is fine when you mean to drive it yourself. Everything
below is for when you do not.

## The brief is the whole job

The session has none of the conversation that produced it. Everything it needs
is in the file, and the difference between a brief that works and one that
wastes an afternoon is whether it carries these six.

**Where to read first.** Name the files, in order, with what each is for.
Point rather than summarise: a repo's own notes beat anything restated here.
Fix the stale ones before launching. A session that reads a document describing
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

**The traps.** The things that cost you an hour each: the cache that has to be
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
