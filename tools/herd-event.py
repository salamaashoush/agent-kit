#!/usr/bin/env python3
"""Record one session event, so watching is not polling.

Claude Code hands a hook its event as JSON on stdin. Appended here as one line
per event, `herd watch` learns that a session blocked the moment it did rather
than on its next poll.

Never fails and never blocks: a hook that raises interrupts the session it was
only supposed to observe.
"""

import json
import os
import sys
import time

EVENTS = os.path.expanduser("~/.herdr/events.jsonl")
KEEP = ("session_id", "cwd", "hook_event_name", "notification_type", "message", "title")
# Every turn of every session appends a line, forever. Past CAP the file is cut
# to its newest KEPT bytes. `herd watch` reads by offset and restarts from the
# end of a file that shrank below it, so a cut costs it at most the events
# written before its next poll.
CAP = 1 << 20
KEPT = CAP // 2


def trim() -> None:
    """Cut the log back to its newest lines. Another session appending between
    the read and the replace loses that one line, once per megabyte."""
    if os.path.getsize(EVENTS) <= CAP:
        return
    with open(EVENTS, "rb") as recorded:
        recorded.seek(-KEPT, os.SEEK_END)
        tail = recorded.read()
    tail = tail[tail.find(b"\n") + 1:]
    temporary = f"{EVENTS}.{os.getpid()}.tmp"
    with open(temporary, "wb") as out:
        out.write(tail)
    os.replace(temporary, EVENTS)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    line = {"at": time.time()}
    line.update({key: payload[key] for key in KEEP if payload.get(key) is not None})
    line.setdefault("hook_event_name", os.environ.get("CLAUDE_HOOK_EVENT", "unknown"))
    line.setdefault("cwd", os.getcwd())

    try:
        os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
        # O_APPEND makes a line-sized write atomic, which is what keeps two
        # sessions finishing at once from interleaving into one broken line.
        with open(EVENTS, "a") as events:
            events.write(json.dumps(line) + "\n")
        trim()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
