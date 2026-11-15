"""The repo's .githooks/pre-commit must block secrets and raw EEG on every OS (runs in CI on all three)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".githooks"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def clean_env(extra=None):
    """The environment minus every GIT_* variable, plus ``extra``.

    Git exports GIT_DIR, GIT_INDEX_FILE, and friends to hooks. When pytest runs inside the
    pre-push hook, a plain subprocess would inherit them, and these tests' git commands would
    hit the developer's real repo: they set core.bare=true, overwrote user.name/email and
    core.hooksPath, and committed "add ok.py" there. Stripping them pins every command to its
    own temporary repo.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra or {})
    return env


def git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=clean_env(env))


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


def test_hook_environment_cannot_reach_an_outer_repo(tmp_path, monkeypatch):
    """Regression: inside the pre-push hook, git exports GIT_DIR; these tests must ignore it."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    git(outer, "config", "user.name", "Real Developer")
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))        # what a hook would export
    monkeypatch.setenv("GIT_WORK_TREE", str(outer))
    inner = tmp_path / "inner"
    inner.mkdir()
    git(inner, "init", "-q")
    git(inner, "config", "user.name", "Hook Test")
    commit(inner, "ok.py", "print('hello')\n")
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    cfg = git(outer, "config", "--local", "--list").stdout
    assert "user.name=Real Developer" in cfg and "core.bare=true" not in cfg
    assert git(outer, "rev-parse", "--verify", "-q", "HEAD").returncode != 0   # no commits
    assert git(inner, "log", "--oneline").stdout.count("add ok.py") == 1
