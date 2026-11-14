# Dev Setup and Docs

Record the verified launch command, vendor prerequisites, and revision.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#11](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/11)

## Python and g.Pype launch path (#19)

From the [g.Pype docs](https://gpype.gtec.at). **Each step is unverified until someone runs it on the demo laptop and checks it off in #19.**

| # | Step | Expected result | Verified |
| --- | --- | --- | --- |
| 1 | Install **Python 3.12** (64-bit, the verified version). Python 3.10 to 3.14 should also work, because we don't use g.Pype's EDF support, which has no Windows wheel on 3.13 and 3.14. | `py -3.12 --version` | ✅ 2026-11-14 |
| 2 | `py -3.12 -m venv .venv` then `.venv\Scripts\activate` (macOS/Linux: `source .venv/bin/activate`) | Prompt shows `(.venv)` | ✅ 2026-11-14 |
| 3 | `pip install -e ".[dev]"` (exact versions: `pip install -r requirements-lock.txt`; on a flaky network add `--resume-retries 30 --timeout 120`) | Installs `gpype[gui,devices]` (core includes OSCAR), h5py, scikit-learn, pyttsx3, and pytest. We skip LSL and EDF. | ✅ 2026-11-14 |
| 3b | `git config core.hooksPath .githooks` (same command on every OS) | Commits are scanned for secrets, raw EEG, and `.env` files. `git push` runs `pytest` first. Skip once with `SKIP_TESTS=1 git push` | ✅ 2026-11-14 |
| 4 | `pytest` | All contract tests pass | ✅ 2026-11-14 |
| 5 | `python -c "import gpype; print(gpype.__version__)"` | 4.2 or later | ✅ 2026-11-14 |
| 6 | Run a g.Pype example with `Generator` (for example `s1e4_time_series_scope.py` from the g.Pype repo) | The scope window shows a moving signal | ✅ 2026-11-14 (scope window ran 15 s with no errors) |
| 7 | Pair the Unicorn Hybrid Black in OS Bluetooth settings, then run `s3e2_hybrid_black.py` | 8 EEG traces at 250 Hz | ☐ (#23) |
| 8 | `python -m signal2speech.app` once #25 lands | The demo window opens on the first choice round | ☐ |

**Verified on 2026-11-14 (Windows 11):** Python 3.12.10, g.Pype 4.2.0, PySide6 6.11.3, `gtec_oscar` 1.3.2, `gtec_unicorn` 2.0.0. `pytest` passes 21 of 21. Built `Generator` → `Bandpass` → `TimeSeriesScope` with `HybridBlack` available. The install fails partway through on a flaky network unless you use `--resume-retries`.

**Linux dev machine (not the demo laptop):** steps 1–5 work with `uv venv --python 3.12 .venv && source .venv/bin/activate && uv pip install -e ".[dev]"`. That installs g.Pype 4.2.0 and PySide6 6.11.3. `QT_QPA_PLATFORM=offscreen pytest` passes, and `python -m signal2speech.eeg.simulated --picks 2,1` runs the g.Pype `Generator` path. Verified 2026-11-14 during #21.

**Offline demo:** g.Pype, the OpenOrbit data, and speech (`pyttsx3`) all work without Wi-Fi. Only AI Answering (#27) needs a network, and it falls back to saved phrases.

## Platform notes

CI (`.github/workflows/tests.yml`) runs `pytest` on Windows, Ubuntu, and macOS (Apple silicon) for every PR. The headset, audio, and Wi-Fi-off launch stay manual.

| | Windows 10/11 x64 | macOS (Apple silicon) | Linux x86_64 |
| --- | --- | --- | --- |
| Supported by g.Pype | Yes. Verified on the dev laptop and in CI. | macOS 13 or later (PySide6 6.10+). Intel Macs can't use the Unicorn driver. | Yes. No ARM Linux wheels. |
| Python | 3.12 (verified), 3.10–3.14 | 3.12 via python.org or Homebrew | 3.12 (CI also tests 3.13) |
| Extra system setup | None | Grant **Input Monitoring** to your terminal for g.Pype's `Keyboard` source. g.Pype needs the main thread's event loop (`MainApp.run()`). | `sudo apt install espeak-ng libegl1 libxkbcommon0 libbluetooth3` |
| Headset pairing | Settings → Bluetooth | System Settings → Bluetooth | `bluetoothctl` → `pair` / `trust` |
| Speech (`pyttsx3`) | SAPI5, built in | NSSpeechSynthesizer, built in | espeak-ng |
| Keyboard input | Works | Needs Input Monitoring | Needs an X11 session (`pynput`). Wayland may block it. |
| Paradigm Presenter | Licensed separately | Not available | Not available |

**Judging laptop:** use the Windows laptop. It's the only fully verified setup, and the only one where the Paradigm Presenter is an option.
