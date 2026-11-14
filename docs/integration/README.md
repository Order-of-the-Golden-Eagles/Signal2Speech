# Integration

Route keyboard, simulated and live EEG input through one confirmation handler.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

## Running the integrated app (#4, #25)

```
python -m signal2speech.app --input keyboard              # keys 1/2, Esc cancels, D simulates a disconnect
python -m signal2speech.app --input simulated --sim 2,1   # scripted classes: choose target-2, then confirm
python -m signal2speech.app --input simulated --sim 2,2   # choose, then cancel: expect no output
```

Add `--mute` for silent runs. Add `--screenshot out.png` to save the window after the first confirm and exit.

- **One output path:** `AppSink.execute` in `signal2speech/app.py` is the only code that changes the map or speaks. It calls the map method first and then speaks `spoken_text`. The handler calls it exactly once per confirmation. Previews, cancels, disconnects, and stale or duplicate events produce no output. `tests/test_app.py` checks this with a fake view and a fake speaker.
- **Transcript:** the right-hand panel and stdout log each round, preview, outcome (with source, event ID, and round), and output line.
- **Speech (`signal2speech/speech/`, #25):**
  - **Bundled clip:** `data/openorbit/audio/<action_id>.wav` plays if it exists. This applies only to the fixed OpenOrbit lines (`show_satellite`, `compare_air_quality`). Generated replies never use a clip, because a recording can't match words the wearer just approved.
  - **OS voice:** otherwise the app uses the OS voice through Qt TextToSpeech, which is offline and doesn't block the window.
  - **pyttsx3:** used only if Qt has no voice engine, because it freezes the window while it speaks.
  - **Logging:** the transcript logs which voice is in use.
- **Still stand-ins, all labelled on screen:**
  - **Map (#30):** until `signal2speech.openorbit.OpenOrbitView` exists, a dashed "OpenOrbit view not built yet (#30)" panel shows which map action ran. When #30 lands, `load_view()` imports it automatically. It needs `show_satellite()` and `compare_air_quality()`.
  - **Simulated input (#21):** `--input simulated` uses `signal2speech.eeg.simulated.SimulatedDecoder`, a real g.Pype `Generator` stream, whenever it imports. Ctrl+1 and Ctrl+2 pick for a waiting sequence, and the stream closes on exit. If it can't import, the app injects scripted decisions through the same `arm_capture()` and `select_captured()` path. The connection label says why it fell back: "#21 SimulatedDecoder not merged" or "g.Pype not installed". Events are labelled `simulated` either way.
  - **Live and recorded input:** `--input live` and `--input recorded` exit with a message that they're blocked on #46, #47, #23, and #48.
