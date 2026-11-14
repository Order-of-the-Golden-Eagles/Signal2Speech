"""The repo's .githooks/pre-commit must block secrets and raw EEG on every OS (runs in CI on all three)."""
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".githooks"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Hook Test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "config", "core.hooksPath", str(HOOKS).replace("\\", "/"))
    return tmp_path


def commit(repo, name, content, *, force=False):
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", *(["-f"] if force else []), name)
    return git(repo, "commit", "-q", "-m", f"add {name}")


def test_clean_commit_passes(repo):
    r = commit(repo, "ok.py", "print('hello')\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "No secret-like patterns found" in r.stdout + r.stderr


@pytest.mark.parametrize("secret", [
    "sk-ant-" + "a" * 30,
    "ghp_" + "A" * 36,
    "AKIA" + "B" * 16,
    "-----BEGIN RSA " + "PRIVATE KEY-----",  # split so this file passes its own scan
])
def test_secret_is_blocked(repo, secret):
    r = commit(repo, "leak.py", f"KEY = '{secret}'\n")
    assert r.returncode != 0
    assert "Secret-like content" in r.stdout + r.stderr


def test_raw_eeg_and_env_are_blocked(repo):
    assert commit(repo, "run.edf", "x", force=True).returncode != 0
    git(repo, "reset", "-q")
    assert commit(repo, ".env", "ANTHROPIC_API_KEY=x", force=True).returncode != 0


def test_env_example_is_allowed(repo):
    assert commit(repo, ".env.example", "ANTHROPIC_API_KEY=\n").returncode == 0
