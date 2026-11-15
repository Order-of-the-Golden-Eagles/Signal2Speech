# Text-to-Speech

Speak the approved reply once after confirmation. Use offline audio for OpenOrbit. Generated-reply speech TBD.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

**Consolidated issues** · [#6](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/6)

## Bundled clips for the OpenOrbit lines (#97)

`data/openorbit/audio/show_satellite.wav` and `compare_air_quality.wav` give the two fixed lines the same voice on every laptop. `signal2speech/speech/` plays a clip only for those two actions. Generated replies (`speak_reply`) always use the offline OS voice, because a recording can't match words the wearer just approved.

- **Regenerate** after changing a line in `contracts/demo-round.json`: `brew install espeak-ng` (or apt or the Windows installer), then `python data/openorbit/audio/make_audio.py`. The voice is robotic but clear, and the licence is clean.
- **Check:** `python data/openorbit/audio/make_audio.py --check`. `tests/test_audio.py` runs the same check in CI.
- **Release check:** `tools/release_check.py` reports WAVs as "media to review" (WARN). That's expected: they're our generated audio, not recordings of anyone.
