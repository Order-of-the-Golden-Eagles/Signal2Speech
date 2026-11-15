"""Bundled OpenOrbit clips (#97): the right words, the right files, and only for those two actions."""
import json
import wave
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from signal2speech.speech import AUDIO_DIR, BUNDLED_CLIPS, bundled_clip  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((AUDIO_DIR / "manifest.json").read_text(encoding="utf-8"))
CONTRACT = {c["actionId"]: c["spokenText"]
            for c in json.loads((ROOT / "contracts" / "demo-round.json").read_text())["choices"]}


@pytest.mark.parametrize("action", sorted(BUNDLED_CLIPS))
def test_clip_reads_the_exact_contract_text(action):
    assert MANIFEST["clips"][action]["text"] == CONTRACT[action]


def test_comparison_clip_matches_the_dataset_line():
    """#106's AI map suggestion speaks dataset.spoken_comparison(); the clip must say the same."""
    from signal2speech.openorbit import load_dataset
    ds = load_dataset()
    if not hasattr(ds, "spoken_comparison"):
        pytest.skip("dataset has no spoken_comparison()")
    assert MANIFEST["clips"]["compare_air_quality"]["text"] == ds.spoken_comparison()


@pytest.mark.parametrize("action", sorted(BUNDLED_CLIPS))
def test_clip_file_is_a_small_valid_wav(action):
    path = bundled_clip(action)
    assert path is not None and path.stat().st_size < 1_000_000
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        assert 2.0 < w.getnframes() / w.getframerate() < 15.0     # seconds


def test_generated_replies_never_use_a_clip():
    assert bundled_clip("speak_reply") is None


def test_make_audio_check_passes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_audio", AUDIO_DIR / "make_audio.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--check"]) == 0
