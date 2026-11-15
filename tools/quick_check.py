"""Quick repo checks that need nothing installed (CI job "quick checks", and the pre-push hook).

    python tools/quick_check.py                 # check the repo's text files
    python tools/quick_check.py --needs-tests   # read changed file names on stdin, print true/false

1. No merge-conflict markers in tracked text files.
2. DEVLOG.md: no entry heading is repeated (a merge duplicated it), and none says "(with <AI tool>)".
3. --needs-tests: do the changed files include code, tests, data, or build config? If not (docs,
   the devlog, images), the slow test suite can be skipped.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A change under any of these needs the full test suite.
CODE_PREFIXES = ("signal2speech/", "tests/", "contracts/", "data/", "tools/", ".github/", ".githooks/")
CODE_FILES = ("pyproject.toml", "requirements-lock.txt", ".gitattributes", ".gitignore")
#: Never code, wherever they live.
DOC_SUFFIXES = (".md", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".svg")

TEXT_SUFFIXES = (".py", ".md", ".toml", ".txt", ".json", ".yml", ".yaml", ".csv", ".cfg", ".sh")
# Built from pieces so this file passes its own check.
MARKERS = tuple(ch * 7 for ch in "<>") + ("=" * 7,)


def needs_tests(paths) -> bool:
    for raw in paths:
        p = raw.strip().replace("\\", "/")
        if not p:
            continue
        if p.endswith(DOC_SUFFIXES) and not p.startswith(("tests/", "contracts/")):
            continue
        if p in CODE_FILES or p.startswith(CODE_PREFIXES):
            return True
        if p.endswith(".py"):
            return True
    return False


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def conflict_markers(files) -> list:
    problems = []
    for f in files:
        if f.suffix.lower() not in TEXT_SUFFIXES or not f.is_file():
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if line.startswith(MARKERS[:2]) or line == MARKERS[2]:
                problems.append(f"{f.relative_to(ROOT).as_posix()}:{i}: merge-conflict marker")
                break
    return problems


def devlog_problems(path: Path = ROOT / "DEVLOG.md") -> list:
    if not path.is_file():
        return []
    problems, seen = [], set()
    in_code = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("```"):
            in_code = not in_code
        if in_code or not line.startswith("## "):
            continue
        if not re.match(r"^## \d\d/\d\d/\d\d", line):
            continue                                   # a section heading, not an entry
        if re.search(r"\(with (claude|copilot|chatgpt|gpt)[^)]*\)", line, re.I):
            problems.append(f"DEVLOG.md:{i}: heading credits an AI tool (developer name only)")
        if line in seen:
            problems.append(f"DEVLOG.md:{i}: repeated heading (a merge duplicated an entry)")
        seen.add(line)
    return problems


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--needs-tests"]:
        print("true" if needs_tests(sys.stdin.read().splitlines()) else "false")
        return 0
    problems = conflict_markers(tracked_files()) + devlog_problems()
    for p in problems:
        print(p)
    print(f"quick checks: {'FAILED, ' + str(len(problems)) + ' problem(s)' if problems else 'passed'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
