"""Release check for the judging build (#10, #35, #39, #42). Run it from the repo root on the
exact revision you plan to submit or freeze:

    python tools/release_check.py                  # every check (about a minute)
    python tools/release_check.py --quick          # skip pytest and the offline app runs
    python tools/release_check.py --all-branches   # also scan every branch's history for secrets

It checks the checked-out revision for secrets in its history, risky tracked files, raw EEG
ignore rules, and commit author emails. It also runs the OpenOrbit data check, pytest, and two
app runs with every network call blocked. Each check prints PASS, WARN, or FAIL. It never
prints a matched secret value or an email address. The exit code is 1 if any check fails.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = {
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI-style key": r"\bsk-[A-Za-z0-9]{20,}",
    "GitHub token": r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}",
    "AWS key ID": r"\bAKIA[0-9A-Z]{16}\b",
    "Google API key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "Slack token": r"\bxox[baprs]-[A-Za-z0-9\-]{10,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "hardcoded secret": r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]",
}
# Never allowed in git: credentials and raw EEG formats.
FORBIDDEN_FILES = re.compile(r"(?i)(^|/)(\.env(\.(?!example$)[^/]*)?|secrets?\.[^/]*)$|"
                             r"\.(pem|key|pfx|p12|h5|hdf5|edf|bdf|gdf|xdf|fif|mat)$")
# Allowed, but a person should look before the repo goes public.
REVIEW_FILES = re.compile(r"(?i)\.(wav|mp3|mp4|mov|mkv|zip|npy|npz)$")
# Where g.Pype and the evidence view (#48) write raw EEG. All must be gitignored.
EEG_SAMPLES = ["recordings/evidence_20261114_170000/HybridBlack.h5", "recordings/x/Marker.h5",
               "run_20261114/source.h5", "x.hdf5", "x.edf", "x.bdf", "x.gdf", "x.xdf", "x.fif",
               "x.mat", "eeg-recordings/a.csv", "eeg-raw/a.csv", ".env", ".env.local"]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Runs the real app (#4) with every network call blocked inside Python.
OFFLINE_APP = (
    "import socket, sys\n"
    "def blocked(*a, **k):\n"
    "    raise RuntimeError('NETWORK ACCESS ATTEMPTED')\n"
    "socket.socket.connect = socket.socket.connect_ex = blocked\n"
    "socket.create_connection = socket.getaddrinfo = blocked\n"
    "from signal2speech.app import main\n"
    "sys.exit(main(sys.argv[1:]))\n"
)

results: List[Tuple[str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name))
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""), flush=True)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def run(args: List[str], env=None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)


def check_revision() -> None:
    head = git("rev-parse", "HEAD").strip()
    dirty = git("status", "--porcelain").strip()
    if dirty:
        report("WARN", "revision", f"{head[:12]} has uncommitted changes; check a clean checkout")
    else:
        report("PASS", "revision", f"{head[:12]} (clean)")


def check_secrets(rev: str) -> None:
    """Scan every added or removed line in the history with Python regexes. (git's own -G
    takes POSIX regexes, which can't express these patterns, and fails quietly.)"""
    compiled = {name: re.compile(pattern) for name, pattern in SECRET_PATTERNS.items()}
    hits, commit, path = set(), "", ""
    for line in git("log", "-p", "--no-color", "--format=commit %h", rev).splitlines():
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1]
        elif line[:1] in ("+", "-") and not line.startswith(("+++", "---")):
            hits.update(f"{name} in {commit}:{path}" for name, rx in compiled.items() if rx.search(line))
    scope = "all branches" if rev == "--all" else "this revision's history"
    if hits:
        report("FAIL", "secrets in history", "; ".join(sorted(hits)[:10]) + " (review those commits)")
    else:
        report("PASS", "secrets in history", f"no secret-shaped strings in {scope}")


def check_tracked_files() -> None:
    forbidden, review = [], []
    for line in git("ls-tree", "-r", "-l", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        size = meta.split()[3]
        if FORBIDDEN_FILES.search(path):
            forbidden.append(path)
        elif REVIEW_FILES.search(path) or (size.isdigit() and int(size) > 1_000_000):
            review.append(path)
    if forbidden:
        report("FAIL", "tracked files", "remove from git: " + ", ".join(forbidden))
    elif review:
        report("WARN", "tracked files", "media, archives, or files over 1 MB to review: " + ", ".join(review))
    else:
        report("PASS", "tracked files", "no credentials, raw EEG, media, or files over 1 MB")


def check_eeg_ignored() -> None:
    ignored = set(git("check-ignore", "--no-index", *EEG_SAMPLES).split())
    missing = [p for p in EEG_SAMPLES if p not in ignored]
    if missing:
        report("FAIL", "raw EEG ignore rules", "not gitignored: " + ", ".join(missing))
    else:
        report("PASS", "raw EEG ignore rules", f"all {len(EEG_SAMPLES)} sample recording and .env paths are ignored")


def check_emails() -> None:
    authors = set()
    for line in git("log", "--format=%an|%ae", "HEAD").splitlines():
        name, _, email = line.partition("|")
        if "noreply" not in email:
            authors.add(name)
    in_files = []
    for spec in git("grep", "-I", "-l", "-E", EMAIL.pattern, "HEAD").splitlines():  # "HEAD:path"
        found = EMAIL.findall(git("show", spec))
        if any("noreply" not in e and "example" not in e for e in found):
            in_files.append(spec.split(":", 1)[1])
    if in_files:
        report("WARN", "email addresses", "in tracked files: " + ", ".join(in_files))
    if authors:
        report("WARN", "commit author emails", "personal (not noreply) address in history for: "
               + ", ".join(sorted(authors)) + ". Public if the repo goes public.")
    if not in_files and not authors:
        report("PASS", "email addresses", "none in files; all commit authors use noreply")


def check_data() -> None:
    r = run([sys.executable, "data/openorbit/build_dataset.py", "--verify-only"])
    last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    report("PASS" if r.returncode == 0 else "FAIL", "OpenOrbit data (#29)", last)


def check_pytest() -> None:
    r = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    report("PASS" if r.returncode == 0 else "FAIL", "pytest", last)


def check_offline_app() -> None:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    if sys.platform == "win32":
        env.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    with tempfile.TemporaryDirectory() as tmp:
        for keys, action in (("2,1", "compare_air_quality"), ("1,1", "show_satellite")):
            shot = str(Path(tmp) / f"{action}.png")
            r = run([sys.executable, "-c", OFFLINE_APP, "--input", "keyboard", "--keys", keys,
                     "--mute", "--screenshot", shot], env=env, timeout=120)
            out = r.stdout + r.stderr
            maps, speaks = out.count(f"OUTPUT map: {action}()"), out.count("OUTPUT speak:")
            ok = (r.returncode == 0 and maps == 1 and speaks == 1
                  and "NETWORK ACCESS ATTEMPTED" not in out and Path(shot).is_file())
            detail = f"keys {keys}: {maps} map action, {speaks} spoken line, exit {r.returncode}"
            report("PASS" if ok else "FAIL", f"offline app: {action}", detail)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip pytest and the offline app runs")
    parser.add_argument("--all-branches", action="store_true",
                        help="scan the history of every local and fetched branch for secrets")
    args = parser.parse_args(argv)
    check_revision()
    check_secrets("--all" if args.all_branches else "HEAD")
    check_tracked_files()
    check_eeg_ignored()
    check_emails()
    check_data()
    if not args.quick:
        check_pytest()
        check_offline_app()
    failed = [name for status, name in results if status == "FAIL"]
    warned = [name for status, name in results if status == "WARN"]
    print(f"\n{len(results)} checks: {len(failed)} failed, {len(warned)} warnings")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
