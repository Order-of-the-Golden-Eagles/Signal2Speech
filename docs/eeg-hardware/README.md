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

**Checklist for live runs:** pair the Unicorn in the OS Bluetooth settings first, check signal quality on all 8 channels, calibrate the P300 (trial count to be set in #46) and the alpha threshold (#47), and record which classes map to which tiles.

**Ask the g.tec mentor:** Paradigm Presenter licence (we use our own PySide6 flashing), access to the MCP visualizer from the workshop, and whether one headset can stream to two apps at once.

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

- **Calibration:** `Calibration.from_samples(open, closed)` sets `level = sqrt(open_p95 × closed_median)` and `release = sqrt(open_p95 × level)`, a geometric midpoint with hysteresis. It refuses when the closed median is under 2× the open p95 (`CalibrationError`). The levels are applied live through `Threshold.set_control()`. Until calibration runs, the level is 1e12, so nothing fires.
- **Gating, on top of the threshold:**
  1. It only listens in an armed Confirm round. Arming happens through `handler.on_round_opened`; cancel or clear disarms it.
  2. The eyes must have been open for `settle_s` since arming. If they were closed when the preview appeared, they have to open first.
  3. Only a rising edge counts. It disarms after one decision, so one closure gives one event.
- **Live EEG:** labelled `live-eeg`. The handler still returns `RejectedLiveConfirmDisarmed` until #23 sets `live_eeg_confirm_armed`. The decoder works, and the contract holds it back.
- **Sharing the headset with #46:** a Unicorn opens only once. Pass `AlphaConfirm(handler, pipeline=p, upstream=bandpass_node, input_source=LIVE_EEG)` to hang the alpha branch off the P300 pipeline instead of opening a second source.
- **Tests:** `tests/test_alpha_confirm.py` covers the calibration math, every gating rule, the live-disarmed contract, and one Generator burst through the real pipeline giving exactly one confirm and no rest triggers.

**Simulated results (Generator with 10 µV noise, 2026-11-14)**

| Burst | Open p95 | Closed median | Ratio | Level / release | False triggers, 60 s eyes-open | Edges per closure | Latency from closure to edge |
| --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| 8 µV | 10.6 | 68.8 | 6.5 | 27.0 / 16.9 | **0** | 1, 1, 1, 1, 1 | 1.21–1.45 s |

Latency is about 0.3–0.5 s for the 1 s FFT window to fill with alpha, plus the 1.0 s dwell. With `--dwell-s 0.5` the switch reacts faster but chatters more. Real eyes-closed alpha is typically 2–10× eyes-open, and some people have weak alpha, so the 2× floor is the first thing to check at the headset slot.

**Fallback (if P300 is unreliable): not built yet.** The plan is to step through the options one at a time and confirm each with this switch. `AlphaConfirm` acts only in Confirm rounds today, so stepping needs a small driver:

1. Highlight one tile at a time.
2. Arm for each highlight.
3. Send the highlighted target on a rising edge.

Then confirm with `AlphaConfirm` as usual. The `rising` signal and the calibration are reusable as-is.

**g.Pype facts we confirmed:**

- `ChannelMean` and `AlphaBursts` are custom `gp.IONode`s. For a 1-channel output, `setup()` sets `channel_count`, `channel_roles`, and `channel_labels` in the output context.
- `Threshold.set_control({"level", "release", "dwell"})` works while the pipeline runs.
- More than one `Pipeline` can run in a process. g.Pype refuses only a faster-than-real-time replay beside another pipeline.
