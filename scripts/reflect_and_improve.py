"""
reflect_and_improve.py — analyzes Claude Code session transcripts for friction patterns
and produces a structured report with proposed AGENTS.md / Makefile improvements.

Usage:
    python scripts/reflect_and_improve.py [--sessions N] [--out REPORT.md]
"""

import json
import re
import sys
import os
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# ── helpers ────────────────────────────────────────────────────────────────────

FRICTION_PATTERNS = {
    "encoding": [
        re.compile(r"[ÄĹŻŚĆÓĄĘŃŹĆÿ]{2,}"),          # mojibake runs
        re.compile(r"U\+201[CD]|U\+2018|U\+2019"),    # smart-quote references
        re.compile(r"[“”‘’]"),     # literal smart quotes
        re.compile(r"UnicodeDecodeError|UnicodeEncodeError"),
        re.compile(r"codec can't (encode|decode)"),
    ],
    "test_skipped": [
        re.compile(r"(?i)nie uruchamia(ł|łem|łam)? test"),
        re.compile(r"(?i)bez testów|skip.*test|pomijam test"),
        re.compile(r"(?i)tests? (not run|skipped|omitted)"),
        re.compile(r"(?i)zadeklarowa.*zakończ.*bez.*test"),
    ],
    "git_error": [
        re.compile(r"(?i)fatal:|error: (pathspec|failed to|cannot)"),
        re.compile(r"(?i)merge conflict|CONFLICT \("),
        re.compile(r"(?i)detached HEAD|not a git repo"),
        re.compile(r"(?i)git reset --hard|force.?push"),
        re.compile(r"(?i)which (repo|branch|repository)"),
    ],
    "bash_error": [
        re.compile(r"(?i)command not found|No such file or directory"),
        re.compile(r"Exit code [1-9]"),
        re.compile(r"(?i)PermissionError|Access is denied"),
        re.compile(r"(?i)SyntaxError|IndentationError|NameError|AttributeError"),
        re.compile(r"Traceback \(most recent call last\)"),
    ],
    "regression": [
        re.compile(r"(?i)broke|regression|cofn|przywróć|przywracam|revert"),
        re.compile(r"(?i)to działało przed|przestało działać|znowu się psuje"),
        re.compile(r"(?i)broke.*after|after.*change.*broke"),
    ],
    "correction": [
        re.compile(r"(?i)^nie,?\s|^wrong\b|^błąd\b|^popraw\b"),
        re.compile(r"(?i)nie o to chodzi|nie tego chcia|zrozumia(ł|łeś) źle"),
        re.compile(r"(?i)nie tak|to nie jest (to|dobre|poprawne)"),
        re.compile(r"(?i)cofnij|undo|odwróć"),
    ],
    "layer_miss": [
        re.compile(r"(?i)JS (nie|not) (updated|zaktualizowany|odzwierciedla)"),
        re.compile(r"(?i)backend (ok|works?) but (frontend|JS|UI)"),
        re.compile(r"(?i)brakuje.*renderowania|render.*nie działa"),
        re.compile(r"(?i)payload.*ok.*widok.*nie|widok.*nie.*payload"),
    ],
    "handoff_needed": [
        re.compile(r"(?i)gdzie byliśmy|gdzie skończyliśmy|co zostało"),
        re.compile(r"(?i)kontynuuj|resume|pick up where"),
        re.compile(r"(?i)przypomnij (mi |)co|what (was|were) we"),
    ],
}

CATEGORY_LABELS = {
    "encoding":       "Encoding / smart-quote issues",
    "test_skipped":   "Tests skipped before declaring done",
    "git_error":      "Git command errors or ambiguity",
    "bash_error":     "Bash / shell execution errors",
    "regression":     "Regressions introduced",
    "correction":     "User corrections (wrong direction)",
    "layer_miss":     "Layer miss (backend OK, JS/CSS not updated)",
    "handoff_needed": "Session context lost (handoff needed)",
}


def extract_text(entry: dict) -> list[str]:
    """Return all text snippets from a single JSONL entry."""
    texts = []

    # queue-operation: content is a plain string
    if entry.get("type") == "queue-operation":
        c = entry.get("content", "")
        if isinstance(c, str):
            texts.append(c)
        return texts

    msg = entry.get("message", {})
    content = msg.get("content", entry.get("content", []))

    if isinstance(content, str):
        texts.append(content)
        return texts

    if not isinstance(content, list):
        return texts

    for block in content:
        if not isinstance(block, dict):
            continue
        t = block.get("type", "")
        if t == "text":
            texts.append(block.get("text", ""))
        elif t == "tool_result":
            for sub in block.get("content", []):
                if isinstance(sub, dict) and sub.get("type") == "text":
                    texts.append(sub.get("text", ""))
        elif t == "tool_use":
            inp = block.get("input", {})
            if isinstance(inp, dict):
                texts.append(json.dumps(inp, ensure_ascii=False))

    return texts


def load_session(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def detect_friction(text: str) -> list[str]:
    found = []
    for category, patterns in FRICTION_PATTERNS.items():
        for pat in patterns:
            if pat.search(text):
                found.append(category)
                break
    return found


def analyze_sessions(session_dir: Path, n: int = 10) -> dict:
    files = sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]

    totals: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    session_counts: list[dict] = []

    for f in files:
        entries = load_session(f)
        session_hits: Counter = Counter()
        for entry in entries:
            for text in extract_text(entry):
                for cat in detect_friction(text):
                    totals[cat] += 1
                    session_hits[cat] += 1
                    if len(examples[cat]) < 3:
                        snippet = text[:200].replace("\n", " ")
                        examples[cat].append(f"`{snippet}`")
        session_counts.append({"file": f.name[:8], "hits": dict(session_hits)})

    return {"totals": totals, "examples": examples, "sessions": session_counts, "files_analyzed": len(files)}


# ── report ─────────────────────────────────────────────────────────────────────

AGENTS_PROPOSALS = {
    "encoding": (
        "## String Handling (reinforced)",
        "- **Encoding gate:** before any `Edit` or `Write` that touches a `.py` file, "
        "verify the file can be read with `open(f, encoding='utf-8')`. "
        "Abort if encoding fails — do not silently replace characters.\n"
        "- Smart quotes (U+201C/D, U+2018/9) are *data* in this repo (inch notation). "
        "NEVER use them as Python string delimiters.",
    ),
    "test_skipped": (
        "## Testing (reinforced)",
        "- Running `pytest` is **not optional** before declaring any task complete — "
        "even for 'trivial' one-line changes. The PostToolUse hook enforces this; "
        "do not suppress hook output.",
    ),
    "git_error": (
        "## Git Workflow (reinforced)",
        "- Before any destructive git command (`reset --hard`, `push --force`, `checkout .`), "
        "print `git remote -v` AND `git branch` so the repo identity is unambiguous.\n"
        "- Default branch-alignment strategy: `git reset --hard <sha>`, not merge.",
    ),
    "layer_miss": (
        "## Layer Checklist (new)",
        "- Every change must be traced through ALL affected layers before closing:\n"
        "  1. Data model / migration\n"
        "  2. Backend route / payload\n"
        "  3. JS rendering (`app.js` section)\n"
        "  4. CSS / template\n"
        "  5. Tests",
    ),
    "handoff_needed": (
        "## Handoff Protocol (new)",
        "- For any task spanning >1 reply, maintain `HANDOFF.md` with: current goal, "
        "files changed, hypotheses tested, what's pending, how to verify. "
        "Update after every significant step.",
    ),
    "correction": (
        "## Zasady pracy (reinforced)",
        "- If the user says 'nie', 'wrong', 'cofnij', or equivalent: **stop, revert last "
        "change, ask for clarification** before attempting a new approach.",
    ),
}

MAKEFILE_PROPOSALS = {
    "encoding": (
        "safe-edit",
        "python -c \"import sys; [open(f,'r',encoding='utf-8').read() for f in sys.argv[1:]]\"",
        "Validate UTF-8 encoding of edited files before committing",
    ),
    "test_skipped": (
        "check",
        "make lint && make test-fast",
        "Run lint + fast tests — use instead of bare pytest for quick pre-commit check",
    ),
}

FRICTION_ADVICE = {
    "encoding":       "Add `make safe-edit` and reinforce String Handling rule in AGENTS.md.",
    "test_skipped":   "Reinforce Testing rule; PostToolUse hook already helps but rule needs to be louder.",
    "git_error":      "Add repo-identity print step before destructive git commands.",
    "bash_error":     "No systemic fix — individual command errors. Monitor for patterns.",
    "regression":     "Layer Checklist in AGENTS.md and call-site search before closing.",
    "correction":     "Stop-and-revert rule when user corrects direction.",
    "layer_miss":     "Layer Checklist protocol covers this.",
    "handoff_needed": "HANDOFF.md protocol covers this.",
}


def build_report(analysis: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    totals = analysis["totals"]
    examples = analysis["examples"]
    n = analysis["files_analyzed"]

    lines = [
        f"# Friction Analysis Report — {now}",
        f"_Sessions analyzed: {n}_\n",
        "## 1. Friction Pattern Counts",
        "",
        "| Category | Hits | Advice |",
        "|----------|-----:|--------|",
    ]
    for cat, label in CATEGORY_LABELS.items():
        count = totals.get(cat, 0)
        advice = FRICTION_ADVICE.get(cat, "")
        lines.append(f"| {label} | {count} | {advice} |")

    lines += ["", "## 2. Example Snippets per Category", ""]
    for cat, label in CATEGORY_LABELS.items():
        exs = examples.get(cat, [])
        if exs:
            lines.append(f"### {label}")
            for ex in exs:
                lines.append(f"- {ex}")
            lines.append("")

    lines += ["## 3. Proposed AGENTS.md Updates", ""]
    active_proposals = [k for k in AGENTS_PROPOSALS if totals.get(k, 0) > 0]
    if not active_proposals:
        lines.append("_No friction detected — no updates proposed._")
    for cat in active_proposals:
        section, body = AGENTS_PROPOSALS[cat]
        lines.append(f"### {section}")
        lines.append(body)
        lines.append("")

    lines += ["## 4. Proposed Makefile Additions", ""]
    active_make = [k for k in MAKEFILE_PROPOSALS if totals.get(k, 0) > 0]
    if not active_make:
        lines.append("_No Makefile changes needed._")
    for cat in active_make:
        target, recipe, desc = MAKEFILE_PROPOSALS[cat]
        lines.append(f"**`make {target}`** — {desc}")
        lines.append(f"```makefile\n{target}:\n\t{recipe}\n```")
        lines.append("")

    lines += [
        "## 5. Metrics (cumulative)",
        "",
        f"| Date | Sessions | Total Friction Hits |",
        f"|------|----------|---------------------|",
        f"| {now} | {n} | {sum(totals.values())} |",
        "",
        "_Re-run `python scripts/reflect_and_improve.py` after each session batch "
        "to track friction reduction over time._",
    ]

    return "\n".join(lines)


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--out", default="FRICTION_REPORT.md")
    args = parser.parse_args()

    project_slug = "D--OneDrive---KBJ-S-A-Dokumenty-GitHub-OPR"
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    session_dir = Path(appdata).parent / "Roaming" / ".claude" / "projects" / project_slug

    # fallback: try USERPROFILE
    if not session_dir.exists():
        session_dir = Path(os.environ.get("USERPROFILE", "~")) / ".claude" / "projects" / project_slug

    if not session_dir.exists():
        print(f"ERROR: session dir not found: {session_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading up to {args.sessions} sessions from {session_dir} …", file=sys.stderr)
    analysis = analyze_sessions(session_dir, args.sessions)
    print(f"Files analyzed: {analysis['files_analyzed']}", file=sys.stderr)
    for cat, count in analysis["totals"].most_common():
        print(f"  {CATEGORY_LABELS[cat]}: {count}", file=sys.stderr)

    report = build_report(analysis)

    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written → {out_path}", file=sys.stderr)
    print(report)


if __name__ == "__main__":
    main()
