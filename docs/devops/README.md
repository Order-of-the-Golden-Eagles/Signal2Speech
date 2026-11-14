# DevOps

Keep an offline judging build and rollback path. Add PR smoke checks after the local check works.

**Active work** · [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15), [#14](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/14)

**Consolidated issues** · [#17](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/17), [#18](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/18)

## Smoke check (#41)

One hardware-free command. It needs no display, no network, and no headset.

```
python -m signal2speech.app --smoke            # dev: pieces not built yet are SKIP, exit 0 unless something FAILs
python -m signal2speech.app --smoke=judging    # judging laptop: any SKIP counts as FAIL
```

| Check | What it proves | Input label |
| --- | --- | --- |
| environment | Python, g.Pype 4.2 or later, PySide6 import | — |
| demo numbers | The spoken line in `contracts/demo-round.json` matches EPA 32→218 (+186) and 58→226 (+168) | — |
| openorbit assets | `data/openorbit/` has `SOURCES.md`, at least 2 images, and the four AQI values. **SKIP until #29 lands.** | — |
| openorbit view | `signal2speech.openorbit.OpenOrbitView` imports. **SKIP until #30 lands**; the app shows a labelled stand-in until then. | — |
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

Each smoke run writes `logs/smoke-<timestamp>.jsonl`; `logs/` is gitignored. Every row carries `input`, `gpype` (source), and `connection`, plus the event fields:

- rounds, previews, outcomes with `since_round_ms`, clears
- `output` rows with `output_ms`, measured from the decision to the end of the map and speech

To log a real demo run, the #25 owner can add one line in `App.__init__`. It isn't wired in yet, because #41 may only touch `--smoke` in `app.py`:

```python
from signal2speech.diagnostics import Diagnostics
self.diag = Diagnostics.to_file().attach(h, input_source=input_source,
                                         gpype_source="Generator" if self.sim else "none",
                                         connection="n/a", sink=self.sink)
```

**Raw EEG guard (#10):** `Diagnostics.record()` raises `TypeError` for numpy arrays and for lists longer than 32 items, so sample data can't reach a log. Call `set_connection()` or `set_gpype_source()` when the headset state changes.

**Next:**
- #37 runs `pytest` and `--smoke` in GitHub Actions.
- #38 records one passing and one deliberately failing run.
