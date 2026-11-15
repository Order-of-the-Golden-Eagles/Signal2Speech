# Text-to-Speech

Speak the approved reply once after confirmation, offline. A natural neural voice (Piper) when it is installed, the operating system's voice otherwise.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

**Consolidated issues** · [#6](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/6)

## Bundled clip for the comparison line (#97)

`data/openorbit/audio/compare_air_quality.wav` gives the fixed comparison line the same voice on every laptop that doesn't have the natural voice. `signal2speech/speech/` plays a clip only for that action. The satellite line's clip (`show_satellite.wav`) was retired on 2026-11-15: its words changed when the satellite view became a day-by-day sequence, and a clip must never say different words from the ones the wearer approved. With the natural voice installed, every line uses that voice and no clip plays. Generated replies (`speak_reply`) always use the offline OS voice, because a recording can't match words the wearer just approved.

- **Regenerate** after changing a line in `contracts/demo-round.json`: `brew install espeak-ng` (or apt or the Windows installer), then `python data/openorbit/audio/make_audio.py`. The voice is robotic but clear, and the licence is clean.
- **Check:** `python data/openorbit/audio/make_audio.py --check`. `tests/test_audio.py` runs the same check in CI.
- **Release check:** `tools/release_check.py` reports WAVs as "media to review" (WARN). That's expected: they're our generated audio, not recordings of anyone.

## A natural voice: Piper (optional)

The operating system's built-in voices sound robotic. When Piper and a voice file are present, the app speaks every line with a natural neural voice instead. It runs on the laptop with no network.

**Set it up once per machine** (the judging laptop is set up):

```
pip install piper-tts
mkdir voices
curl -L -o voices/en_US-hfc_female-medium.onnx      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx
curl -L -o voices/en_US-hfc_female-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json
```

- **Check it's on:** the developer log (F2) says `speech: natural voice, Piper (en_US-hfc_female-medium)` after a confirm. Without Piper or the file, the app speaks exactly as before.
- **Another voice, or none:** set `SIGNAL2SPEECH_VOICE` to an `.onnx` file, or to `off`.
- **No delay on confirm:** making a sentence takes one to two seconds, so the app starts making a line when it's previewed. Measured on the judging laptop: audio starts 0.15 s after the confirm when the line was previewed, and 1.5 s when it wasn't. A line is made once and reused.
- **Abbreviations:** the voice is given the full form when we know it ("AQI" is said as "air quality index") and letters otherwise ("PDF" as "P.D.F."). The screen keeps the original text. Names the voice gets wrong are respelled for it ("MODIS" as "Moe-diss"). The lists are in `signal2speech/speech/neural.py`.
- **Dates are read as dates:** "June 28, 2023" is spoken as "June twenty-eighth, twenty twenty-three", and "Jun 26" as "June twenty-sixth".
- **Numbers are read slower:** a line with figures in it is spoken 25 % slower, so they're easy to catch (`NUMBER_SLOWDOWN` in `neural.py`).
- **If a line can't be made,** that line falls back to the bundled clip or the operating system's voice.

**Licences. Check these before reusing the project elsewhere.**
- Piper (`piper-tts`) is GPL-3.0. We run its command line as a separate program and never import it.
- The `hfc_female` voice was trained on the Hi-Fi-CAPTAIN dataset, which is CC BY-NC-SA 4.0: non-commercial use, with credit. The voice file is never committed (`voices/` is gitignored).

## One sound player, and what we checked (2026-11-15)

- **One player for the whole session.** `OfflineSpeaker` reuses a single `QSoundEffect` for every line, where it used to create a new one each time.
- **Measured on the judging laptop:** 52 lines in a row, and separately an eight-question recorded-mode run with three guidance lines, all reached the speakers for their full length (level meter on the default output device).
- **Unexplained:** during one earlier session the voice was reported to stop after a while. We could not reproduce it, and that session's log shows every reply as playing. Restart the app between judges.
- **Walkthrough guidance** in recorded mode is spoken with the same voice as the replies (`--no-narration` turns it off). It is never the wearer's reply and is not logged as output.
