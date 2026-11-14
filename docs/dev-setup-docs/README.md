# Dev Setup and Docs

Record the verified launch command, vendor prerequisites, and revision.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#11](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/11)

## Python and g.Pype launch path (#19)

From the [g.Pype docs](https://gpype.gtec.at). **Each step is unverified until someone runs it on the demo laptop and checks it off in #19.**

| # | Step | Expected result | Verified |
| --- | --- | --- | --- |
| 1 | Install **Python 3.12** (64-bit). On Windows with 3.13 or 3.14, g.Pype's EDF support doesn't install. | `py -3.12 --version` | ✅ 2026-11-14 |
| 2 | `py -3.12 -m venv .venv` then `.venv\Scripts\activate` (macOS/Linux: `source .venv/bin/activate`) | Prompt shows `(.venv)` | ✅ 2026-11-14 |
| 3 | `pip install -e ".[dev]"` (exact versions: `pip install -r requirements-lock.txt`; on a flaky network add `--resume-retries 30 --timeout 120`) | Installs `gpype[all]`, PySide6, pyttsx3, and pytest | ✅ 2026-11-14 |
| 4 | `pytest` | All contract tests pass | ✅ 2026-11-14 |
| 5 | `python -c "import gpype; print(gpype.__version__)"` | 4.2 or later | ✅ 2026-11-14 |
| 6 | Run a g.Pype example with `Generator` (for example `s1e4_time_series_scope.py` from the g.Pype repo) | The scope window shows a moving signal | ✅ 2026-11-14 (scope window ran 15 s with no errors) |
| 7 | Pair the Unicorn Hybrid Black in OS Bluetooth settings, then run `s3e2_hybrid_black.py` | 8 EEG traces at 250 Hz | ☐ (#23) |
| 8 | `python -m signal2speech.app` once #25 lands | The demo window opens on the first choice round | ☐ |

**Verified on 2026-11-14 (Windows 11):** Python 3.12.10, g.Pype 4.2.0, PySide6 6.11.3, `gtec_oscar` 1.3.2, `gtec_unicorn` 2.0.0. `pytest` passes 21 of 21. Built `Generator` → `Bandpass` → `TimeSeriesScope` with `HybridBlack` available. The install fails partway through on a flaky network unless you use `--resume-retries`.

**Offline demo:** g.Pype, the OpenOrbit data, and speech (`pyttsx3`) all work without Wi-Fi. Only AI Answering (#27) needs a network, and it falls back to saved phrases.
