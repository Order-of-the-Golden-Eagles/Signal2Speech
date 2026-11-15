"""Double-blink confirm: blinks stand far above the resting signal; only a quick pair fires."""
import numpy as np
import pytest

from signal2speech.eeg.blink_confirm import BlinkError, BlinkSwitch

RATE = 250


def signal(seconds, blinks=(), amp=80.0, noise=5.0, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, noise, (int(seconds * RATE), 8))
    for t in blinks:                       # a 0.2 s swing on the forehead channel
        i = int(t * RATE)
        x[i:i + 50, 0] += amp * np.hanning(50)
    return x


def calibrated(fired):
    b = BlinkSwitch(fired.append, log=lambda s: None)
    rest = np.abs(signal(6, seed=1)[:, 0])
    windows = [np.abs(signal(2.5, blinks=(0.3, 0.8), seed=s)[:, 0]) for s in (2, 3, 4)]
    b.calibrate(rest, windows)
    return b


def test_a_quick_pair_of_blinks_fires_once_and_single_blinks_never_do():
    fired = []
    b = calibrated(fired)
    b._on_rows(signal(3, blinks=(0.5,), seed=5))            # one blink
    b._on_rows(signal(3, blinks=(0.5, 2.2), seed=6))        # two, too far apart
    assert fired == []
    b._on_rows(signal(3, blinks=(0.5, 1.0), seed=7))        # a double blink
    assert len(fired) == 1


def test_calibration_refuses_blinks_that_dont_stand_out():
    b = BlinkSwitch(lambda t: None, log=lambda s: None)
    rest = np.abs(signal(6, seed=1)[:, 0])
    weak = [np.abs(signal(2.5, blinks=(0.3, 0.8), amp=8.0, seed=s)[:, 0]) for s in (2, 3, 4)]
    with pytest.raises(BlinkError):
        b.calibrate(rest, weak)
    assert b.level is None


def test_nothing_fires_before_calibration():
    fired = []
    b = BlinkSwitch(fired.append, log=lambda s: None)
    b._on_rows(signal(3, blinks=(0.5, 1.0)))
    assert fired == []


def test_a_blink_while_resting_does_not_spoil_calibration():
    b = BlinkSwitch(lambda t: None, log=lambda s: None)
    rest = np.abs(signal(6, blinks=(3.0,), seed=1)[:, 0])       # blinked once while "not blinking"
    windows = [np.abs(signal(2.5, blinks=(0.3, 0.8), seed=s)[:, 0]) for s in (2, 3, 4)]
    assert b.calibrate(rest, windows) > 0
