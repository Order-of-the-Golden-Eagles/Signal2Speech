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
  - The next round after any clear (cancel, Esc, timeout, disconnect) is a Choose round. If a Choose round is cleared before its decision, its pick goes back.
  - If a Confirm round is cleared, the whole pair replays: the choose pick that made the preview, then the unused confirm pick. A scripted Cancel (class 2) replays nothing.
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

**Measure it:** see [Flash timing](#flash-timing) below.

## Flash timing

The P300 is locked to the moment a tile really lights on the monitor. The chooser sends its Marker right after Qt repaints the tile. A constant gap between the two is fine, because calibration learns it. Jitter in the gap smears every epoch and lowers accuracy. `signal2speech/eeg/flash_timing.py` (#46) measures it.

**Run it on the judging laptop, on the display the wearer will watch, before 8:15**

```
python -m signal2speech.eeg.flash_timing --seconds 30                   # real QLabel tiles + DWM vblank estimate
python -m signal2speech.eeg.flash_timing --seconds 30 --tiles gl        # QOpenGLWidget tiles + Qt frameSwapped
python -m signal2speech.eeg.flash_timing --seconds 60 --csv logs/flash_timing.csv   # keep per-flash times for the photodiode check
```

It flashes two tiles with the chooser's own `FlashScheduler` (100 ms flash, 75 ms gap). For every lit flash it records the time `on_flash` runs (where the chooser emits the Marker) and the best present time it can get:

- **`--tiles widget` (default).** Same QLabel restyle plus `repaint()` path as the real tiles. The present time is the next display vblank after the repaint flushed, read from the Windows compositor clock (`DwmGetCompositionTimingInfo`, same QueryPerformanceCounter clock as the marker). This is an **estimate**, and a weak one. The offset is just "next vblank after the flush", so at 60 Hz it is spread evenly over 0–16.7 ms plus repaint time, and the jitter (about 15 ms) is built in and always under the 20 ms threshold. It can't see DWM composition latency, a late present for this window, or the panel's own scan-out delay. **A widget-mode PASS only rules out repaint stalls and missed frames.** The real test is `--tiles gl` or the light sensor / camera check below. Off Windows there is no source, and the tool says so.
- **`--tiles gl`.** `QOpenGLWidget` tiles with vsync on. The present time is Qt's `frameSwapped` signal for the lit frame.

It prints the offset (present minus marker) mean, p95, max, min, and standard deviation, then the jitter (the p95 − p5 spread of the offset), the refresh rate, repaint time, flash-onset interval, and frames the compositor missed. Then it prints:

- **PASS:** the jitter is at most 20 ms (`--threshold-ms`), with at least 20 flashes, fewer than 10 % of flashes missing a present time, and no missed compositor frames. In widget mode the PASS line says plainly that it only rules out repaint stalls and missed frames.
- **WARN:** anything else. It is always WARN under `QT_QPA_PLATFORM=offscreen`, which never draws to a screen. The exit code is 0 for PASS and 1 for WARN.

At 60 Hz, a one-frame quantisation gives about 0–17 ms of offset and passes. If you get a WARN, close other apps, turn off Windows battery saver and variable refresh rate, keep the window on the laptop's own panel (not a projector mirror), and run it again.

**Verified so far (2026-11-14, dev Windows laptop, offscreen only):** 18 headless tests cover the statistics, PASS/WARN logic, CSV, and ground-truth comparison. A 3 s offscreen run executes, reads a 60.00 Hz refresh from DWM, and reports WARN because it is offscreen. Offscreen numbers mean nothing. **Not verified:** a run on a real display, the `--tiles gl` swap timing (offscreen gives no swaps), and macOS or Linux.

### Ground truth with a light sensor or a phone camera

Software timestamps can't see the panel itself. To check what the screen really does, record when the light actually comes on and compare it to the markers. Both methods below compare **intervals** between consecutive flashes, so the sensor's clock never needs to match the laptop's. A constant delay cancels out. Only jitter remains.

**Option A: phone slow-motion camera (no parts, about 10 minutes)**

1. Set the laptop to the brightness and power plan you'll use for the demo, and plug in the charger.
2. Run `python -m signal2speech.eeg.flash_timing --seconds 20 --csv logs/flash_timing.csv`.
3. Film one tile with the phone at 240 fps (iPhone and most Android phones have this) from the moment the window opens. 240 fps gives 4.2 ms per frame. 120 fps (8.3 ms) is still usable. Fill the frame with the tile, and lock exposure if you can.
4. Step through the video frame by frame, for example in VLC with `E`, or a free frame-stepping app. Write down the frame number where the tile first turns white, for every flash of that tile.
5. Convert each frame number to seconds (frame ÷ fps) and write one per line in `logs/onsets.txt`. Start from the first flash of that tile the tool made.
6. Run `python -m signal2speech.eeg.flash_timing --compare logs/flash_timing.csv logs/onsets.txt --tile target_1` (the left tile is `target_1`, the right is `target_2`). `--tile` keeps only that tile's markers.
7. Read the "estimated per-flash jitter std". Anything under about 10 ms is fine for the P300 at 240 fps. The resolution floor is about one camera frame.

**Option B: cheap light sensor (photodiode or photoresistor) on a microcontroller**

1. Tape a photodiode (for example a BPW34) or a photoresistor over a tile corner with black tape so room light can't reach it. Wire it to an analog pin of an Arduino, ESP32, or similar, using a voltage divider (photoresistor plus a 10 kΩ resistor).
2. Have the board print `micros()/1e6` over serial each time the reading crosses a threshold upward, with a few ms of debounce. Save the serial output as `logs/onsets.txt`, one time per line.
3. Run the tool with `--csv`, then `--compare ... --tile <taped tile>` as in Option A. A photodiode resolves about 1 ms. A photoresistor is slower (10–50 ms rise), but its delay is mostly constant, so it still shows jitter.
4. Reset the board's log before each run, and drop any onsets from before the tool's first flash so both lists start on the same flash. The tool warns when the counts differ.

**Option C: through the EEG (best, needs the g.tec mentor).** A photodiode recorded by the amplifier puts the light onsets on the EEG clock, so you can measure the absolute marker-to-light latency, including OSCAR and g.Pype delays. The Unicorn has no dedicated photodiode input. Ask the mentor before connecting anything to an electrode input. If it's possible: record a calibration run with the evidence view's `--record`, find each onset in the sensor channel offline, and subtract the matching marker sample. The mean is the latency and the standard deviation is the jitter.

**What to do with the result**

- Jitter std under about 10 ms: do nothing. Calibration absorbs the constant part.
- Above that: pass a measured present time to `P300Chooser.on_flash(target_id, observed_at=...)`. `on_flash` already accepts it, and `Marker.emit(..., observed_at=...)` timestamps the marker with it. Take it as `gp.stamp_clock()` in a `frameSwapped` handler (the `--tiles gl` path shows how). Note that `observed_at` must be on g.Pype's clock, not the QPC clock this tool uses.
- Write the measured numbers (laptop, refresh rate, method, jitter) in this section and in docs/MEMORY.md. Don't commit `logs/` files. They're gitignored.

## Alpha-switch confirm (#47): works on simulated input

`signal2speech/eeg/alpha_confirm.py`. Closing the eyes for about 2 s in an armed Confirm round emits exactly one `target-1` (Confirm). **Verified on simulated input only** (g.Pype `Generator` plus injected 10 Hz bursts), on Linux with Python 3.12.13 and g.Pype 4.2.0. Live calibration on a wearer is pending the headset slot (#23).

```
python -m signal2speech.eeg.alpha_confirm                          # Generator: 10 s + 10 s calibration, 60 s rest, 3 closures, JSON report
python -m signal2speech.eeg.alpha_confirm --demo                   # Generator: keyboard preview, then alpha confirm through the handler
python -m signal2speech.eeg.alpha_confirm --source hybrid-black    # live: pair the Unicorn first, then follow the >>> prompts
```

Flags: `--calib-s`, `--rest-s`, `--closures`, `--dwell-s` (default 1.0), `--settle-s` (default 1.0), `--burst-uv` (Generator alpha amplitude, default 8), `--min-ratio` (default 2).

**Pipeline**

```
source -> [AlphaBursts, simulated only] -> Bandpass 1-30 Hz -> ChannelSelector(indices 5,6,7 = PO7, Oz, PO8)
  -> FFT(250, overlap 0.9) -> BandPower(alpha 8-13 Hz) -> ChannelMean -> Threshold(level, release, dwell 10 rows)
  -> Tap -> AlphaConfirm.rising/.falling (queued Qt signals) -> main thread -> adapter.select_captured("target-1")
```

- **Calibration:** `Calibration.from_samples(open, closed)` refuses NaN or infinite rows, which come from a flat or railing electrode. Then it sets `level = sqrt(open_p95 × closed_median)` and `release = sqrt(open_p95 × level)`, a geometric midpoint with hysteresis. It refuses when the closed median is under 2× the open p95 (`CalibrationError`). The levels are applied live through `Threshold.set_control()`. Until calibration runs, the level is 1e12, so nothing fires.
- **Gating, on top of the threshold:**
  1. It only listens in an armed Confirm round. Arming happens through `handler.on_round_opened`; cancel or clear disarms it.
  2. The eyes must have been open continuously for `settle_s`. That's measured from arming, or from the last time they opened. A closure that comes too early doesn't count, and the eyes have to open again. Arming reads the worker thread's Threshold state, so a closure still in flight from the previous round can't slip through.
  3. Only a rising edge counts. It disarms after one decision, so one closure gives one event. If the handler rejects the decision and the Confirm round stays open (for example `RejectedLiveConfirmDisarmed`), it keeps listening in that round.
- **Live EEG:** labelled `live-eeg`. The handler still returns `RejectedLiveConfirmDisarmed` until #23 sets `live_eeg_confirm_armed`. The decoder works, and the contract holds it back.
- **Sharing the headset with #46:** a Unicorn opens only once. Pass `AlphaConfirm(handler, pipeline=p, upstream=bandpass_node, input_source=LIVE_EEG)` to hang the alpha branch off the P300 pipeline instead of opening a second source. If that stream isn't 250 Hz, pass `sampling_rate=`: the FFT window stays 1 s and the dwell stays in seconds. A mismatch raises at pipeline start.
- **Lifecycle:** `close()` unhooks from the handler. The band-power buffer keeps the last 2 minutes, and edges and log entries keep the last 256, so a long demo can't grow memory.
- **Tests:** `tests/test_alpha_confirm.py` covers the calibration math, every gating rule, the live-disarmed contract, and one Generator burst through the real pipeline giving exactly one confirm and no rest triggers.

**Simulated results (Generator with 10 µV noise, 2026-11-14)**

| Burst | Open p95 | Closed median | Ratio | Level / release | False triggers, 60 s eyes-open | Edges per closure | Latency from closure to edge |
| --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| 8 µV | 10.6 | 68.8 | 6.5 | 27.0 / 16.9 | **0** | 1, 1, 1, 1, 1 | 1.21–1.45 s |
| 4 µV (weak alpha) | 10.1 | 23.2 | 2.3 | 15.3 / 12.4 | **0** | 1, 1, 1, 1, 1 | 1.19–1.49 s |

Latency is about 0.3–0.5 s for the 1 s FFT window to fill with alpha, plus the 1.0 s dwell. With `--dwell-s 0.5` the switch reacts faster but chatters more. Real eyes-closed alpha is typically 2–10× eyes-open, and some people have weak alpha, so the 2× floor is the first thing to check at the headset slot. Even at ratio 2.3 (4 µV), the simulated switch held: no false triggers and one edge per closure. Real EEG adds blinks and drift that the Generator lacks.

**Fallback (if P300 is unreliable): not built yet.** The plan is to step through the options one at a time and confirm each with this switch. `AlphaConfirm` acts only in Confirm rounds today, so stepping needs a small driver:

1. Highlight one tile at a time.
2. Arm for each highlight.
3. Send the highlighted target on a rising edge.

Then confirm with `AlphaConfirm` as usual. The `rising` signal and the calibration are reusable as-is.

**g.Pype facts we confirmed:**

- `ChannelMean` and `AlphaBursts` are custom `gp.IONode`s. For a 1-channel output, `setup()` sets `channel_count`, `channel_roles`, and `channel_labels` in the output context.
- `Threshold.set_control({"level", "release", "dwell"})` works while the pipeline runs.
- More than one `Pipeline` can run in a process. g.Pype refuses only a faster-than-real-time replay beside another pipeline.

## Live run

`signal2speech/eeg/live.py` ([#23](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/23)) walks the headset slot step by step, so the live run is one command.

```
python -m signal2speech.eeg.live --source hybridblack   # Live EEG: Unicorn Hybrid Black, OSCAR on
python -m signal2speech.eeg.live --source generator     # dry run, no hardware, labelled Simulated
```

**Before you start:** turn the headset on and pair it in the OS Bluetooth settings. Close anything else that might have it open, such as the evidence view or another g.Pype run.

| Step | What happens | Stops when |
| --- | --- | --- |
| 1. Device check | Opens the source through the #46 P300 pipeline. One headset can be opened once, so every branch shares that pipeline. | The headset isn't paired or sends no samples within 5 s. It prints the pairing checklist and exits with code 3. |
| 2. Signal quality | About 10 s of stream with OSCAR on (`--quality-s`). For each channel it shows the 1–30 Hz RMS and the 50/60 Hz RMS, then GO or NO-GO. | NO-GO, unless the operator types `y`. Exits with code 4. |
| 3. P300 calibration | `P300Chooser.begin_calibration` / `finish_calibration` from `p300.py`, over `--calibration` sequences (default 10). The test tiles show which tile to attend. It prints a cross-validated epoch accuracy (chance is 0.50). | No epochs collected. Exits with code 5. |
| 4. Confirm calibration | The #47 alpha switch (`measure()`: eyes open, eyes closed, a rest period to count false triggers, and 2 closures), if `signal2speech/eeg/alpha_confirm.py` is on the checkout. Otherwise it uses keyboard confirm. | Alpha calibration fails. Exits with code 5. |
| 5. Attempts | `--attempts` choose+confirm attempts (default 10) through `SelectionHandler` and `InputAdapter`. Confirm a correct preview. Let a wrong one time out (alpha) or cancel it (keyboard). | — |
| 6. Summary | P300 accuracy, correct and confirmed, mean seconds per selection, false confirms, `RejectedStaleRound` count, late P300 decisions, every outcome, and the arming verdict. | — |

**Arming rule.** It is safe to set `live_eeg_confirm_armed = True` only if all of these are true:

- the input was Live EEG, never Simulated
- at least 5 confirm rounds were decided by the alpha switch, not the keyboard
- no `RejectedStaleRound` was seen
- there were 0 false confirms (a Confirmed after a wrong preview)

The harness uses its own handler with a logging sink, so nothing is spoken and the map doesn't change. On a live alpha run it arms that handler for step 5 only. The app's handler stays disarmed until someone changes it after reading the summary.

**Logs.** Each run writes `logs/live_<YYYYmmdd-HHMMSS-mmm>_<pid>_<simulated|live-eeg>.jsonl`, opened with mode `x` so two runs started at the same moment never share a file. The `logs/` folder is gitignored. The log holds steps, the quality table, calibration counts, every handler outcome with its event, every P300 decision (and whether it was late), each attempt, and the summary. `RunLog` refuses arrays and long lists, so raw EEG can't end up in a log.

**Event IDs.** Two `InputAdapter`s with the same source on one handler both count from 1. So the P300 branch's `s1` and the alpha branch's `s1` collide, and the alpha confirm is rejected as `RejectedDuplicateEvent`. The harness found this. `TaggedAdapter` adds a branch tag (`s1-p300`, `s1-alpha`). The app needs the same fix when it wires up both branches.

**Verified (2026-11-14, Windows 11, Python 3.12.10, g.Pype 4.2.0)**

| Check | Result |
| --- | --- |
| `--source generator` (defaults: `--confirm auto`, so the #47 alpha switch now on main), Simulated | Ran to completion in about 160 s. Quality GO on 8 channels. LDA on 50 target and 50 non-target epochs, CV epoch accuracy 0.89. Alpha ratio 7.0, 0 false triggers in the 20 s rest, 1 edge per closure. 10/10 correct previews, 10/10 confirmed by simulated eye closures, 0 false confirms, 0 `RejectedStaleRound`, 0 late decisions, 5.65 s per selection. Verdict: not safe (Simulated). |
| `--source generator --confirm keyboard`, Simulated | Earlier run, before #47 merged: 83 s, 10/10 correct and Confirmed, 0 false confirms. An earlier alpha run with PR #58 loaded by hand found the event-ID collision above. |
| `--source hybridblack` with no headset | `ConnectionError: No Unicorn device available`. Prints the pairing checklist and exits with code 3 in about 8 s. |
| `pytest tests/test_live.py` (19 tests) | Pass. Covers quality rules, arming rules, scoring, the log refusing samples, separate log files for runs in the same second, tagged adapters, step order and exit codes, and three end-to-end Generator dry runs. Two of them inject wrong decodes: on keyboard, a wrong preview is cancelled and a wrongly confirmed one counts as 1 false confirm (verdict not safe); on alpha, a wrong preview with no eye closure times out. |

**Not verified yet:** anything with the real headset. That includes the quality thresholds (`FLAT_RMS_UV` 0.5, `NOISY_RMS_UV` 50, `LINE_RMS_UV` 10 µV are starting guesses), whether the HybridBlack signal-role channels are the 8 EEG channels in Unicorn order, OSCAR's effect, real P300 and alpha accuracy, and whether a late decision ever crosses rounds. Fill in the table below after the run.

| Live result (#23) | Value |
| --- | --- |
| Pairing steps that worked | |
| Bad channels at first, and fix | |
| Calibration time (P300 / alpha) | |
| P300 accuracy (correct / attempts) | |
| False confirms | |
| `RejectedStaleRound` seen | |
| Class → tile mapping | 1 → `target-1`, 2 → `target-2` (`EegClassMap.default()`) |
| Arm `live_eeg_confirm_armed`? | |

## Live EEG in the app (#103)

`python -m signal2speech.app --input live` runs the demo on the Unicorn. The P300 chooses a tile, and the eye-closure switch confirms. Both run on **one** `HybridBlack(enable_oscar=True)` pipeline, because the headset opens only once. The code is in `signal2speech/eeg/app_live.py` (`LiveEegInput`).

```
python -m signal2speech.app --input live                        # pair the Unicorn first; calibrate, then the demo
python -m signal2speech.app --input live --arm-live-confirm     # only after #23's run says eye confirm is safe
python -m signal2speech.app --input simulated --p300 --sim 2,1  # the same code path on the Generator
```

Flags: `--calibration N` sets the P300 calibration sequences (default 10). `--alpha-calib-s S` sets the seconds of eyes open, then eyes closed (default 10).

**What happens**

1. **Device check.** It looks for a Unicorn before opening anything, because with no headset g.Pype's `start()` blocks instead of failing. If none is found within 15 s, or the stream sends no data within 8 s, it prints the pairing checklist and exits with code 3.
2. **Calibration on the app's own tiles.**
   - P300: N flash sequences, each naming the tile to watch, e.g. "look at “Compare counties” and count its flashes". `P300Chooser.finish_calibration()` then refits the LDA.
   - Alpha switch: eyes open, then eyes closed, then `AlphaConfirm.calibrate`.
   - If either calibration fails, keys 1 and 2 still work, and the window says so.
3. **Demo.**
   - Choose rounds flash the tiles at the chooser's validated timing: 5 flashes per tile, 100 ms on, 250 ms SOA. Each flash emits the P300 `Marker` on the frame the tile lights. The decision reaches the handler on the Qt main thread through `InputAdapter(LIVE_EEG)`.
   - Confirm rounds listen for one deliberate eye closure on the same pipeline.
   - The bottom strip reads **Input: Live EEG · Unicorn Hybrid Black · OSCAR on · eye confirm off (#23)**.
4. **Live confirm stays disarmed** (`handler.live_eeg_confirm_armed = False`) until #23's harness (`python -m signal2speech.eeg.live`) says it's safe. Until then, an eye closure is logged and rejected, key 1 confirms, and the Confirm hint says so. `--arm-live-confirm` turns eye confirm on.

**Simulated through the same path (`--input simulated --p300`).** This uses the same `LiveEegInput`, the same hooks, and the same calibration, on `gp.Generator` plus `SyntheticP300`, labelled **Simulated**. The `--sim` script alternates:
- the tile the synthetic brain attends in each Choose round (1 or 2)
- what it does in each Confirm round: 1 closes its eyes, so the alpha switch confirms; 2 keeps them open, so the confirm timeout cancels

The alpha branch uses its own Generator with `AlphaBursts`, because the P300 Generator carries a constant 10 Hz sine.

**Verified (2026-11-14, Linux, simulated only).** `--input simulated --p300 --sim 2,1 --calibration 6 --alpha-calib-s 2`:
- The P300 calibrated on 30 target and 30 non-target epochs, and the alpha ratio was 6.1.
- The P300 picked tile 2, giving a preview. An eye closure confirmed. The result was one map action and one spoken line.
- Peak memory was 310 MB, and the whole run took 38 s.

`tests/test_app_live.py` covers the simulated end-to-end run, the live wiring without hardware (shared pipeline, labels, disarmed hint, key 1 confirm), `--arm-live-confirm`, and the no-headset exit (code 3, under 15 s).

**Not verified: anything on a real wearer.** At the slot:
1. Pair the headset.
2. Run `--input live`.
3. Do one deliberate preview and confirm.
4. Record the result here and in #103.

The app's 5-flash, 250 ms timing still needs #101's flash-timing check on the judging laptop's real display.
