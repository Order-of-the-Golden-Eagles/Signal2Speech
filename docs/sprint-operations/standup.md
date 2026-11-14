# Standup snapshot

**As of 11/14/26, 5:30 PM Eastern.** Sources: `gh pr list`, `gh issue list`, `gh run list`, DEVLOG.md, docs/MEMORY.md. Part of #16.

## What works now (merged to main)

| What | PR | How verified |
|---|---|---|
| Selection contract | [#44](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/44) | Docs and tests |
| Python + g.Pype environment, versions pinned; g.Pype GUI launches | [#52](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/52), [#55](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/55), [#59](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/59) | Local install and launch |
| PySide6 selection UI and flash scheduler | [#51](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/51) | Unit tests, offscreen |
| Integrated app: one map action and one spoken line per confirm | [#54](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/54), [#60](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/60) | Keyboard and simulated input, Wi-Fi off, dev Mac on macOS 12. Map is a stand-in until #30 |
| AI answering | [#57](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/57) | Tests |
| Simulated brain through the real g.Pype pipeline | [#53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53) | Simulated only; 82 tests pass |
| Evidence view: scopes, averaged P300, record and replay | [#56](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/56) | Simulated and recorded |
| P300 chooser: flash markers, epochs, LDA, class 1/2 | [#63](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/63) | Simulated only, not yet live |
| CI: pytest on Windows, macOS, Linux | [#64](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/64) | Latest main run passed |

Nothing has been verified on live EEG yet.

## Owners: in-flight PRs and next task

- **vas2000-personal:** [#66](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/66) git hooks (one CI failure, rerun in progress). Next: #40 pre-headset checkpoint, then #23 live selection and #48 live evidence.
- **MagicJester2764:** [#58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58) alpha confirm (#47), [#61](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/61) smoke command (#41, CI failing), [#68](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/68) CI follow-up (#37, CI failing), [#67](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/67) devlog backfill. Next: fix CI on #61 and #68, then #26 cancel and disconnect.
- **InYoung-Song:** [#65](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/65) OpenOrbit data and view (#29, #30), CI passing. Next: #31/#32 FIRMS, #35 secrets check, #39 offline launch.
- **LongNguyenThanhLe:** [#69](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/69) devlog backfill. Next: #33 judging review, #34 submission video.

## Next checkpoint

1. **#40 pre-headset checkpoint:** full app on simulated g.Pype input, smoke passing, open PRs merged.
2. **8:15 PM: #23 live Unicorn selection.** First live P300 and alpha calibration on a real wearer.

## Top 3 risks

1. **Live P300 accuracy and flash timing.** The chooser and alpha confirm are proven only on simulated data. Live confirm stays off until #23 says it is safe.
2. **Open PRs need review.** Seven PRs open (#58, #61, #65, #66, #67, #68, #69); #61 and #68 have failing CI. #58 and #61 matter for #40.
3. **macOS 12 setup blocker (#19).** `gpype[gui]` 4.2 needs PySide6 6.10.1+, with no macOS 12 wheel. g.Pype work needs macOS 13+ or Windows.
