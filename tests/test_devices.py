"""Device detection and back-of-head channel choice (#150)."""
import numpy as np
import pytest

from signal2speech.eeg import devices as dv

RATE = 250


def eeg(seconds, channels, alpha_uv, seed=0):
    """Noise on every channel plus 10 Hz alpha with a per-channel amplitude."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    x = rng.normal(0, 10, size=(len(t), channels))     # ~5.6 uV RMS in 1-40 Hz: good contact
    return x + np.sin(2 * np.pi * 10 * t)[:, None] * np.asarray(alpha_uv, float)[None, :]


def test_detect_known_devices():
    assert dv.detect("hybridblack") is dv.UNICORN
    assert dv.detect("hybrid-black") is dv.UNICORN
    assert dv.detect("dataset") is dv.GTEC_P300_DATASET
    assert dv.detect("generator") is dv.GENERATOR
    assert dv.detect(stream_name="Octopus16", channel_count=16, rate=250) is dv.PIEEG_OCTOPUS16
    assert dv.detect(stream_name="S2S-PiEEG-laptop", channel_count=16) is dv.PIEEG_OCTOPUS16
    other = dv.detect(stream_name="SomeAmp", channel_count=4, rate=500)
    assert other.key == "unknown" and other.channel_count == 4 and not other.fixed_montage


def test_gtec_montages_put_occipital_on_channels_6_to_8():
    for d in (dv.UNICORN, dv.GTEC_P300_DATASET):
        names = {d.channel_names[i] for i in d.alpha_channels}
        assert names == {"PO7", "Oz", "PO8"}, d.name
    assert dv.UNICORN.channel_names != dv.GTEC_P300_DATASET.channel_names   # same set, other order


def test_unicorn_default_matches_the_alpha_switch():
    alpha = pytest.importorskip("signal2speech.eeg.alpha_confirm")
    assert tuple(alpha.OCCIPITAL) == dv.UNICORN.alpha_channels


def test_fixed_montage_needs_no_data_and_override_wins():
    pick = dv.resolve_alpha_channels(dv.UNICORN)
    assert pick.channels == (5, 6, 7) and "PO7" in pick.reason
    assert dv.resolve_alpha_channels(dv.PIEEG_OCTOPUS16, requested=[14, 15]).channels == (14, 15)
    with pytest.raises(ValueError):
        dv.resolve_alpha_channels(dv.PIEEG_OCTOPUS16, requested=[16])
    with pytest.raises(ValueError):
        dv.resolve_alpha_channels(dv.PIEEG_OCTOPUS16)          # unnamed board, no data


def test_pick_finds_the_electrodes_on_the_back_of_the_head():
    open_amp = [2.0] * 16
    closed_amp = [2.0] * 16
    closed_amp[13], closed_amp[14] = 20.0, 17.0             # the two pins with good contact
    pick = dv.resolve_alpha_channels(dv.PIEEG_OCTOPUS16, open_block=eeg(8, 16, open_amp, 1),
                                     closed_block=eeg(8, 16, closed_amp, 2), rate=RATE)
    assert set(pick.channels) == {13, 14} and pick.channels[0] == 13
    assert "ch 14" in pick.table(dv.PIEEG_OCTOPUS16) and "<- used" in pick.table(dv.PIEEG_OCTOPUS16)


def test_one_good_electrode_is_not_diluted():
    closed_amp = [2.0] * 16
    closed_amp[15] = 25.0
    pick = dv.pick_alpha_channels(eeg(8, 16, [2.0] * 16, 3), eeg(8, 16, closed_amp, 4), RATE)
    assert pick.channels == (15,)


def test_no_alpha_response_says_what_to_do():
    with pytest.raises(dv.NoAlphaResponse) as e:
        dv.pick_alpha_channels(eeg(8, 16, [2.0] * 16, 5), eeg(8, 16, [2.0] * 16, 6), RATE)
    assert "back of the head" in str(e.value) and "--channels" in str(e.value)


def test_bad_contact_pins_are_never_picked():
    rng = np.random.default_rng(7)
    open_b = eeg(8, 16, [2.0] * 16, 8)
    closed = eeg(8, 16, [12.0] * 16, 9)                     # every pin sees alpha...
    open_b[:, 0] = closed[:, 0] = 0.0                       # ...but pin 1 is flat (no contact)
    open_b[:, 1] = rng.normal(0, 10, len(open_b))           # and pin 2 is loose: quiet with eyes
    closed[:, 1] = rng.normal(0, 600, len(closed))          # open, then railed (over 150 uV RMS)
    pick = dv.resolve_alpha_channels(dv.PIEEG_OCTOPUS16, open_block=open_b, closed_block=closed, rate=RATE)
    assert 0 not in pick.channels and 1 not in pick.channels
    assert len(pick.channels) >= 10                          # the good pins are averaged together


def test_no_contact_at_all_says_how_to_seat_the_sensor():
    flat = np.zeros((8 * RATE, 16))
    with pytest.raises(dv.NoAlphaResponse) as e:
        dv.pick_alpha_channels(flat, flat, RATE)
    assert "headband" in str(e.value)


def test_pieeg_contact_uses_the_vendor_range():
    assert dv.PIEEG_OCTOPUS16.contact_rms_uv == (2.0, 150.0)
    rng = np.random.default_rng(11)
    block = rng.normal(0, 10, size=(8 * RATE, 3))
    block[:, 1] *= 0.05                                      # flat: under 2 uV RMS
    block[:, 2] *= 60                                        # railed: over 150 uV RMS
    assert dv.contact_ok(block, RATE, dv.PIEEG_OCTOPUS16.contact_rms_uv).tolist() == [True, False, False]
