# Integration

Route keyboard, simulated and live EEG input through one confirmation handler.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

## Running the integrated app (#4, #25)

```
python -m signal2speech.app --input keyboard              # keys 1/2, Esc cancels, D simulates a disconnect
python -m signal2speech.app --input simulated --sim 2,1   # scripted classes: choose target-2, then confirm
python -m signal2speech.app --input simulated --sim 2,2   # choose, then cancel: expect no output
```

Add `--mute` for silent runs. `--confirm-timeout SECONDS` (default 15; 0 = never; otherwise 0.1–3600) cancels an unanswered Confirm round. The timeout lives in `App`, so dev entry points that build their own handler (`python -m signal2speech.ui`, `eeg.simulated --ui`) have no timeout. Moving it into `SelectionHandler` is a #22 contract decision. The transcript shows `cleared (timeout): no output` (#26). Add `--screenshot out.png` to save the window after the first confirm and exit.

- **One output path:** `AppSink.execute` in `signal2speech/app.py` is the only code that changes the map or speaks. It calls the map method first and then speaks `spoken_text`. The handler calls it exactly once per confirmation. Previews, cancels, disconnects, and stale or duplicate events produce no output. `tests/test_app.py` checks this with a fake view and a fake speaker.
- **Transcript:** the right-hand panel and stdout log each round, preview, outcome (with source, event ID, and round), and output line.
- **Map reveal:** after a confirmed map action, the empty tiles hide and the map gets most of the window. The judge strip and its input label stay visible. The next question waits 8 s (`reveal_ms`), so the audience can read the AQI table. Spoken replies and cancels go back to the question after 2 s (`reopen_ms`).
- **Speech (`signal2speech/speech/`, #25):**
  - **Bundled clip:** `data/openorbit/audio/<action_id>.wav` plays if it exists. This applies only to the fixed OpenOrbit lines (`show_satellite`, `compare_air_quality`). Generated replies never use a clip, because a recording can't match words the wearer just approved.
  - **OS voice:** otherwise the app uses the OS voice through Qt TextToSpeech, which is offline and doesn't block the window.
  - **pyttsx3:** used only if Qt has no voice engine, because it freezes the window while it speaks.
  - **Logging:** the transcript logs which voice is in use.
- **Still stand-ins, all labelled on screen:**
  - **Map (#30, merged in #65):** `load_view()` uses `signal2speech.openorbit.OpenOrbitView`. The dashed stand-in panel appears only if that import fails.
  - **Simulated input (#21):** `--input simulated` uses `signal2speech.eeg.simulated.SimulatedDecoder`, a real g.Pype `Generator` stream, whenever it imports. Ctrl+1 and Ctrl+2 pick for a waiting sequence, and the stream closes on exit. If it can't import, the app injects scripted decisions through the same `arm_capture()` and `select_captured()` path. The connection label says why it fell back: "#21 SimulatedDecoder not merged" or "g.Pype not installed". Events are labelled `simulated` either way.
  - **Live and recorded input:** `--input live` and `--input recorded` exit with a message that they're blocked on #46, #47, #23, and #48.

## Rehearse without a headset: g.Pype simulated input (#21)

`signal2speech/eeg/simulated.py` (`SimulatedDecoder`) is the g.Pype version of `InjectedSimulatedInput`. A real `gp.Generator` stream runs on g.Pype worker threads. Each decision crosses to the Qt main thread on a queued signal and reaches `InputAdapter(handler, SIMULATED).select_captured()`. Events are labelled `simulated`.

**Used by `app.py` (#25, PR #60):** `python -m signal2speech.app --input simulated` builds `SimulatedDecoder(h, script, flasher=window.flasher, confirm_s=2.0)` whenever the module imports. Otherwise it falls back to `InjectedSimulatedInput` and labels why. With `flasher=`:

- **Choose rounds** arm on `on_sequence_started` and decide on `on_sequence_finished`, never during the flashes.
- **Confirm rounds** arm when the round opens and decide after `confirm_s`.
- The window's own flash hooks are chained, not replaced. `close()` unhooks everything.
- Verified 2026-11-14: `--input simulated --sim 2,1 --mute` gives one preview, then one map action and one spoken line, labelled `simulated`.

- A decision from an older sequence is dropped before it reaches the adapter. `select_captured()` alone would stamp a late decision with the newest armed round.
- With no picks left, a sequence waits for `set_next(cls)`.
- `disconnect_stream()` stops the stream and calls `handler.disconnect()` (#26).
- Standalone: `python -m signal2speech.eeg.simulated --ui --picks 2,1`. See [EEG Hardware](../eeg-hardware/README.md#simulated-input-21--works) for the threading details.
