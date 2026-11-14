# DevOps

Keep an offline judging build and rollback path. Add PR smoke checks after the local check works.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15), [#14](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/14)

**Consolidated issues** · [#17](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/17), [#18](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/18)

## Smoke check (#41)

One hardware-free command. It needs no display, no network, and no headset.

```
python -m signal2speech.app --smoke            # dev: pieces not built yet are SKIP, exit 0 unless something FAILs
python -m signal2speech.app --smoke=judging    # judging laptop: any SKIP or WARN counts as FAIL
```

| Check | What it proves | Input label |
| --- | --- | --- |
| environment | Python, g.Pype 4.2 or later, and PySide6 import. Python other than 3.12 is a **WARN**. | — |
| demo numbers | In the spoken line (read with the app's own `load_demo_choices`), each county is followed in the same sentence by its exact rise: Washtenaw +186, Wayne +168. `1860` doesn't count. | — |
| openorbit assets | `data/openorbit/` has `SOURCES.md` and at least 2 images. Each county's before and after values must be on that county's own rows: Washtenaw 32 and 218, Wayne 58 and 226. **SKIP until #29 lands.** | — |
| openorbit view | `app.load_view()` returns the real view, not `PendingMapView`. **SKIP until #30 lands**; the app shows a labelled stand-in until then. | — |
| confirm flow | The real `App` with a fake map and speaker. Preview gives no output. Confirm gives exactly one `compare_air_quality` and one spoken line. | keyboard |
| cancel flow | Preview, then Cancel, gives no output. A late key gets `RejectedNoOpenRound`. | keyboard |
| g.Pype stream | A `Generator` → `Collector` pipeline delivers samples (about 1 s) | simulated |

The smoke prints these **MANUAL** checks and never runs them:
- headset pairing and 8-channel signal
- live P300 and alpha calibration (#23)
- evidence scopes (#48)
- audible speech
- the Wi-Fi-off full reveal

**Verified 2026-11-14 (Linux dev machine, Python 3.12.13):**
- `--smoke` gives `SMOKE PASS: 5 pass, 2 skip, 0 fail`. The skips are #29 and #30.
- `--smoke=judging` gives `SMOKE FAIL` with exit 1, as expected until #29 and #30 land.
- A deliberate double-output breakage makes `confirm flow` FAIL with exit 1. That's covered in `tests/test_diagnostics.py`.

### Diagnostics log

Each smoke run claims its own `logs/smoke-<timestamp>-<ms>-<pid>.jsonl`, so parallel runs never share a file. `logs/` is gitignored. Every row carries `input`, `gpype` (source), and `connection`, plus the event fields:

- rounds, previews, outcomes with `since_round_ms`, clears
- `output` rows with `sink_call_ms`: the time inside `AppSink.execute`, which covers the map update and *starting* speech. Qt plays speech asynchronously, so the audible duration isn't included.
- Attaching several `Diagnostics` to one sink wraps it once. Each one logs a single output row per confirm.

To log a real demo run, the #25 owner can add one line in `App.__init__`. It isn't wired in yet, because #41 may only touch `--smoke` in `app.py`:

```python
from signal2speech.diagnostics import Diagnostics
self.diag = Diagnostics.to_file().attach(h, input_source=input_source,
                                         gpype_source="Generator" if self.sim else "none",
                                         connection="n/a", sink=self.sink)
```

**Raw EEG guard (#10):** `Diagnostics.record()` uses an allow-list. It accepts scalars, dicts up to 3 levels deep, and lists of up to 32 scalars. Anything else raises `TypeError`, including arrays, deques, bytes, nested sample lists, and long strings. Nothing gets stringified as a fallback. Call `set_connection()` or `set_gpype_source()` when the headset state changes.

**Next:**
- #37 runs `pytest` and `--smoke` in GitHub Actions.
- #38 records one passing and one deliberately failing run.

## CI on every PR (#37)

`.github/workflows/tests.yml` runs on every pull request and every push to `main`.

- **Matrix:** Windows, Ubuntu, and macOS (Apple silicon) on Python 3.12, plus Ubuntu on 3.13. Qt runs offscreen.
- **Install:** `pip install -c requirements-lock.txt -e ".[dev]"`. Every package in the lock (g.Pype, PySide6, numpy, scipy, scikit-learn, h5py, and so on) gets its verified pin, and the pins have cp313 wheels too. Windows-only pins (pywin32, comtypes) are ignored elsewhere. Linux and macOS extras that the Windows-generated lock doesn't list (pynput's evdev and python-xlib, pyobjc) still float. The pip cache is keyed on `pyproject.toml` and the lock file.
- **Steps:**
  - install
  - version report (`importlib.metadata`, so it can't crash the job)
  - `pytest -q -rs`
  - `python -m signal2speech.app --smoke` (#41). It fails the job on any FAIL. Before #41, it was a visible "Smoke skipped" notice.
  - a **manual checks** list
- **Job summary:** each `ci (...)` job's summary shows the pytest exit code and result line, every skip with its reason, any FAILED or ERROR lines, the full smoke report with its exit code, and the manual checklist. It's written even when a step fails, so skips and failures are never silent. If the app can't even start, the smoke step fails instead of reporting a skip.
- **Cancelling runs:** a new push cancels the older run only on PRs. Each commit on `main` keeps its own result. Before this change, a quick second merge cancelled the first merge's run ([example](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43646992188)).
- **Linux packages** are the same list as in [platform notes](../dev-setup-docs/README.md#platform-notes). Only `espeak-ng` is installed, because pyttsx3 2.99 loads `libespeak-ng` and the legacy `libespeak1` isn't needed.
