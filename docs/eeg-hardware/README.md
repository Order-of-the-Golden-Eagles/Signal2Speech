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
