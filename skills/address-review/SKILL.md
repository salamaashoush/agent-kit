---
name: address-review
version: 1.1.0
description: Address reviewer feedback on your own pull request: implement fixes, push, and reply to each thread. Use when the user says "address the review comments", "respond to reviewer feedback", "fix the PR comments on my PR". You are the PR author here, not the reviewer.
---

# Address Review

You are the author of this pull request, addressing reviewer feedback. Work through every review thread listed in the prompt:

1. UNDERSTAND each comment in context: read the file at the referenced line and enough surrounding code to judge whether the reviewer is right.
2. DECIDE per thread: implement the requested change, or, where the reviewer is mistaken or the request is out of scope, prepare a respectful, technically grounded reply explaining the reasoning. Threads that later commits or replies already addressed get noted as such and skipped. An ambiguous comment gets the most reasonable reading, said out loud in the reply.
3. IMPLEMENT the accepted changes on the current branch. Follow the project's conventions, run the project's verify command (build, lint, tests), and fix failures at the root.
4. COMMIT following the project's commit convention and push to the PR branch.
5. REPLY to each thread via the GitHub CLI once the user has confirmed the set. Reply to a line comment thread with:
   ```
   gh api repos/{owner}/{repo}/pulls/{pr}/comments/{comment_id}/replies -f body='...'
   ```
   Keep replies short: what changed (with the commit sha) or why you disagree.

## Rules
- The branch only ever gains commits, so the reviewer's read of the history stays intact.
- A comment about a linter or type-checker is answered by fixing the cause or by pushing back, and the checker stays on either way.
- Summarize at the end: threads fixed, threads pushed back on, threads skipped as already handled.
