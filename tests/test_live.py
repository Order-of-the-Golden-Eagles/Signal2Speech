"""Live-run harness (#23): step logic and the arming decision, headless.

The pure parts (quality, scoring, arming, logging, step order) run without g.Pype or a
headset. One end-to-end dry run uses the g.Pype Generator, labelled Simulated.
"""
import json

import numpy as np
import pytest

from signal2speech.core import (Choice, InputSources, Outcome, SelectionHandler, TargetIds)
from signal2speech.eeg import live

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2
RATE = live.RATE


def _eeg(seconds=10.0, noise=10.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    x = rng.normal(0, noise, (t.size, 8)) + 5 * np.sin(2 * np.pi * 10 * t)[:, None]
    return x + 3000.0   # DC offset must not matter


# ── signal quality ──

def test_quality_go_on_clean_eeg():
    report = live.assess_quality(_eeg())
    assert report.go and report.bad == []
    assert [c.name for c in report.channels] == list(live.CHANNELS)
    assert all(live.FLAT_RMS_UV < c.rms_uv < live.NOISY_RMS_UV for c in report.channels)
    assert "GO" in live.format_quality(report)


def test_quality_flags_flat_noisy_and_line():
    x = _eeg()
    t = np.arange(x.shape[0]) / RATE
    x[:, 0] = 1234.0                                  # flat: electrode off
    x[:, 3] += np.random.default_rng(1).normal(0, 200, x.shape[0])   # noisy
    x[:, 6] += 60 * np.sin(2 * np.pi * 50 * t)       # strong mains
    report = live.assess_quality(x)
    by = {c.name: c for c in report.channels}
    assert by["Fz"].status == "flat"
    assert by["C4"].status == "noisy"
    assert by["Oz"].line_warning and by["Oz"].status == "ok"
    assert not report.go and set(report.bad) == {"Fz", "C4"}
    assert "NO-GO" in live.format_quality(report)


def test_quality_too_short_is_no_go():
    report = live.assess_quality(_eeg(seconds=0.5))
    assert report.channels == [] and not report.go


# ── scoring and arming ──

def _stats(source=InputSources.LIVE_EEG, method="alpha", n=6, wrong_confirmed=0, stale=0):
    label = "Live EEG" if source == InputSources.LIVE_EEG else "Simulated"
    s = live.RunStats(label, source, method)
    for i in range(n):
        a = live.Attempt(i + 1, T1, decoded=T1, preview_outcome="Previewed",
                         confirm_method=method, confirm_outcome="Confirmed")
        s.attempts.append(a)
    for i in range(wrong_confirmed):
        s.attempts.append(live.Attempt(100 + i, T1, decoded=T2, preview_outcome="Previewed",
                                       confirm_method=method, confirm_outcome="Confirmed"))
    for _ in range(stale):
        s.note_outcome(Outcome.RejectedStaleRound)
    return s


def test_arming_safe_only_on_clean_live_alpha_run():
    d = live.decide_arming(_stats())
    assert d.safe and d.rule_passed
    assert "SAFE to set live_eeg_confirm_armed = True" in d.text()


def test_arming_blocked_by_stale_round():
    d = live.decide_arming(_stats(stale=1))
    assert not d.safe and not d.rule_passed
    assert any("RejectedStaleRound" in r for r in d.reasons)


def test_arming_blocked_by_false_confirm():
    s = _stats(wrong_confirmed=1)
    assert s.false_confirms == 1
    d = live.decide_arming(s)
    assert not d.safe and any("false confirm" in r for r in d.reasons)


def test_arming_blocked_by_keyboard_confirm_or_too_few_rounds():
    assert not live.decide_arming(_stats(method="keyboard")).safe
    d = live.decide_arming(_stats(n=live.MIN_ARMING_ATTEMPTS - 1))
    assert not d.safe and any("need" in r for r in d.reasons)


def test_dry_run_never_arms():
    d = live.decide_arming(_stats(source=InputSources.SIMULATED))
    assert d.rule_passed and not d.safe
    assert any("dry run never arms" in r for r in d.reasons)


def test_attempt_scoring_and_summary():
    s = live.RunStats("Simulated", InputSources.SIMULATED, "keyboard")
    s.attempts += [
        live.Attempt(1, T1, T1, "Previewed", "keyboard", "keyboard", "Confirmed", 3.0),
        live.Attempt(2, T2, T1, "Previewed", "keyboard", "keyboard", "Cancelled", 4.0),  # miss
        live.Attempt(3, T2, None, "NoDecision", "keyboard", None, "Skipped", 5.0),
    ]
    for o in (Outcome.Previewed, Outcome.Confirmed, Outcome.Previewed, Outcome.Cancelled):
        s.note_outcome(o)
    out = s.summary()
    assert out["attempts"] == 3 and out["p300_correct"] == 1
    assert out["p300_accuracy"] == pytest.approx(0.333, abs=1e-3)
    assert out["confirmed_correct"] == 1 and out["false_confirms"] == 0
    assert out["mean_seconds_per_selection"] == 4.0
    assert out["outcomes"] == {"Previewed": 2, "Confirmed": 1, "Cancelled": 1}
    assert out["eeg_confirm_rounds"] == 0


# ── logging: never raw EEG ──

def test_runlog_writes_events_and_refuses_samples(tmp_path):
    log = live.RunLog(str(tmp_path), "Simulated")
    log.write("outcome", outcome="Previewed", event={"eventId": "s1-p300"})
    with pytest.raises(TypeError):
        log.write("bad", samples=np.zeros((250, 8)))
    with pytest.raises(TypeError):
        log.write("bad", samples=list(range(250)))
    lines = open(log.path, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["label"] == "Simulated" and rec["outcome"] == "Previewed"
    assert "simulated" in log.path


# ── adapters ──

def test_tagged_adapters_on_one_handler_do_not_collide():
    class Sink:
        def execute(self, action):
            self.action = action
    h = SelectionHandler(Sink())
    p300 = live.TaggedAdapter(h, InputSources.SIMULATED, "p300")
    alpha = live.TaggedAdapter(h, InputSources.SIMULATED, "alpha")
    h.begin_choice_round([Choice(T1, "show_satellite", "Satellite"),
                          Choice(T2, "compare_air_quality", "Compare")])
    p300.arm_capture()
    assert p300.select_captured(T2) is Outcome.Previewed
    alpha.arm_capture()
    assert alpha.select_captured(T1) is Outcome.Confirmed   # same counter value, distinct id


# ── step order (stubbed steps, no g.Pype) ──

class _Quiet:
    def write(self, *_):
        pass

    def flush(self):
        pass


def _harness(tmp_path, source="hybridblack", answers=None, **kw):
    console = live.Console(scripted=answers is None, out=_Quiet(),
                           inp=lambda _q: answers.pop(0) if answers else "")
    opts = live.Options(source=source, logs_dir=str(tmp_path), confirm="keyboard", **kw)
    h = live.LiveHarness(opts, console)
    h.calls = []
    h.close = lambda: h.calls.append("close")
    return h


def _report(go):
    ch = live.ChannelQuality("Fz", 5.0 if go else 0.1, 1.0, "ok" if go else "flat", False)
    return live.QualityReport([ch], 10.0)


def test_labels_and_sources(tmp_path):
    sim = _harness(tmp_path, source="generator")
    assert sim.label == "Simulated" and sim.eeg_source == InputSources.SIMULATED
    assert sim.console.scripted and sim.confirm_method == "keyboard"
    hb = _harness(tmp_path, answers=[])
    assert hb.label == "Live EEG" and hb.eeg_source == InputSources.LIVE_EEG
    assert hb.handler.live_eeg_confirm_armed is False   # the harness never arms before step 5


def test_no_device_exits_cleanly(tmp_path):
    h = _harness(tmp_path, answers=[])
    h.device_check = lambda: False
    h.signal_quality = lambda: pytest.fail("must stop at step 1")
    assert h.run() == live.EXIT_NO_DEVICE
    assert h.calls == ["close"]


def test_quality_no_go_stops_unless_operator_continues(tmp_path):
    h = _harness(tmp_path, answers=["n"])
    h.device_check = lambda: True
    h.signal_quality = lambda: _report(False)
    h.calibrate_p300 = lambda: pytest.fail("must stop at step 2")
    assert h.run() == live.EXIT_NO_GO

    h = _harness(tmp_path, answers=["y"])
    order = []
    h.device_check = lambda: True
    h.signal_quality = lambda: _report(False)
    h.calibrate_p300 = lambda: order.append(3) or True
    h.calibrate_confirm = lambda: order.append(4) or True
    h.attempts = lambda: order.append(5)
    h.finish = lambda: order.append(6)
    assert h.run() == live.EXIT_OK and order == [3, 4, 5, 6]


def test_calibration_failure_exits(tmp_path):
    h = _harness(tmp_path, source="generator")
    h.device_check = lambda: True
    h.signal_quality = lambda: _report(True)
    h.calibrate_p300 = lambda: False
    h.attempts = lambda: pytest.fail("must stop at step 3")
    assert h.run() == live.EXIT_CALIBRATION and h.calls == ["close"]


# ── end-to-end dry run (g.Pype Generator, Simulated) ──

def test_generator_dry_run_end_to_end(tmp_path):
    pytest.importorskip("gpype")
    pytest.importorskip("sklearn")
    pytest.importorskip("h5py")
    pytest.importorskip("PySide6")
    opts = live.Options(source="generator", attempts=3, quality_s=2.0, calibration=4,
                        confirm="keyboard", logs_dir=str(tmp_path), seed=1)
    h = live.LiveHarness(opts, live.Console(scripted=True, out=_Quiet()))
    assert h.run() == live.EXIT_OK
    s = h.stats.summary()
    assert s["label"] == "Simulated" and s["attempts"] == 3
    assert s["stale_round_rejections"] == 0 and s["false_confirms"] == 0
    assert s["outcomes"].get("Previewed", 0) == 3 - sum(
        a.preview_outcome != "Previewed" for a in h.stats.attempts)
    records = [json.loads(line) for line in open(h.log.path, encoding="utf-8")]
    kinds = {r["kind"] for r in records}
    assert {"step", "device", "quality", "p300_calibration", "outcome", "attempt",
            "summary"} <= kinds
    summary = next(r for r in records if r["kind"] == "summary")
    assert summary["arming_safe"] is False                  # a dry run never arms
    assert all(r["label"] == "Simulated" for r in records)
