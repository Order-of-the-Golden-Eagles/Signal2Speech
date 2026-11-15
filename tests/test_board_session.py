"""Voice-guided board session (#150, #170, #171). No board, no PiEEG code, no sound."""
import json

import numpy as np
import pytest

pytest.importorskip("gpype")
pytest.importorskip("pylsl")

from signal2speech.eeg import board_session as bs     # noqa: E402


def test_closure_is_matched_to_the_choice_being_read():
    offers = [(10.0, "Yes"), (13.0, "No"), (16.0, "Compare counties")]
    # Reacting to "No": the switch fires one latency after the wearer hears it.
    assert bs.attribute(13.0 + 1.8, offers, latency_s=1.8) == "No"
    assert bs.attribute(13.0 + 1.8 - 0.4, offers, latency_s=1.8) == "No"      # a quick reaction
    assert bs.attribute(13.0 + 1.8 + 2.0, offers, latency_s=1.8) == "No"      # a slow one
    assert bs.attribute(16.0 + 1.8 + 0.6, offers, latency_s=1.8) == "Compare counties"
    assert bs.attribute(9.0, offers, latency_s=1.8) == "Yes"                  # before anything: first
    assert bs.attribute(5.0, [], latency_s=1.8) is None


def test_choices_are_spoken_with_numbers():
    assert bs.spoken_option(0, "Yes") == "One: Yes."
    assert bs.spoken_option(3, "Satellite view") == "Four: Satellite view."


def test_verdict_is_strict():
    good = {"calibration": {"ratio": 8.0}, "rest": {"false_triggers": 0},
            "switch_test": {"cued": 5, "hits": 5, "extra_triggers": 0},
            "scan_test": {"trials": 4, "correct": 4}}
    assert bs.judge(good).ready
    for path, value in ((("rest", "false_triggers"), 1), (("switch_test", "hits"), 4),
                        (("switch_test", "extra_triggers"), 1), (("scan_test", "correct"), 3)):
        bad = json.loads(json.dumps(good))
        bad[path[0]][path[1]] = value
        v = bs.judge(bad)
        assert not v.ready and v.reasons, path
    no_cal = {k: v for k, v in good.items() if k != "calibration"}
    assert not bs.judge(no_cal).ready


def test_silent_voice_prints_every_cue_and_can_keep_speech_timing():
    v = bs.Voice(enabled=False)
    v.say("Close your eyes.")
    v.beep("go")
    assert v.log == ["Close your eyes."] and not v.audible
    assert 1.0 < bs.Voice.estimate_s("Two: Compare counties.") < 2.5


def test_verify_recording_reads_back_the_calibration(tmp_path):
    rng = np.random.default_rng(0)
    rate, n = 250, 250 * 40
    t = np.arange(n) / rate
    eeg = rng.normal(0, 10, size=(n, 16))
    closed = (t >= 10) & (t < 20) | (t >= 30) & (t < 40)
    eeg += (np.where(closed, 25.0, 3.0) * np.sin(2 * np.pi * 10 * t))[:, None]
    np.savez_compressed(tmp_path / "eeg.npz", eeg=eeg.astype(np.float32), lsl_time=t)
    events = [{"event": "cal_open", "sample": 0}, {"event": "cal_closed", "sample": 2500},
              {"event": "cal_open", "sample": 5000}, {"event": "cal_closed", "sample": 7500},
              {"event": "cal_end", "sample": n}]
    (tmp_path / "events.json").write_text(json.dumps(events))
    (tmp_path / "report.json").write_text(json.dumps(
        {"label": "Simulated", "started": "x", "seconds": 40, "phases_done": ["calibration"],
         "channels_1based": [3, 4, 5]}))
    lines = []
    assert bs.verify_recording(tmp_path, say=lines.append) is True
    text = "\n".join(lines)
    assert "10000 samples x 16 channels" in text and "0 gap(s)" in text and "USABLE" in text


def test_verify_recording_flags_missing_files_and_gaps(tmp_path):
    lines = []
    assert bs.verify_recording(tmp_path, say=lines.append) is False and "missing" in lines[0]
    (tmp_path / "events.json").write_text("[]")
    (tmp_path / "report.json").write_text(json.dumps({"label": "Live", "phases_done": []}))
    assert bs.verify_recording(tmp_path, say=lines.append) is False        # report only
    t = np.concatenate([np.arange(500) / 250, 10 + np.arange(500) / 250])   # a 8 s hole
    np.savez_compressed(tmp_path / "eeg.npz", eeg=np.zeros((1000, 16), np.float32), lsl_time=t)
    assert bs.verify_recording(tmp_path, say=lines.append) is False
    assert any("1 gap(s)" in l for l in lines)


def test_live_recording_needs_consent(capsys):
    with pytest.raises(SystemExit):
        bs.main([])                                           # must say what is publishing


def test_whole_session_on_the_simulated_board(tmp_path, capsys):
    """Every phase, on our own 16-pin stream: one flat pin, one loose pin, a simulated wearer."""
    import pylsl

    from signal2speech.eeg import lsl_source
    pub = lsl_source.SelfTestStream(name="S2S-Probe4").start()
    try:
        seen = bool(pylsl.resolve_byprop("name", "S2S-Probe4", 1, 5.0))
    finally:
        pub.stop()
    if not seen:
        pytest.skip("LSL streams can't be discovered on this machine (multicast blocked)")

    out = tmp_path / "session"
    code = bs.main(["--self-test", "--quick", "--fast-silent", "--out", str(out)])
    text = capsys.readouterr().out
    report = json.loads((out / "report.json").read_text())
    assert code == 0, text[-1500:]
    assert report["phases_done"] == ["contact", "channel pick", "switch", "calibration", "rest",
                                     "switch test", "scan test"]
    assert report["ready_for_live_confirm"] is True and report["reasons"] == []
    assert 1 not in report["channels_1based"] and 2 not in report["channels_1based"]
    assert report["rest"]["false_triggers"] == 0
    assert report["switch_test"]["hits"] == report["switch_test"]["cued"] == 3
    assert report["scan_test"]["correct"] == report["scan_test"]["confirmed_correct"] == 2
    assert (out / "eeg.npz").is_file() and (out / "events.json").is_file()
    assert "USABLE: the recording is complete." in text
    assert "Simulated" in report["label"]
