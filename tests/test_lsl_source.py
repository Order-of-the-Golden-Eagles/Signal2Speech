"""Eyes-closed confirm on an LSL EEG board (#150). No board or PiEEG code needed."""
import json

import numpy as np
import pytest

pytest.importorskip("gpype")
pytest.importorskip("pylsl")

from signal2speech.eeg import devices                 # noqa: E402
from signal2speech.eeg import lsl_source as lsl       # noqa: E402


def test_parse_channels_is_one_based_and_checked():
    assert lsl.parse_channels("15,16", 16) == [14, 15]
    assert lsl.parse_channels("", 16) is None and lsl.parse_channels("auto", 16) is None
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


def test_live_label_names_the_device_and_safety_names_the_power_bank():
    assert lsl.live_label(devices.PIEEG_OCTOPUS16) == "Live EEG (PiEEG Octopus 16)"
    assert "power bank" in lsl.SAFETY and "USB" in lsl.SAFETY


def test_contact_report_names_flat_and_railed_pins():
    rng = np.random.default_rng(0)
    block = rng.normal(0, 10, size=(8 * 250, 16))
    block[:, 0] = 0.0
    block[:, 1] *= 60
    text = lsl.contact_report(devices.PIEEG_OCTOPUS16, block, 250.0)
    assert "flat (not touching)" in text and "railed" in text and "14 of 16 pins" in text


def test_missing_stream_explains_what_to_run(capsys):
    assert lsl.main(["--input", "simulated", "--stream", "no-such-stream-xyz"]) == 1
    assert "python_quickstart.py" in capsys.readouterr().out


def test_input_label_must_be_stated():
    with pytest.raises(SystemExit):
        lsl.main(["--stream", "Octopus16"])


def test_self_test_board_picks_good_pins_and_confirms_once_per_closure(capsys):
    """Our own simulated 16-pin stream: one flat pin, one railed pin, alpha on the rest."""
    pub = lsl.SelfTestStream(name="S2S-Probe").start()
    try:
        import pylsl
        visible = pylsl.resolve_byprop("name", "S2S-Probe", 1, 5.0)
    finally:
        pub.stop()
    if not visible:
        pytest.skip("LSL streams can't be discovered on this machine (multicast blocked)")

    code = lsl.main(["--self-test", "--probe-s", "5", "--calib-s", "5", "--rest-s", "6",
                     "--closures", "2", "--demo"])
    out = capsys.readouterr().out
    lines = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    report = next(l for l in lines if "report" in l)
    assert report["label"].startswith("Simulated") and report["device"] == "pieeg-octopus16"
    assert 1 not in report["channels_1based"] and 2 not in report["channels_1based"]   # bad pins
    assert len(report["channels_1based"]) >= 10
    assert report["safe_to_arm"] is True and report["report"]["false_triggers"] == 0
    assert report["report"]["edges_per_closure"] == [1, 1]
    assert [l["outcome"] for l in lines if "outcome" in l] == ["Previewed", "Confirmed"]
    assert "14 of 16 pins have good contact" in out
    assert code == 0
