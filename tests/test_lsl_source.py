"""LSL EEG source for a borrowed PiEEG Octopus 16 (#150). No board or PiEEG code needed."""
import json

import pytest

pytest.importorskip("gpype")
pytest.importorskip("pylsl")

from signal2speech.eeg import lsl_source as lsl   # noqa: E402


def test_parse_channels_is_one_based_and_checked():
    assert lsl.parse_channels("15,16", 16) == [14, 15]
    assert lsl.parse_channels("", 4) == [0, 1, 2, 3]
    for bad in ("0", "17", "3,3"):
        with pytest.raises(ValueError):
            lsl.parse_channels(bad, 16)


def test_arming_needs_a_clean_check():
    clean = {"false_triggers": 0, "edges_per_closure": [1, 1, 1]}
    assert lsl.safe_to_arm(clean, 3) == (True, [])
    assert not lsl.safe_to_arm({**clean, "false_triggers": 1}, 3)[0]
    assert not lsl.safe_to_arm({**clean, "edges_per_closure": [1, 2, 1]}, 3)[0]
    assert not lsl.safe_to_arm({**clean, "edges_per_closure": [1]}, 1)[0]      # too few closures
    assert not lsl.safe_to_arm({"error": "eyes open and closed look the same"}, 3)[0]


def test_missing_stream_explains_what_to_run(capsys):
    assert lsl.find_stream("no-such-stream-xyz", timeout=0.5) is None
    assert lsl.main(["--input", "simulated", "--stream", "no-such-stream-xyz"]) == 1
    out = capsys.readouterr().out
    assert "python_quickstart.py --lsl" in out and "no-such-stream-xyz" in out


def test_input_label_must_be_stated():
    with pytest.raises(SystemExit):
        lsl.main(["--stream", "Octopus16"])


def test_self_test_stream_confirms_once_per_closure(capsys):
    """Our own simulated LSL stream through gp.LslReceiver and the alpha switch."""
    pub = lsl.SelfTestStream(name="S2S-Probe").start()
    try:
        visible = lsl.find_stream("S2S-Probe", timeout=5.0)
    finally:
        pub.stop()
    if visible is None:
        pytest.skip("LSL streams can't be discovered on this machine (multicast blocked)")
    assert (visible.channels, visible.rate, visible.type) == (16, 250.0, "EEG")

    code = lsl.main(["--self-test", "--calib-s", "5", "--rest-s", "6", "--closures", "2", "--demo"])
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    report = next(l for l in lines if "report" in l)
    assert report["label"].startswith("Simulated") and report["safe_to_arm"] is True
    assert report["report"]["false_triggers"] == 0
    assert report["report"]["edges_per_closure"] == [1, 1]
    assert [l["outcome"] for l in lines if "outcome" in l] == ["Previewed", "Confirmed"]
    assert code == 0
