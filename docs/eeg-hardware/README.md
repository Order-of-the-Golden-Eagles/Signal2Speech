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
- **Picks:** `--picks` gives one class per round. With no picks queued, a sequence waits for `set_next(cls)` (Ctrl+1 / Ctrl+2 in `--ui`). In flash mode, a keyed pick still waits for the flashes to end. Class 2 in a Confirm round means Cancel.
- **Pick alignment:**
  - If the judge cancels or the headset disconnects before a decision, the pick goes back to the front of the queue, because the same step comes again.
  - If another input (keys 1/2) uses the round, that round's pick is dropped, so the next round still gets its own pick.
- **Headless runner:**
  - It reopens the question while picks remain and exits 0 when they are spent.
  - It exits 1 on `--timeout`, and 2 with no `--picks`.
  - It always uses `QApplication`, forcing offscreen when there's no display.
- `close()` removes the decoder's handler listeners and restores the flasher hooks, so a closed decoder never arms again.
- `disconnect_stream()` stops the stream and calls `handler.disconnect()`, for recovery checks (#26).
- Tests: `tests/test_simulated.py` (13 tests) covers:
  - preview then confirm through the real pipeline
  - cancel and stale-drop
  - keyed picks, which wait for the flashes
  - pick alignment
  - hook chaining and unhooking
  - the CLI: several rounds, the timeout exit code, and the usage error

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
- **Driven by the P300 chooser (`--p300`):** `python -m signal2speech.evidence --source generator --p300` (or `--source hybridblack --p300`) builds the graph with `build_evidence_graph(front_end=p300_front_end)` and puts the chooser's online scorers and calibration collectors in the same pipeline (`signal2speech/evidence/p300_mode.py`). A `P300Chooser` emits every flash on the graph's `marker`, from `make_sequence` flash schedules, and two test tiles flash in the window header. The run calibrates first (`--calibration N` sequences, default 6), fits the LDA, then selects until the window closes. Each decision goes through `InputAdapter.select_captured` to the `SelectionHandler`, and the header shows the decision, the outcome, and the attended tile (simulated on the Generator, cued on the headset).
  - The target vs non-target average uses the calibration codes (101 / 100). Those averages and the classifier's training epochs come from the same Trigger nodes on the same filtered stream (the OSCAR branch when there is one), so the plot shows what the LDA learns from. Online flashes use the tile codes (1 / 2, yellow markers) and are not averaged, because on live EEG the attended tile is only what the cue asked for.
  - On the Generator the chooser's own synthetic P300 is used, labelled Simulated. With `--p300` the filter is the chooser's 1–30 Hz bandpass only (no 50 / 60 Hz notches).
  - Verified on simulated input only: headless tests in `tests/test_evidence_p300.py`, and a 22 s offscreen run (`--calibration 2`) that made 2 of 2 correct simulated selections. With so few calibration epochs the average separates only weakly on screen. Not yet run with a headset.
- **Seam for #46:** `build_evidence_graph(front_end=...)` accepts the P300 chooser's filter chain, and the graph's `marker` is the node the flashing tiles emit on. Without `--p300`, pass `--no-flasher` when other tiles send the markers.

## P300 chooser

`signal2speech/eeg/p300.py` ([#46](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/46)) picks one of two tiles from the P300 the wearer makes when the attended tile flashes.

```
HybridBlack(enable_oscar=True) | Generator + SyntheticP300
  → Bandpass 1–30 Hz
  → Trigger(tile code, −0.1…0.7 s) → P300Scorer (shrinkage LDA) → per-sequence mean → class 1/2
  → EegClassMap.default() → InputAdapter.select_captured() on the Qt main thread
```

**Run it**

```
python -m signal2speech.eeg.p300 --source offline        # synthetic recordings through batch g.Pype, ~5 s
python -m signal2speech.eeg.p300 --source generator      # realtime Generator + synthetic P300, labelled Simulated
python -m signal2speech.eeg.p300 --source hybridblack    # Live EEG: shows two test tiles, cues the tile to attend
```

Options: `--calibration N` sequences (default 10), `--sequences N` online picks (default 6), `--flashes N` per tile (default 5), `--soa S` seconds between flashes (default 0.25), `--no-oscar`, `--window` (test tiles for the Generator too). The test tiles are a bare CLI aid; the real tiles are `signal2speech/ui` (#24).

**How it works**

- **Calibration.** The wearer attends a cued tile. Each flash sends Marker 101 (attended tile) or 100 (the other tile). Triggers on those codes collect epochs, and `gp.Sklearn.fit_offline` fits `LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")` on 40 ms bin means (20 bins × 8 channels).
- **Selection.** Tile flashes send Marker 1 or 2. Each tile has its own Trigger and scorer. Once every tile has had its flashes, the tile with the highest mean LDA score wins. `arm_capture()` runs at sequence start, so the decision carries the round it was flashed in.
- **Plugging in from the UI (#24).** `chooser = P300Chooser(build_pipeline("hybridblack", model=model), adapter)`, then `chooser.attach(flash_scheduler)`. This wires `on_sequence_started` to `begin_sequence` (arms capture) and `on_flash` to the Marker. It also forces a decision `TIME_POST + 0.5` s after the last flash if an epoch went missing. Flashes per tile equals the scheduler's `repetitions`.
- **For the evidence view (#48).** `build_pipeline()` returns `P300Nodes` (`eeg`, `marker`, `triggers`, `scorers`, calibration collectors). `p300_front_end` can be passed as `build_evidence_graph(front_end=...)`.
- **Threading.** Scorers run on g.Pype worker threads. `SequenceAggregator` is lock-protected. The decision crosses to the main thread through a Qt `Signal` (`QtDecisionBridge`) before it touches `SelectionHandler`.
- **Models.** A model is the calibration epochs (`P300Model`), kept in memory and refitted into each scorer. Nothing is written to disk. Never commit EEG or fitted models. `models/`, `*.pkl`, `*.joblib`, and `*.npy` are gitignored.

**Verified (synthetic only, 2026-11-14)**

| Check | Result |
| --- | --- |
| `pytest tests/test_p300.py` (7 tests, ~11 s, headless) | Pass. Trains on a synthetic calibration recording cut by g.Pype `Epochs`, then checks held-out accuracy, chance level without a P300, aggregation, thread safety, and the contract hand-off. A realtime Generator test checks that decisions reach `InputAdapter` on the Qt thread. |
| `--source offline --calibration 10 --sequences 20` | Epoch accuracy 0.95. Sequence accuracy 0.95 with 1 flash per tile, 1.00 with 2–5. |
| `--source generator --calibration 8 --sequences 6` | 6/6 online in realtime. Every decision came back `Previewed` through `SelectionHandler`. Also 2/2 with `--window` under the offscreen Qt platform. |

The synthetic P300 is a 5 µV Gaussian at 300 ms over 10 µV white noise plus 10 Hz alpha, and every flash adds a small N1. This is far cleaner than real single-trial EEG, so **these numbers show the plumbing works, not that a person can use it.**

**Not verified yet**

- **Live headset:** `--source hybridblack` hasn't been run. Accuracy, trials needed per wearer, and OSCAR's effect on P300 epochs are all unmeasured. Report them here after the first live calibration.
- **Two-tile oddball:** each tile is the target half the time, which isn't rare. Real P300s are larger for rare targets. If live accuracy is weak, add null flashes or more tiles, or fall back to the alpha step-through (#47).
- **Flash-to-marker timing:** the P300 is locked to the real flash. The marker is emitted right after Qt repaints the tile, not at the monitor's vsync (`FlashScheduler` and the CLI tiles both work this way). Expect 0–17 ms of jitter at 60 Hz plus compositor delay. A constant offset is harmless because calibration learns it, but jitter smears the epoch. OSCAR adds processing delay, and we haven't checked whether g.Pype aligns Marker events to OSCAR-delayed samples.

**TODO: measure flash jitter.**

1. Tape a photodiode over a tile corner, wired into an aux input.
2. Record a calibration run with the evidence view's `--record`.
3. Offline, find each light onset in the photodiode channel and subtract the matching marker sample. The mean is the latency and the standard deviation is the jitter.
4. If the standard deviation is above about 10 ms, pass the flip time to `on_flash(target_id, observed_at=...)`, for example `gp.stamp_clock()` taken in a `QWindow.frameSwapped` handler.
