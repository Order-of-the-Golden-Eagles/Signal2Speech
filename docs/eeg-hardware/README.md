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
