#!/usr/bin/env python3
"""Lint a draft for the two things that actually go wrong in Salama's writing,
then hand it to unslop's scanners for the AI tells.

    python3 mylint.py draft.md
    pbpaste | python3 mylint.py
    python3 mylint.py --pr body.md      # also check the PR-description tells
    python3 mylint.py --commit msg.txt  # ...or the commit-message ones
    git show -s --format=%B HEAD | python3 mylint.py --commit

Measured over 22k words of his own review comments: seven misspellings account
for 96% of spelling errors, and 4% of segments run past 60 words. Everything
else in that corpus already scans clean, so this checks those two and stops.
"""

import json
import pathlib
import re
import subprocess
import sys

UNSLOP = pathlib.Path("/Users/sashoush/Workspace/unslop/scripts")

# Frequency in his corpus is the comment; the count is why the list is this short.
MISSPELLINGS = {
    "dont": "don't",           # 48
    "wont": "won't",           # 29
    "diffrent": "different",   # 16
    "anther": "another",       # 12
    "cant": "can't",           # 8
    "seperate": "separate",    # 6
    "becasue": "because",      # 4
    "doesnt": "doesn't",
    "didnt": "didn't",
    "isnt": "isn't",
    "thats": "that's",
    "teh": "the",
    "recieve": "receive",
    "occured": "occurred",
    "untill": "until",
    "alot": "a lot",
}

LONG = 60          # words; p95 of his corpus is 56, so this flags the tail
MANY_COMMAS = 4    # a long segment with this many commas is doing a period's job


def segments(text: str):
    """Prose segments only. Tables, headings, and list scaffolding are structure,
    and counting a five-row table as one 109-word sentence is noise."""
    body = re.sub(r"```.*?```", " ", text, flags=re.S)
    body = re.sub(r"(?m)^\s*\|.*$", " ", body)      # table rows
    body = re.sub(r"(?m)^\s*#{1,6}\s.*$", " ", body)  # headings
    body = re.sub(r"(?m)^\s*[-*+]\s", "", body)     # list bullets, keep the text
    for raw in re.split(r"(?<=[.!?])\s+|\n{2,}", body):
        s = raw.strip()
        if s:
            yield s


def check_spelling(text: str):
    for match in re.finditer(r"\b[a-zA-Z]+\b", text):
        fix = MISSPELLINGS.get(match.group().lower())
        if fix:
            line = text.count("\n", 0, match.start()) + 1
            yield line, match.group(), fix


def check_runons(text: str):
    for s in segments(text):
        n = len(s.split())
        if n >= LONG:
            commas = s.count(",")
            shape = "comma-splice" if commas >= MANY_COMMAS else "long"
            yield n, commas, shape, s


# Measured over 27 of his merged PRs against 85 an agent drafted: he has never
# used a table or an em-dash in a PR description, and averages 1.3 headings to
# the agent's 3.1. Those three plus the length gap are the whole tell.
PR_LIMITS = {"tables": 0, "em_dashes": 0, "headings": 1, "words": 160}


def check_pr(text: str):
    counts = {
        "tables": len(re.findall(r"(?m)^\s*\|", text)),
        "em_dashes": text.count("\u2014") + len(re.findall(r"\s--\s", text)),
        "headings": len(re.findall(r"(?m)^#{2,6}\s", text)),
        "words": len(text.split()),
    }
    for key, limit in PR_LIMITS.items():
        if counts[key] > limit:
            yield key, counts[key], limit


# His 2026 commit bodies explain a mechanism and its consequence in prose; his
# 2025 ones dumped the diff as 6.4 bullets. The later shape is the target, so
# these thresholds guard against sliding back rather than forward.
COMMIT_SUBJECT_MAX = 72
COMMIT_BULLETS_MAX = 3
CONVENTIONAL = re.compile(r"^(feat|fix|docs|refactor|test|chore|perf|build|ci|style|revert)(\(.+\))?!?: .")


def check_commit(text: str):
    lines = text.strip().splitlines()
    subject = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip()

    if not CONVENTIONAL.match(subject):
        yield f"subject is not conventional: {subject[:60]!r}"
    if len(subject) > COMMIT_SUBJECT_MAX:
        yield f"subject is {len(subject)} chars (keep it under {COMMIT_SUBJECT_MAX})"
    if len(lines) > 1 and lines[1].strip():
        yield "no blank line between subject and body"

    bullets = len(re.findall(r"(?m)^\s*[-*]\s", body))
    if bullets > COMMIT_BULLETS_MAX:
        yield f"{bullets} bullets: a body that lists the diff says what, not why"
    if re.search(r"(?m)^#{1,6}\s", body):
        yield "headings in a commit body"
    if "\u2014" in text:
        yield "em-dash"
    for signature in ("Co-Authored-By: Claude", "Generated with", "\U0001f916"):
        if signature in text:
            yield f"AI signature: {signature!r}"


def scan(script: str, text: str):
    out = subprocess.run(
        ["python3", str(UNSLOP / script)], input=text, capture_output=True, text=True
    ).stdout
    try:
        return json.loads(out)
    except ValueError:
        return {}


def main() -> int:
    args = sys.argv[1:]
    as_pr = "--pr" in args
    as_commit = "--commit" in args
    args = [a for a in args if a not in ("--pr", "--commit")]
    if args:
        text = pathlib.Path(args[0]).read_text()
        where = args[0]
    else:
        text = sys.stdin.read()
        where = "stdin"

    spelling = list(check_spelling(text))
    runons = list(check_runons(text))
    phrases = scan("banned_phrase_scan.py", text)
    structure = scan("structure_scan.py", text)

    print(f"{where}: {len(text.split())} words\n")

    if spelling:
        print(f"spelling ({len(spelling)})")
        for line, found, fix in spelling:
            print(f"  L{line}: {found} -> {fix}")
        print()

    if runons:
        print(f"sentences past {LONG} words ({len(runons)})")
        for n, commas, shape, s in runons:
            print(f"  {n}w, {commas} commas, {shape}")
            print(f"    {s[:110]}{'...' if len(s) > 110 else ''}")
            print("    put a period where you would take a breath")
        print()

    commit = list(check_commit(text)) if as_commit else []
    if commit:
        print(f"commit message ({len(commit)})")
        for c in commit:
            print(f"  {c}")
        print("  a body earns its place by naming the mechanism and what it broke,")
        print("  then what now stops it coming back")
        print()

    pr = list(check_pr(text)) if as_pr else []
    if pr:
        print(f"PR description ({len(pr)})")
        for key, got, limit in pr:
            noun = key.replace("_", " ")
            print(f"  {noun}: {got} (he writes {limit})")
        print("  bullets and the occasional bold span are fine; tables, em-dashes")
        print("  and stacked headings are what mark it agent-written")
        print()

    tells = phrases.get("violations", [])
    if tells:
        print(f"AI tells ({len(tells)})")
        for v in tells:
            print(f"  L{v.get('line_number')}: \"{v.get('phrase')}\" [{v.get('category')}/{v.get('severity')}]")
        print()

    flags = structure.get("flags", [])
    if flags:
        print(f"structure ({len(flags)})")
        for f in flags:
            print(f"  {f.get('metric')}: {f.get('suggestion')}")
        print()

    metrics = structure.get("metrics", {})
    if metrics:
        print(f"em-dash/1k {metrics.get('em_dash_per_1k', 0):.1f}   "
              f"mean sentence {metrics.get('sentence_mean_len', 0):.0f}w")

    total = len(spelling) + len(runons) + len(tells) + len(flags) + len(pr) + len(commit)
    print(f"\n{total} finding{'' if total == 1 else 's'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
