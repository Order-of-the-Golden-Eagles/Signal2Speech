"""#41: one hardware-free smoke command, plus metadata-only diagnostics."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
np = pytest.importorskip("numpy")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech import diagnostics as d  # noqa: E402
from signal2speech.app import AppSink, main  # noqa: E402
from signal2speech.core import (InputAdapter, InputSources, SelectionHandler,  # noqa: E402
                                TargetIds)
from signal2speech.ui.__main__ import load_demo_choices  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    # QApplication, not QCoreApplication: the first app created wins, and #24 widgets need it.
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def tmp_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "LOG_DIR", tmp_path / "logs")   # keep test runs out of logs/


def run(mode="dev"):
    lines = []
    code = d.run_smoke(mode, out=lines.append)
    return code, "\n".join(lines)


def test_smoke_passes_on_a_good_checkout(qapp):
    code, out = run()
    assert code == 0, out
    assert "FAIL " not in out
    for name in ("environment", "demo numbers", "confirm flow", "cancel flow", "g.Pype stream"):
        assert f"PASS  {name}" in out
    assert out.count("MANUAL") == len(d.MANUAL_CHECKS)
    assert "SMOKE PASS" in out


def test_judging_mode_turns_skips_into_failures(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(d, "DATA_DIR", tmp_path / "no-bundle")
    code, out = run("judging")
    assert code == 1
    assert "FAIL  openorbit assets" in out and "SMOKE FAIL" in out


def test_smoke_fails_when_a_confirm_produces_output_twice(qapp, monkeypatch):
    """Deliberate breakage (#38): the check must go red, not just green."""
    original = AppSink.execute

    def twice(self, action):
        original(self, action)
        original(self, action)
    monkeypatch.setattr(AppSink, "execute", twice)
    monkeypatch.setattr(d, "check_gpype_stream", lambda: d.Check("g.Pype stream", "PASS", "skipped"))
    code, out = run()
    assert code == 1
    assert "FAIL  confirm flow" in out


def test_asset_check_reads_the_bundle(tmp_path):
    (tmp_path / "SOURCES.md").write_text(
        "EPA AirData daily AQI: Washtenaw 32 (Jun 26) 218 (Jun 28); Wayne 58 and 226.")
    for name in ("modis_2023-06-26.png", "modis_2023-06-28.png"):
        (tmp_path / name).write_bytes(b"\x89PNG")
    assert d.check_assets(tmp_path).status == "PASS"
    (tmp_path / "SOURCES.md").write_text("Washtenaw 32 218")
    bad = d.check_assets(tmp_path)
    assert bad.status == "FAIL" and "Wayne" in bad.detail


def test_diagnostics_never_record_raw_eeg():
    diag = d.Diagnostics()
    with pytest.raises(TypeError):
        diag.record("eeg", samples=np.zeros((250, 8)))
    with pytest.raises(TypeError):
        diag.record("eeg", samples=list(range(250)))
    assert diag.record("ok", level=np.float32(1.5))["level"] == 1.5


def test_attach_logs_input_connection_and_timing(qapp):
    class Sink:
        def execute(self, action):
            pass

    sink = Sink()
    h = SelectionHandler(sink)
    diag = d.Diagnostics().attach(h, input_source=InputSources.KEYBOARD, gpype_source="none",
                                  connection="n/a", sink=sink)
    kb = InputAdapter(h, InputSources.KEYBOARD)
    h.begin_choice_round(load_demo_choices())
    kb.select_now(TargetIds.TARGET_2)
    kb.select_now(TargetIds.TARGET_1)
    kinds = [r["kind"] for r in diag.rows]
    assert kinds.count("handled") == 2 and kinds.count("output") == 1
    handled = [r for r in diag.rows if r["kind"] == "handled"]
    assert all("since_round_ms" in r for r in handled)
    out = diag.outputs()[0]
    assert out["action"] == "compare_air_quality" and "output_ms" in out
    assert all(r["input"] == "keyboard" and r["connection"] == "n/a" for r in diag.rows[3:])


def test_app_smoke_flag(qapp):
    assert main(["--smoke"]) == 0
