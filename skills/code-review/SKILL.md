---
name: code-review
version: 1.2.0
description: Review the current diff for correctness bugs and reuse/simplification/efficiency/altitude/prose cleanups at a chosen effort level. Use when the user types /code-review, "review my diff", "review my changes", "find bugs in this branch", "review before I push". Args - effort low|medium|high|max (default medium); --comment posts findings as inline PR comments; --fix applies the findings to the working tree; an explicit base ref or PR to scope against. The generic correctness plus quality pass. For quality-only cleanups use simplify.
---

# Code Review

Review the working diff and report real problems: correctness bugs first, then reuse, simplification, efficiency, altitude, and prose cleanups. A generic engineering review, language- and framework-aware. For quality-only cleanups with no bug hunt, use `simplify`.

## Arguments
- **effort** `low` | `medium` (default) | `high` | `max`, trading breadth against confidence:
  - `low` / `medium`: fewer, high-confidence findings, the things you would block a PR on.
  - `high` / `max`: broader coverage, including lower-confidence findings worth a look. Spend proportionally more time reading surrounding code.
- **--comment**: after the review, post findings as inline PR comments, once the user has approved the set.
- **--fix**: after the review, apply the findings to the working tree.
- **base ref / PR**: scope target (e.g. `main`, a branch, `#123`). Defaults to the current branch vs its base.

## Scope the diff
Run first to know what's under review:
```
git status
git log <base>..HEAD --oneline
git diff --stat <base>...HEAD
```
Resolve the target in this order: explicit PR (`gh pr diff <ref>`) → explicit base (`git diff <base>...HEAD`) → default current branch vs base, **plus** uncommitted (`git diff`) so the review covers "what I would push". The review covers **new code only**: the added and changed lines. Removed lines, untouched lines, and code truncated at a hunk boundary are all out of scope.

## What to look for
Read the actual code around each change before flagging: context is what decides whether something is a bug. Where the diff extends an existing pattern, the pattern stands; a finding argues about this change, not about the file's history.

**Correctness (always, first priority)**
- Logic errors: wrong conditions, off-by-one, inverted operators, broken control flow.
- Edge cases: empty/null/undefined inputs, zero, boundaries, unexpected types.
- Error handling: swallowed errors, missing propagation, wrong error type, panics on bad input.
- State/concurrency: stale state, races, inconsistent updates, missing synchronization.
- Security: injection (SQL/command/XSS/CSRF/path traversal), auth/authz gaps, credential exposure, missing validation at boundaries.
- API/contract: breaking changes, meaning removed or renamed exports, changed signatures, new required params, altered return/error shapes.

**Cleanups (quality)**
- **Reuse**: duplicated logic that an existing helper/type already covers; reinvented utilities.
- **Simplification**: dead code, redundant branches, over-nesting, needless allocation. Includes **speculative generality**: a parameter, hook, trait, or layer of indirection added for a need the change does not have. Inline it back until a real caller asks for it.
- **Efficiency**: expensive work in loops, N+1, unbounded lists, missing memoization, sequential calls that could parallelize, render-path cost in React.
- **Altitude**: logic at the wrong layer, such as business rules in a view, parsing in a handler, or a concern that belongs upstream.
- **Prose**: comments and docs that cost more than they carry. See below.

**Prose in the diff**

A comment earns its place by carrying the *why* the code cannot: a hidden constraint, a subtle invariant, a workaround for a named bug, a behaviour that surprises the reader. Judge every added comment and doc block against that bar, and flag the ones below it:

- **Restatement**: the comment says what the next line already says (`// increment the counter`). The code is the documentation.
- **Reflex doc blocks**: JSDoc, docstrings, or `///` on a self-evident helper, prop, type, or field, added because the construct exists rather than because a reader needs it.
- **Narration**: prose about the change rather than the code ("Mirror the legacy behaviour", "Caller is responsible for...", "Note that we now..."). If a reader can infer it from the names and the surrounding code, it is noise.
- **Planning metadata**: phase numbers, tier labels, migration-step markers, ticket keys, commit SHAs, "reserved for a later change". That belongs in the commit message, the PR, or the tracker, where it stays true.
- **Unrequested documents**: a new `README` or `.md` the change did not need.

Judge the density against the file's neighbours: a diff whose comment-to-code ratio jumps well above the code around it is the signal, and the fix is deleting whole comments rather than shortening them.

Adapt to the stack (Rust, TypeScript, React, and so on) detected from file extensions and patterns. At `low`/`medium`, report only findings you are confident in; at `high`/`max`, widen the net and mark the uncertain ones as such.

## Output
Lead with a one-line summary and counts. Each finding:
```
path/to/file.ext:line - <one-line problem>
  why: <what breaks / why it matters>
  fix: <concrete change>
```
Group by severity: **BLOCKING** (correctness and security, which must be fixed), **SHOULD-FIX** (warnings), **CLEANUP** (reuse, simplification, efficiency, altitude, prose), **QUESTION** (needs author intent). Clean is a valid result, and saying so is the honest report: correctness outranks every cleanup, and one real bug is worth more than ten nits.

## After the review (only if asked)
- **--fix**: apply the findings to the working tree. Apply BLOCKING plus clear CLEANUP by default, and confirm anything ambiguous. Re-run the project verify command (build, lint, tests) afterwards and fix whatever it reports at the root, leaving no suppression comment behind.
- **--comment**: post findings as inline PR comments via `gh` (`gh api .../pulls/<n>/comments`). Show the user the comment set and post on their explicit go-ahead.
