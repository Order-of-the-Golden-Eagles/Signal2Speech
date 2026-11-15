"""tools/quick_check.py: the no-install checks CI and the pre-push hook run on every change."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quick_check", ROOT / "tools" / "quick_check.py")
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)


def test_docs_only_changes_skip_the_test_suite():
    assert not qc.needs_tests(["README.md", "DEVLOG.md", "docs/eeg-hardware/README.md",
                               "docs/demo-submission/media/app.png", "data/openorbit/SOURCES.md", ""])


def test_code_data_and_build_changes_need_tests():
    for path in ("signal2speech/app.py", "tests/test_app.py", "contracts/demo-round.json",
                 "data/openorbit/aqi_rows.csv", "pyproject.toml", "requirements-lock.txt",
                 ".github/workflows/tests.yml", ".githooks/pre-push", "tools/quick_check.py",
                 "tests/fixtures/readme.md", "somewhere/new_script.py", "/".join(["signal2speech", "ui", "window.py"]).replace("/", chr(92))):
        assert qc.needs_tests(["README.md", path]), path


def test_devlog_flags_duplicates_and_ai_credit_only(tmp_path):
    log = tmp_path / "DEVLOG.md"
    log.write_text("# Log\n\n"
                   "## 11/14/26 - 1:00 PM - A Dev (with Claude) - #1 First\n- x\n\n"
                   "## 11/14/26 - 2:00 PM - B Dev - #2 Grounded Claude replies\n- y\n\n"
                   "## 11/14/26 - 2:00 PM - B Dev - #2 Grounded Claude replies\n- y\n\n"
                   "## 11/14/26 - 3:00 PM - C Dev (filled in later, from git history) - Kickoff\n- z\n",
                   encoding="utf-8")
    problems = qc.devlog_problems(log)
    assert len(problems) == 2
    assert any("credits an AI tool" in p and ":3:" in p for p in problems)
    assert any("repeated heading" in p and ":9:" in p for p in problems)


def test_conflict_markers_are_found(tmp_path, monkeypatch):
    bad = tmp_path / "notes.md"
    bad.write_text("ok\n" + "<" * 7 + " HEAD\nmine\n" + "=" * 7 + "\ntheirs\n" + ">" * 7 + " main\n", encoding="utf-8")
    good = tmp_path / "fine.md"
    good.write_text("a line of ======= inside text is fine\n", encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", tmp_path)
    assert qc.conflict_markers([bad, good]) == ["notes.md:2: merge-conflict marker"]


def test_the_repo_itself_passes():
    assert qc.main([]) == 0
