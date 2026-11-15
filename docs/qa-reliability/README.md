# QA and Reliability

Verify confirmation, cancellation, duplicate events, disconnects, and offline launch. Record live EEG results separately.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13), [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#9](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/9)

## Automated checks

- `pytest`: the contract scenarios, UI, app, AI, evidence, and EEG tests. Run it with `QT_QPA_PLATFORM=offscreen` on a machine with no display.
- `python -m signal2speech.app --smoke`: one confirm and one cancel through the real app with fake output, plus the demo numbers, assets, and a g.Pype stream. It exits 0 or 1. Use `--smoke=judging` on the judging laptop. See [DevOps](../devops/README.md#smoke-check-41).
- Live EEG, audio, and Wi-Fi-off are manual checks. The smoke lists them under MANUAL. Record live results separately.

## Soak test: the judging hour (#165)

Judging lasts an hour, and judges come back. `tests/soak/soak.py` runs the real app through the crash-safe launcher (#133) for that long, with its own simulated input, and checks it doesn't crash, double up an output, leak memory, or slow down.

```
python tests/soak/soak.py --minutes 60 --p300 --kill-at 30      # the judging-laptop run (about 61 min)
python tests/soak/soak.py --minutes 5 --windowed --mute          # a quick check
```

- **What it drives:** `tools/demo_launcher.py -- --input simulated --p300 --sim <script>`. That's the live code path (P300 chooser and alpha switch) on the g.Pype Generator, labelled Simulated. The script repeats choose → preview → confirm, three times out of four, and choose → preview → no eye closure, so the confirm timeout cancels. It's long enough that it never runs out. Without `--p300` it uses the plain simulated decoder.
- **What it reads:** the app's transcript as it streams, with each line stamped on arrival. The raw copy goes to `logs/soak-<time>.log`.
- **Pass needs all of these:**
  - **0 double outputs:** every `Confirmed` has exactly one map action and one spoken line, and no output appears on a cancelled or timed-out round.
  - **0 unplanned app exits and 0 Python tracebacks.**
  - **Memory stable:** the RSS of each app process, sampled every minute with psutil, grows less than +50 MB or +15% (whichever is larger), judged from 90 s after that process started. On Windows it samples the real interpreter, not the venv's `python.exe` stub.
  - **Keeps going at the same speed:** a round finishes at least every 180 s, and the median selection time in the last 10 minutes is at most 1.5× the first 10.
  - **The kill test:** with `--kill-at`, the app is killed on purpose once, and the launcher must start a new one. A requested kill that never happened is a FAIL. Ctrl+C still writes the report, marked as stopped early. The report gives both times: when the new process appeared, and when it was logging again.
- **Report:** `logs/soak-<time>.md` has the verdict, the exact command, the machine, round counts, crashes, memory start vs end, and the median selection time (Choose round opens → preview) and confirm → map time, first 10 minutes vs last 10. Paste it into #165. `logs/` stays out of git.
- **Tests:** `tests/test_soak.py` pins the pass/fail parsing (double outputs, cancels with output, restarts, a run cut mid-confirm) without starting the app.

### Results

| Where | Input | Run | Result |
| --- | --- | --- | --- |
| Dev machine (Linux, 8 CPUs, offscreen, muted), 11/15/26 03:09–04:09 | Simulated, `--p300` | `--minutes 60 --p300 --kill-at 30 --windowed --mute` | **PASS.** 226 previews, 169 confirms, 56 cancels (all by the confirm timeout), 169 map actions and 169 spoken lines, **0 double outputs**, 0 crashes, 0 Python errors. Kill at 30 min: a new app process after 1.1 s, logging again after 5.4 s. Memory: first app process 226 → 241 MB over minutes 2–30 (peak 302 MB during start-up). After the restart, the progress lines read 299–303 MB from minute 53 to 59. (That run's report covered only the first process; the soak now gives a row per app process.) Selection time (Choose round opens → preview), median: 3.10 s in the first 10 min, 3.20 s in the last 10. Confirm → map: 1 ms both. |
| Judging laptop, Wi-Fi off | Simulated, `--p300` | Not run yet. Part D of the [judging laptop session](../devops/judging-laptop-session.md#part-d-optional-the-judging-hour-soak-165) | |

## Recovery checks (#26)

`tests/test_recovery.py` runs every case through the real `App` with a fake map and speaker. It asserts that nothing fires an extra map action or spoken line.

| Case | Inputs exercised | Result |
| --- | --- | --- |
| Cancel during preview: Esc, key 2, confirm timeout | keyboard and simulated | Round cleared (`cancel` or `timeout`), 0 outputs. Late simulated decisions are dropped. |
| Disconnect during preview: key D, g.Pype stream stop (`SimulatedDecoder.disconnect_stream()`) | keyboard and simulated | Round cleared (`disconnect`), and the in-flight confirm from the stopped stream is dropped. 0 outputs. |
| Duplicate event ID, held or repeated confirm key, the same simulated decision twice, the same recording replayed twice | keyboard, simulated, recorded | `RejectedDuplicateEvent`, `RejectedRoundConsumed`, or `RejectedNoOpenRound`. Exactly 1 output. |
| Stale decision from the Choose round arriving in the Confirm round, late decision from a closed round | keyboard, recorded, simulated | `RejectedStaleRound` or dropped before the adapter. 0 outputs. |
| Gauntlet: cancel, disconnect, stale, and duplicate, then one real confirm and a repeat | keyboard and recorded | Exactly 1 map action and 1 spoken line |

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_recovery.py -v` (23 tests, about 10 s). The g.Pype-only cases skip, with a reason, where g.Pype isn't installed. Key D is tested through its real `QShortcut`. A timeout in the Confirm round replays the simulator's choose+confirm pair, so a scripted rehearsal stays aligned. `App.close()` stops the confirm and reopen timers. Recorded input is the contract's sample events replayed with `source: recorded`. Live EEG recovery is #23.

**Gap (not in #26):** nothing notices a stream that **stalls without stopping**, for example the headset going silent. Only an explicit stop or disconnect clears the round. A sample-count watchdog that calls `handler.disconnect()` belongs with the live run (#23).

## Tests on machines without g.Pype (#98)

g.Pype can't be installed everywhere: macOS 12, Intel Macs, and ARM Linux. Tests that need it carry a `needs_gpype` skip marker (`tests/test_diagnostics.py`, `tests/test_recovery.py`), so `pytest` is green there with a visible reason (`pytest -rs`). CI installs g.Pype from `requirements-lock.txt` and still runs them on Windows, macOS, and Linux. Mark only the tests that need it, never a whole file.
