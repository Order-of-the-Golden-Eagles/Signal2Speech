# QA and Reliability

Verify confirmation, cancellation, duplicate events, disconnects, and offline launch. Record live EEG results separately.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13), [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#9](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/9)

## Automated checks

- `pytest`: the contract scenarios, UI, app, AI, evidence, and EEG tests. Run it with `QT_QPA_PLATFORM=offscreen` on a machine with no display.
- `python -m signal2speech.app --smoke`: one confirm and one cancel through the real app with fake output, plus the demo numbers, assets, and a g.Pype stream. It exits 0 or 1. Use `--smoke=judging` on the judging laptop. See [DevOps](../devops/README.md#smoke-check-41).
- Live EEG, audio, and Wi-Fi-off are manual checks. The smoke lists them under MANUAL. Record live results separately.

## Recovery checks (#26)

`tests/test_recovery.py` runs every case through the real `App` with a fake map and speaker. It asserts that nothing fires an extra map action or spoken line.

| Case | Inputs exercised | Result |
| --- | --- | --- |
| Cancel during preview: Esc, key 2, confirm timeout | keyboard and simulated | Round cleared (`cancel` or `timeout`), 0 outputs. Late simulated decisions are dropped. |
| Disconnect during preview: key D, g.Pype stream stop (`SimulatedDecoder.disconnect_stream()`) | keyboard and simulated | Round cleared (`disconnect`), and the in-flight confirm from the stopped stream is dropped. 0 outputs. |
| Duplicate event ID, held or repeated confirm key, the same simulated decision twice, the same recording replayed twice | keyboard, simulated, recorded | `RejectedDuplicateEvent`, `RejectedRoundConsumed`, or `RejectedNoOpenRound`. Exactly 1 output. |
| Stale decision from the Choose round arriving in the Confirm round, late decision from a closed round | keyboard, recorded, simulated | `RejectedStaleRound` or dropped before the adapter. 0 outputs. |
| Gauntlet: cancel, disconnect, stale, and duplicate, then one real confirm and a repeat | keyboard and recorded | Exactly 1 map action and 1 spoken line |

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_recovery.py -v` (18 tests, about 8 s). Recorded input is the contract's sample events replayed with `source: recorded`. Live EEG recovery is #23.

**Gap (not in #26):** nothing notices a stream that **stalls without stopping**, for example the headset going silent. Only an explicit stop or disconnect clears the round. A sample-count watchdog that calls `handler.disconnect()` belongs with the live run (#23).
