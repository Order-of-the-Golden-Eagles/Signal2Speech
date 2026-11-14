# EEG Hardware

Use g.Pype with the `HybridBlack` source (`enable_oscar=True`). Develop against `Generator` and recorded runs, and record simulated, recorded, and live verification separately. Never commit raw EEG.

**Active work** · [#2](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/2)

## Tracks

| Issue | File | What |
| --- | --- | --- |
| [#21](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/21) | `signal2speech/eeg/simulated.py` | `Generator` or injected decisions → `InputAdapter(SIMULATED)` |
| [#46](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/46) | `signal2speech/eeg/p300.py` | Flash markers → `Epochs` → `Sklearn` LDA → class 1/2 |
| [#47](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/47) | `signal2speech/eeg/alpha_confirm.py` | `FFT` → `BandPower(alpha)` → `Threshold` → one confirm per eye closure |
| [#23](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/23) | `signal2speech/eeg/live.py` | Pair the headset, calibrate, and run the live preview and confirm |
| [#48](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/48) | `signal2speech/evidence/` | Scopes, OSCAR toggle, `EpochAverage`, record and replay |

## Simulated input (#21) — works

`signal2speech/eeg/simulated.py` runs a real g.Pype pipeline with a scripted brain. **Verified on Linux, Python 3.12.13, g.Pype 4.2.0, with simulated input only.** It hasn't been run on the judging laptop yet.

```
python -m signal2speech.eeg.simulated --picks 2,1        # headless: preview r1, confirm r2, then exit
python -m signal2speech.eeg.simulated --ui               # #24 window labelled Simulated; Ctrl+1 / Ctrl+2 pick
python -m signal2speech.eeg.simulated --ui --picks 2,1   # window, scripted
python -m signal2speech.eeg.simulated --ui --flash --picks 2,1 --confirm-s 2   # flash tiles, P300-like timing
```

Each event prints as one JSON line, labelled `"source": "simulated"`. `--decision-s` sets the stream seconds per sequence (default 0.8).

**How it works.** This is the path that live decoders (#46, #47, #23) should copy:

```
gp.Generator (8 ch, 250 Hz) -> DecisionSink (gp.INode, g.Pype worker thread)
  -> SimulatedDecoder.decided  (Qt Signal, QueuedConnection)  -> Qt main thread
  -> InputAdapter(handler, SIMULATED).select_captured(EegClassMap.default().target_for(cls))
```

- **Arm at sequence start.** By default, each round calls `arm_capture()` when it opens and decides after `decision_s` (Choose) or `confirm_s` (Confirm) seconds of stream.
- **`flasher=window.flasher` mode:** a Choose round arms on the #24 `FlashScheduler.on_sequence_started` and decides on `on_sequence_finished`, the same hooks #46 will use. A Confirm round arms when it opens and decides after `confirm_s`, which is where the #47 alpha window goes. This matches `InjectedSimulatedInput` in `app.py`, so it's a one-line swap. See [Integration](../integration/README.md#rehearse-without-a-headset-gpype-simulated-input-21).
- **Drop stale decisions before the adapter.** Each sequence gets an ID. A decision whose ID isn't the pending sequence is dropped (`decoder.dropped`), so a late result can't be stamped with the next round's ID. `adapter.select_captured()` alone doesn't protect against this, because it uses the most recent arm.
- **Picks:** `--picks` gives one class per sequence. With no picks queued, a sequence waits for `set_next(cls)` (Ctrl+1 / Ctrl+2 in `--ui`). Class 2 in a Confirm round means Cancel.
- `disconnect_stream()` stops the stream and calls `handler.disconnect()`, for recovery checks (#26).
- Tests: `tests/test_simulated.py` covers preview then confirm through the real pipeline, cancel, stale-drop, keyed picks, flasher mode (the decision comes only after every flash), and the CLI.

**g.Pype facts we verified (4.2.0):**

- A custom sink is `class X(gp.INode)` with `step(self, data)` reading `data["in"]` and returning `{}`. Set any callback attributes after `super().__init__()`, not as constructor kwargs, because kwargs become node config.
- `step()` runs on a g.Pype worker thread (`Thread-N (_thread_function)`), never the Qt main thread.
- `Pipeline.start()` takes about 0.5 s. `Generator` sends 4-sample frames at 250 Hz, plus one timestamp channel that `Bandpass` drops.
- `Generator` parameters can't be changed while the pipeline runs: it has no `set_control`. `Threshold` and `Gate` can be changed at runtime. `Gate` only accepts event (async) input.
- `FFT(window_size=250, overlap=0.9)` → `BandPower(["alpha"])` emits 10 rows per second, one value per channel, labelled `ChNN:alpha`. A 20 µV 10 Hz sine gives a power of about 400.

**Qt gotcha:** every test or tool that creates the Qt app must use `QApplication.instance() or QApplication([])`, not `QCoreApplication`. The first app created wins, and the #24 widgets abort the whole pytest run under a `QCoreApplication`.

**Checklist for live runs:** pair the Unicorn in the OS Bluetooth settings first, check signal quality on all 8 channels, calibrate the P300 (trial count to be set in #46) and the alpha threshold (#47), and record which classes map to which tiles.

**Ask the g.tec mentor:** Paradigm Presenter licence (we use our own PySide6 flashing), access to the MCP visualizer from the workshop, and whether one headset can stream to two apps at once.

## Evidence view

`signal2speech/evidence/` ([#48](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/48)) opens a g.Pype window for judges. It shows raw EEG with flash markers, filtered EEG (1–30 Hz plus 50 and 60 Hz notches), an OSCAR panel, the spectrum, and the averaged response to target flashes against non-target flashes. The window title and a coloured banner always name the input: **Simulated**, **Recorded**, or **Live EEG**.

```
python -m signal2speech.evidence --source generator              # Simulated
python -m signal2speech.evidence --source hybridblack            # Live EEG, OSCAR off and on side by side
python -m signal2speech.evidence --source hybridblack --record   # also record to recordings/
python -m signal2speech.evidence --source replay recordings/evidence_<timestamp>   # Recorded
```

- **OSCAR on and off:** `HybridBlack(enable_oscar=True)` gives only the cleaned stream. To show both, the view builds the headset with OSCAR off and runs g.Pype's `Oscar` node on a branch. That node comes from a private module (`gpype.backend.core._private.oscar`). If it is missing, the view falls back to `enable_oscar=True`, and you can compare by running a second time with `--oscar off`. OSCAR runs on our Generator data, but it hasn't been checked on real EEG.
- **Generator** has no brain, so the view adds a synthetic deflection about 300 ms after each target marker. That is why the average separates. It is labelled Simulated, and OSCAR is shown as unavailable.
- **Record and replay** use g.Pype's launch recorder (`LaunchConfig` `save_as` / `load_from`). It saves the EEG and the flash markers as HDF5 files, taken before OSCAR, under `recordings/`, which is gitignored. Never commit a recording. A replay rebuilds the same graph and is labelled Recorded.
- **Seam for #46:** `build_evidence_graph(front_end=...)` accepts the P300 chooser's filter chain, and the graph's `marker` is the node the flashing tiles should emit on. Pass `--no-flasher` when the tiles send the markers.
