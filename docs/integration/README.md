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
  - **Live input (#103):** `--input live` opens one Unicorn pipeline, calibrates on the app's own tiles, then runs the demo. The P300 chooses and the eye-closure switch confirms. See [EEG Hardware](../eeg-hardware/README.md#live-eeg-in-the-app-103).
  - **PiEEG eye-closure confirm (#172):** `--input pieeg` keeps the keyboard choosing and takes the confirm from a PiEEG board's eye closure. See [below](#pieeg-eye-closure-confirm-in-the-app-172).
  - **Recorded input:** `--input recorded` still exits with a "blocked" message (#104). Record and replay work in the evidence view (#48).

## PiEEG eye-closure confirm in the app (#172)

Keys choose and preview. A real eye closure, read from a PiEEG Octopus 16 over LSL, confirms. Then the map changes and the line is spoken once.

```
python -m signal2speech.app --input pieeg --pieeg live          # a real board on a person
python -m signal2speech.app --input pieeg --pieeg-self-test     # no board: our simulated 16-pin stream
python -m signal2speech.app --input pieeg --pieeg simulated     # PiEEG's own simulator (python_quickstart.py --sim --lsl)
python -m signal2speech.app --input pieeg --pieeg recorded      # a recorded session replayed over LSL
```

- **What's publishing must be stated** (`--pieeg live|simulated|recorded`), because LSL can't prove it. The app refuses to start without it, and `--pieeg-self-test` can never be labelled live.
- **One pipeline, g.Pype only.** `PiEEGConfirm` (`signal2speech/eeg/app_live.py`) finds this computer's stream and relays it under a name unique to this machine (`lsl_source.find_stream`, `pieeg_lsl.PiEEGRelay`). It then puts it into the same `AlphaConfirm` (#47) the Unicorn uses, through `pieeg_lsl.make_source`. The P300 chooser is never wired to this board. One spot on the head gives an eyes-closed signal, not a P300.
- **The #150 check runs on screen first:** the channel check, alpha calibration, rest, and closures. Prompts appear in the window's big prompt line, and the window stays responsive (closing it aborts cleanly). Eye-closure confirm switches on only if `lsl_source.safe_to_arm` passes in this session: 0 false triggers and exactly one confirm per closure. If it fails, the board's switch is closed and key 1 confirms. `--arm-live-confirm` is refused here, because only the check decides.
- **The strip shows both inputs:** `Choose: Keyboard · Confirm: Live EEG (PiEEG Octopus 16)` once armed, or `Choose: Keyboard · Confirm: key 1 · Live EEG (PiEEG Octopus 16): eye check failed`. Each confirm in the transcript carries its real source (`live-eeg`, `simulated`, `recorded`, or `keyboard`), and so does the session report.
- **Options:** `--stream`, `--any-host`, `--channels 3,7` (1-based; default `auto` picks the pins that respond), `--probe-s`, `--alpha-calib-s`, `--rest-s`, `--closures`. The defaults match `lsl_source`'s full check: about 1.5 minutes before the first question.
- **Self-test rehearsal:** with `--pieeg-self-test`, the simulated eyes follow the prompts and close on each Confirm round, so `--keys 2` runs hands-free. Tests drive the eyes themselves (`tests/test_app_pieeg.py`).
- **Choose stays on the keyboard.** The simulated P300 chooser and g.tec's recorded data aren't combined with this confirm yet.
- **Recorded:** `--pieeg recorded` labels any replay published over LSL as `Recorded (PiEEG Octopus 16)`. Recording a board session is #170.
- **Not verified:** a real Octopus 16 on a person. Verified on our self-test stream (simulated) only.

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

## Confirm-to-output timing and the session report (#130, #131)

- **Timing:** every confirm logs `timing: confirm→map N ms` (until the map call returns) and `timing: confirm→speech N ms` (until the audio actually starts: Qt's voice reports Speaking, or the bundled clip reports playing). The bottom strip shows the latest values after "Last:". Measured on a Mac (macOS 12): map 2–30 ms, speech 14–17 ms for a bundled clip, and about 50 ms for the OS voice. Muted runs have no speech time.
- **Session report:** on exit, `python -m signal2speech.app` writes `logs/session-<time>.md` (gitignored). It has the date, commit, input, connection, and voice, the counts of previews, confirms, cancels, clears, and rejections, a confirm-to-output table, and the timeline. It's built only from handler outcomes and timings. Any line that looks like raw samples (20+ decimal numbers) is dropped. `--no-report` turns it off. Paste it into the rehearsal log in `docs/demo-submission/submission-checklist.md`.
