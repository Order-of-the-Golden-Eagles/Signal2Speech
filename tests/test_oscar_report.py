"""#164: OSCAR on recorded EEG. The measures are checked on constructed data; one slow test runs
a short synthetic "recording" through the real g.Pype OSCAR branch. g.tec's dataset isn't needed."""
import numpy as np
import pytest

pytest.importorskip("gpype")
pytest.importorskip("sklearn")
pytest.importorskip("scipy")

from signal2speech.evidence import dataset as gtec  # noqa: E402
from signal2speech.evidence import oscar_report as rep  # noqa: E402
from signal2speech.evidence.synthetic import NONTARGET_CODE, TARGET_CODE  # noqa: E402

FS = 250.0


def fake_session(seconds=60, seed=0, blink_uv=150.0):
    """8 channels of noise, a P300-like bump after target flashes, and big blinks on Fz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    eeg = rng.normal(0, 5, (n, 8))
    codes = np.zeros(n)
    t = np.arange(int(0.6 * FS)) / FS
    bump = 4 * np.exp(-((t - 0.3) / 0.06) ** 2)
    for i, at in enumerate(range(int(2 * FS), n - int(FS), int(0.25 * FS))):
        target = i % 6 == 0
        codes[at] = TARGET_CODE if target else NONTARGET_CODE
        if target:
            eeg[at:at + len(bump), 4] += bump
    for at in range(int(5 * FS), n - int(FS), int(7 * FS)):            # a blink every 7 s
        eeg[at:at + int(0.3 * FS), 0] += blink_uv * np.hanning(int(0.3 * FS))
    return gtec.Session("fake", FS, eeg, codes)


def test_find_delay_recovers_a_known_lag():
    s = fake_session(30)
    after = np.vstack([np.zeros((82, 8)), s.eeg])[:len(s.eeg)]
    assert rep.find_delay(s.eeg, after, start=int(rep.WARMUP_S * FS)) == 82


def test_measure_reports_blinks_and_accuracy_on_unchanged_data():
    """With "after" equal to "before" (no OSCAR), nothing should look improved."""
    s = fake_session(90)
    r = rep.measure(s, s.eeg, s.eeg.copy())
    assert r.delay_ms == 0
    assert r.fz_artifact_uv_before == r.fz_artifact_uv_after > 3 * r.fz_clean_uv_before
    assert r.accuracy_before == r.accuracy_after
    assert "Fz artifact stretches" in r.line() and "| fake |" in rep.table([r])


@pytest.mark.slow
def test_oscar_runs_on_a_replayed_recording():
    """The OSCAR branch really processes replayed data: output follows input after a delay."""
    from signal2speech.evidence.pipeline import oscar_node
    if oscar_node() is None:
        pytest.skip("this g.Pype has no standalone OSCAR node")
    s = fake_session(25)
    before, after = rep.replay(s)
    assert np.allclose(before[:len(s.eeg)], s.eeg, atol=1e-3)      # the player is exact
    assert len(after) >= len(s.eeg)
    assert not np.allclose(after[:len(s.eeg)], s.eeg)                 # OSCAR changed something
