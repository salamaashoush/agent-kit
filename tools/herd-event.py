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
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
