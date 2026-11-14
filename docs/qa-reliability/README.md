# QA and Reliability

Verify confirmation, cancellation, duplicate events, disconnects, and offline launch. Record live EEG results separately.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13), [#15](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/15)

**Consolidated issues** · [#9](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/9)

## Automated checks

- `pytest`: the contract scenarios, UI, app, AI, evidence, and EEG tests. Run it with `QT_QPA_PLATFORM=offscreen` on a machine with no display.
- `python -m signal2speech.app --smoke`: one confirm and one cancel through the real app with fake output, plus the demo numbers, assets, and a g.Pype stream. It exits 0 or 1. Use `--smoke=judging` on the judging laptop. See [DevOps](../devops/README.md#smoke-check-41).
- Live EEG, audio, and Wi-Fi-off are manual checks. The smoke lists them under MANUAL. Record live results separately.
