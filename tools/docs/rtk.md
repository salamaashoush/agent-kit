# RTK - Rust Token Killer

**Usage**: Token-optimized CLI proxy (cuts up to 90% of bash output)

## Meta Commands (always use rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze Claude Code history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Installation Verification

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
```

**Name collision**: If `rtk gain` fails, you may have reachingforthejack/rtk (Rust Type Kit) installed instead.

## Hook-Based Usage

Supported shell commands are rewritten by the PreToolUse hook in Claude Code
and Codex. Example: `git status` → `rtk git status` (transparent, 0 tokens
overhead). `install.sh` wires that hook when `rtk` is on PATH.

In Claude a rewrite runs without a prompt only when the original command
matches a `Bash(...)` allow rule; otherwise Claude asks about `rtk ...`. Codex
runs `rtk hook codex`, and its own approval and sandbox still apply to the
rewritten command. After a hook change, approve it in Codex's `/hooks`.

Two rewrites change what a command means, so `install.sh` keeps them out
through rtk's own `[hooks] exclude_commands`: `grep` with `-h` (rtk's grep
reads it as its help flag and prints usage instead of matches) and `ls` with
`-l` (rtk drops the owner and dates). Those run as the plain command. A
truncated result names its full copy, or `rtk proxy <cmd>` runs a command
unfiltered.

`rtk --help` lists the rest.
