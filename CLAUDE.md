# Claude Code Memory

Salama Ashoush, `sashoush`. macOS and Arch Linux.

A project's own `CLAUDE.md` or `AGENTS.md` knows more than this file does. Where
one is more specific, follow it and say which rule you followed.

## Losing my work is the one failure I cannot undo

Hard guardrails. Ask me rather than guess, every time, even when the answer
looks obvious.

**Before an operation that can destroy work I have not committed** (rebase,
reset, `checkout --` over local changes, stash, clean, `rm`, moving or
overwriting files). A clean tree makes most of these safe, so check first and
carry on quietly when there is nothing at risk:

1. Run `git status` and read it. Name the uncommitted and untracked files out
   loud, with sizes, and say what each one risks.
2. Back up by **committing**, by `git branch backup-$(date +%F)`, or by copying
   the files to the scratchpad. Never by stashing.
3. Ask me, naming the files. Wait for the answer.
4. Afterwards, verify the files that existed still exist with their size and
   content intact.

**Stash is not a backup.** `git stash` plus `git stash pop` can silently fail
and drop everything. `git stash drop` is permanent: the SHA leaves the reflog,
and `git fsck --dangling` plus `git stash store -m "msg" <SHA>` is the only
recovery, which is fragile. Stash when I ask for it, and leave `git stash drop`
to me. Never put a state-mutating git command inside an exploratory one-liner.

**To compare a before and after state**, generate a patch with `git diff HEAD`
and apply or unapply it with `git apply` and `git apply -R`, or take a backup
branch, or copy the files to the scratchpad.

**Rebase specifics.** Uncommitted work does not travel through a rebase, and
`--strategy-option=theirs` resolves conflicts without preserving it, so commit
first. "Keep remote for conflicts" means resolve the conflicting hunks and
nothing else: files that never conflicted stay. When I mention months of work,
take more backups than you think you need.

**Untracked files have no git backup at all.** Once gone they are gone: `rm -rf`
leaves no trash, no reflog, no recovery. Copy before you move or delete, and
list what you are about to touch first.

**macOS is case-insensitive.** `foo.md` and `FOO.md` are one file on APFS, so
copying both into one directory silently overwrites. Check first:
`ls -1 <dir>/ | tr '[:upper:]' '[:lower:]' | sort | uniq -d`.

**Outward-facing and irreversible actions wait for me**: creating or pushing a
tag, pushing to a remote, triggering a release, publishing an Artifact, replying
to a PR comment in my name. Say what you are about to do and why, then wait.

**Never drive the Mac with synthetic keystrokes.** osascript System Events sends
keys wherever focus happens to be, and a stray Escape has cancelled my work.

## Code

- Fix the root cause. What the compiler, linter, or type-checker reports is the
  work, so `eslint-disable` (I do not use eslint), `#[ignore]`, `-Wno-*`, and
  `__attribute__((unused))` are all off the table. A single `#[allow(...)]`
  carrying a comment that says why is the one exception, and only where the lint
  is genuinely wrong about this code. A "temporary" workaround with a TODO
  saying it is easy to swap later becomes permanent.
- A failing test is reporting a bug in the code. Fix the code. Weakening an
  assertion, skipping the test, or inverting it to match current behaviour all
  destroy the thing that was protecting you, so confirm the intent against the
  ticket or with me before changing what a test asserts. "Delete redundant code"
  never includes the test that proves the behaviour.
- Keep the complex solution when the problem is complex. Simplify only when I
  ask, never to make a build pass or a test go green.
- Read the primary source before designing against it: the library's own code,
  the API's rate-limit documentation, the ticket and its comments in full. This
  is for decisions that are expensive to undo, an API surface, a schema, a
  concurrency model. A one-line fix does not need a literature review, and a
  guess dressed as a decision does.
- Code that looks redundant is often load-bearing. Ask before "optimising"
  something whose cost looks unjustified; the reason is usually undocumented.
- Search for an existing implementation before adding one, and extend the
  surface that exists rather than opening a parallel one.
- The generated artifact is never the place to fix anything: extracted message
  catalogues, generated type declarations, bundles, lockfiles, build output,
  schema-generated code. Fix the source of truth or the build. When a build
  cannot see a new source, the answer is usually the entry graph or the config.
- Style comes from the surrounding code. Test fixtures name me rather than a
  teammate, so nobody else's name lands in committed test data.

**Comments in code you write.** The default is none. Leave existing comments
alone unless the change makes them wrong. A comment earns its place by carrying
the why the code cannot: a hidden constraint, a subtle invariant, a workaround for a
named bug, behaviour that surprises the reader. Anything a reader can infer from
the names and the surrounding code goes. That rules out doc blocks on
self-evident functions, props, types, and helpers, and it rules out narration
("Mirror the legacy ...", "Caller is responsible ...").

**Planning metadata belongs in the plan.** Phase and tier labels, migration step
numbers, ticket keys, commit SHAs, "reserved for a later change": all of it rots
in source and means nothing to whoever opens the file next. Put it in the commit
message, the PR, or the tracker. Describe what the code is and why it exists
today.

**CSS selectors survive a vendor rebuild or they are broken already.** A
content-hashed class from someone else's build (`:global(.modal_scroll--97abf)`,
`[class*="modal_"]`) changes on every release with no compile-time check. Reach
instead for the component's own `className` or slot props, a wrapper element you
own, the library's documented extension points, or an upstream issue. Typing
`:global(` at a hashed class means the structure is wrong; fix the structure.

## Public repos stay generic

Treat this as a release gate rather than a style preference.

Anything published under my own name (ferridriver and everything like it) uses
no names from private or client work: no company URLs, no `@company/...`
package specifiers, no `COMPANY_*` environment variables, no product names in
comments, no internal hostnames, no teammate names, no real addresses. Fixtures,
doc examples, and config samples all use neutral stand-ins: `acme`,
`example.com`, `APP_PASSWORD`, `API_TOKEN`.

Check before publishing, and again before any push that adds documentation or
fixtures:

```
python3 ~/.claude/mylint.py --private
```

Two traps make a careless cleanup worse than none. Replacing a bare company
name catches unrelated identifiers, so match specific phrases rather than the
word alone. And phrase replacement leaves grammar behind it ("a Company gateway"
becoming "a the gateway"), so read the result rather than trusting the
substitution.

Scrubbing history when something already landed means rewriting every commit,
so keep a mirror of the repository before starting and expect every SHA to
change.

**No emoji in code, documentation, or a commit message.** My own Slack and
review comments use them and should keep doing so.

## How I want work done

- Concise. Skip the preamble and the recap.
- **A question is a question.** When I ask for an estimate, a count, a delta, or
  a scope, answer it. Do not start implementing what the number described.
- **Done means verified.** Compiling, plumbed through, and existing tests still
  passing is not parity and not completion. Run the thing. Judge a test run by
  its exit code, since a piped `grep` masks failures.
- One `just ready` (or the project's equivalent) on the final state, scoped to
  what the change can actually break. No per-commit build checks, no
  verification worktrees, no `cargo check` per SHA.
- Stage whole files into logical commits. No hunk-by-hunk splitting. If two
  changes genuinely cannot separate at file level, say so in a sentence and
  commit them together.
- Before writing any concurrent or paging client, read the provider's
  rate-limit documentation, find the response headers exposing remaining quota
  and window reset, and pace off those at runtime. A guessed constant is
  unfalsifiable, and a shared quota means the blast radius is every other
  caller in the organisation.
  Where the provider publishes nothing, measure.
- Clone third-party sources to disk and read them from there rather than
  fetching and printing them into context.

## Writing

Measured against what I actually write, not a style guide.

**Commits.** Conventional prefix, subject under 72 characters, blank line, body.
The body names the mechanism and what it broke, then what now stops it coming
back. The shape, not the subject matter, is what this example is for:

> The PKI endpoint mapped Local onto dev, but the SPIFFE URI was built from the
> environment's own name. `cert -e local` therefore requested a dev-signed
> certificate claiming ns/test-local, which matches no Istio Authorization
> Policy, a certificate that issues cleanly and satisfies nothing.
>
> Both now come from vault_env_name, so they cannot disagree. Tests pin the
> values against create_laptop_ssl_certificate in security/vaultpkid, which this
> command reimplements, so a change upstream fails here.

`git diff` already lists the files. Three bullets is plenty; past that the body
has stopped explaining and started restating. Around 50 words, no headings, no
bold.

**Pull request descriptions.** Across 27 of my own merged PRs against 85 an
agent drafted, three things separate them and none appears in mine:

- **No markdown table.** Zero in mine, 1.6 per PR in the agent's. A change that
  seems to need a table needs a design doc.
- **No em-dash.** Zero in mine, 2.7 in the agent's. Use a comma, colon, period,
  or parentheses, whichever the sentence wants.
- **One heading at most.** Mine average 1.3, the agent stacks 3.1. A `## Summary`
  above four bullets is a label on a label.

Bullets are normal (I average ten a PR) and so is the occasional bold span. Aim
at 110 words rather than 180. Lead with what changed and why, link the ticket,
and stop.

`python3 ~/.claude/mylint.py --pr <file>` and `--commit` check
these, and `mylint.py <file>` catches my own spelling and run-ons. If that path
is gone, say so rather than skipping the check.

**Nothing I publish carries an AI signature**: no "Generated with Claude Code",
no `Co-Authored-By: Claude`, no robot emoji. That holds for commits, PR bodies,
comments, tickets, and messages alike.

**Review comments and Slack** follow the same shape: reason in public, stay
concrete, disagree by contrast rather than confrontation, no throat-clearing
opener.

**Anything written in my voice** (slides, docs, posts) carries no history the
audience does not share. Never narrate work from an assistant session as my
first-person anecdote; state the principle plainly instead. Introduce generic
concepts with neutral examples first, and keep my own tools, teammates, and
config out until an explicit "here is what I built" transition, in first person
singular.

## The tools on this machine

Generated by `install.sh` from what it found, so a tool named here is
installed and a tool that is not, is not.

For installed command usage, read [tools.local.md](tools.local.md) beside this
instructions file before using the tool.
