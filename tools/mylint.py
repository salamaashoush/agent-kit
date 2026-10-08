#!/usr/bin/env python3
"""Lint a draft for the two things that actually go wrong in Salama's writing,
then hand it to unslop's scanners for the AI tells.

    python3 mylint.py draft.md
    pbpaste | python3 mylint.py
    python3 mylint.py --pr body.md      # also check the PR-description tells
    python3 mylint.py --private         # secrets, public IPs, emails, private names
    python3 mylint.py --private --history   # ...in every commit and message, before publishing
    python3 mylint.py --commit msg.txt  # ...or the commit-message ones
    git show -s --format=%B HEAD | python3 mylint.py --commit

Measured over 22k words of his own review comments: seven misspellings account
for 96% of spelling errors, and 4% of segments run past 60 words. Everything
else in that corpus already scans clean, so this checks those two and stops.
"""

import ipaddress
import json
import os
import pathlib
import re
import subprocess
import sys

# The vendored copy, so a fresh clone scans without a second checkout.
UNSLOP = pathlib.Path(__file__).resolve().parent.parent / "skills" / "unslop" / "scripts"

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


# The list itself lives outside this repo: writing a private name here in order
# to catch it would publish it, so only the shape is versioned, in
# config/private-names.example.json.
PRIVATE_NAMES = pathlib.Path(
    os.environ.get("MYLINT_PRIVATE_NAMES")
    or pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    / "private-names.json"
)

# Built in, so a machine with no names list still catches what leaks the same
# way for everyone. Each pattern is specific enough that a hit is worth reading.
SECRETS = [
    (r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----", "private key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{50,}\b", "GitHub token"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bsk-ant-[A-Za-z0-9_-]{20,}", "Anthropic key"),
    (r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}", "OpenAI key"),
    (r"\bAIza[0-9A-Za-z_-]{35}\b", "Google API key"),
    (r"\b[rs]k_live_[0-9A-Za-z]{20,}", "Stripe live key"),
    (r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b[\"']?"
     r"\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']", "credential"),
]
# A credential whose value is one of these is a stand-in, not a secret.
PLACEHOLDER = re.compile(r"(?i)example|changeme|placeholder|dummy|fixture|redacted|xxx|"
                         r"your[_-]|\$\{|\{\{|<[^>]+>|\*\*\*")

IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
# Public resolvers appear in every network doc and identify nobody.
PUBLIC_RESOLVERS = {"1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112"}

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
# Addresses that reach nobody: the reserved example domains, noreply senders,
# and the git@ user of an SSH remote.
PUBLIC_EMAIL = re.compile(r"(?i)^(?:git|no-?reply)@|@(?:[a-z0-9-]+\.)*example\.(?:com|org|net)$"
                          r"|@users\.noreply\.github\.com$|\.(?:example|test|invalid|localhost)$")


def private_rules():
    """(patterns, allow), or None when this machine has no list to check against.

    A pattern is deliberately specific. Matching a bare company name also hits
    the identifiers that merely contain it, which is how a careless sweep turns
    into a bad diff, so `allow` carries the substrings that clear a line."""
    try:
        rules = json.loads(PRIVATE_NAMES.read_text())
    except FileNotFoundError:
        return None
    except ValueError as err:
        sys.exit(f"{PRIVATE_NAMES} is not valid JSON ({err})")
    patterns = [(entry["match"], entry["why"]) for entry in rules.get("patterns", [])]
    return patterns, tuple(rules.get("allow", ()))


def line_findings(line: str, patterns, allow):
    """What on this line should not be published, first finding only."""
    if any(ok in line for ok in allow):
        return None
    for pattern, why in SECRETS:
        found = re.search(pattern, line)
        if found and not (found.groups() and PLACEHOLDER.search(found.group(1))):
            return f"{why}: {found.group()[:40]}"
    for match in IPV4.finditer(line):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        # is_global is false for the private and documentation ranges; a
        # multicast group such as SSDP's is a protocol constant, not a host.
        if address.is_global and not address.is_multicast and match.group() not in PUBLIC_RESOLVERS:
            return f"public IP address: {match.group()}"
    for match in EMAIL.finditer(line):
        if not PUBLIC_EMAIL.search(match.group()):
            return f"email address: {match.group()}"
    for pattern, why in patterns:
        found = re.search(pattern, line)
        if found:
            return f"{why}: {found.group()}"
    return None


def tracked_files(root: str = "."):
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [f for f in out.stdout.split("\0") if f]


def check_private(root, patterns, allow):
    files = tracked_files(root)
    if not files:
        yield None, 0, "not a git repository, or no tracked files", ""
        return
    for name in files:
        path = pathlib.Path(root) / name
        try:
            text = path.read_text(errors="strict")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable
        for number, line in enumerate(text.splitlines(), 1):
            why = line_findings(line, patterns, allow)
            if why:
                yield name, number, why, line.strip()[:90]


def check_history(root, patterns, allow):
    """Every line any commit added, and every commit message. Publishing a repo
    publishes its history, so a leak removed from the tree still counts."""
    log = subprocess.run(["git", "log", "--all", "-p", "--no-color", "--format=COMMIT %h%n%B"],
                         cwd=root, capture_output=True, text=True, errors="replace")
    if log.returncode != 0:
        yield None, 0, "not a git repository", ""
        return
    commit, where = "?", "(message)"
    for line in log.stdout.splitlines():
        if line.startswith("COMMIT "):
            commit, where = line.split()[1], "(message)"
            continue
        if line.startswith("+++ b/"):
            where = line[6:]
            continue
        if line.startswith(("diff --git", "index ", "--- ", "@@", "+++ ")):
            continue
        if where != "(message)":
            if not line.startswith("+"):
                continue
            line = line[1:]
        why = line_findings(line, patterns, allow)
        if why:
            yield f"{commit} {where}", 0, why, line.strip()[:90]


WARNED = set()


def warn(message: str):
    if message not in WARNED:
        WARNED.add(message)
        print(f"mylint: {message}", file=sys.stderr)


def scan(script: str, text: str):
    """A scanner that cannot run is reported. Silence here once meant a draft
    came back clean because the scripts were not where this file expected."""
    path = UNSLOP / script
    if not path.exists():
        warn(f"unslop scanners missing at {UNSLOP}, AI-tell checks skipped")
        return {}
    done = subprocess.run([sys.executable, str(path)], input=text,
                          capture_output=True, text=True)
    try:
        return json.loads(done.stdout)
    except ValueError:
        detail = done.stderr.strip().splitlines()
        warn(f"{script} returned nothing: {detail[-1] if detail else 'no output'}")
        return {}


def report_private(args) -> int:
    history = "--history" in args
    args = [a for a in args if a != "--history"]
    rules = private_rules()
    if rules is None:
        print(f"no private names list at {PRIVATE_NAMES}; built-in checks only")
        print("(copy config/private-names.example.json there to add your own names)\n")
        rules = ([], ())
    root = args[0] if args else "."
    hits = list((check_history if history else check_private)(root, *rules))
    if hits and hits[0][0] is None:
        print(hits[0][2])
        return 0
    for name, number, why, line in hits:
        print(f"{name}:{number}  {why}" if number else f"{name}  {why}")
        print(f"    {line}")
    scope = "commits and messages" if history else "tracked files"
    print(f"\n{len(hits)} private finding{'' if len(hits) == 1 else 's'} in {scope}")
    if hits:
        print("replace with a neutral stand-in (acme, example.com, 203.0.113.10,")
        print("APP_PASSWORD) and read the result: replacement leaves grammar behind it")
    return 1 if hits else 0


def main() -> int:
    args = sys.argv[1:]
    if "--private" in args:
        return report_private([a for a in args if a != "--private"])
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
