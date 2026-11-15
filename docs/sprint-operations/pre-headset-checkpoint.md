# Pre-headset checkpoint (#40)

**Snapshot:** 11/14/26, 7:00 PM ET, `main` at `bfce988`. Block 2 ends at 8:15 PM. Each developer, please confirm or correct your row in [#40](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/40).

## Evidence: the reveal works without a headset

| Input | What ran | Result | Evidence |
| --- | --- | --- | --- |
| **Keyboard, Wi-Fi off** | `python -m signal2speech.app --input keyboard` on InYoung's Windows 11 laptop, commit `eecc31a` (older than `bfce988`, with the same lock file) | Keys 2,1 give the compare view and one spoken line. Keys 1,1 give the satellite view and one line. Keys 2,2 give nothing. | [#39 comment](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/39) |
| **Simulated, real g.Pype stream** | `python -m signal2speech.app --input simulated --sim 2,1 --mute` on `bfce988` (Linux, offscreen, **Wi-Fi on, muted**, so the spoken line was logged, not heard) | One preview with no output, then one `compare_air_quality` map action and one spoken line. The real NASA/EPA view shows. The judge strip reads *Input: Simulated · Connection: g.Pype Generator stream*. | Re-run the command; add `--screenshot out.png` for an image |
| **Smoke check** | `python -m signal2speech.app --smoke` on `bfce988` | `SMOKE PASS: 7 pass, 0 skip, 0 fail`. The #29 assets and the #30 view now pass, so `--smoke=judging` is usable. | [DevOps](../devops/README.md#smoke-check-41) |
| **CI, every PR** | `pytest` and smoke on Windows, macOS, and Ubuntu | Green on `bfce988` | [run 43655531748](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/actions/runs/43655531748) |

None of this is live EEG. Still unverified: simulated input with Wi-Fi off, and audible speech on the judging laptop.

## Each developer: works, next, blocked

| Developer | Works (merged) | Next | Blocked on |
| --- | --- | --- | --- |
| **Vasanth** | Contract (#22), the Python/g.Pype pivot, environment (#19), evidence view (#56, synthetic), P300 chooser (#63, synthetic), CI (#64), git hooks (#66), duplicate-ID fix (#82) | Live-run harness #78 (**conflicts with `main`**), flash timing tool #77, evidence driven by the chooser #76, run of show #74 | The headset slot for #23 and #46's live accuracy |
| **Long** | Selection UI (#51), the app (#54), AI Answering (#57), speech (#60), real map in the app (#81), judging build rollback (#86), first security pass (#85) | Judging laptop session script #88 | The final security pass waits on the #42 freeze |
| **InYoung** | OpenOrbit data and view (#65), the release check, the Wi-Fi-off keyboard run on her laptop (#39), the rollback rehearsal (#42) | FIRMS #89 (stretch), tag `judging-draft` (#42; the runbook's name for `judging-v1`) | Nothing |
| **MagicJester2764** | Simulated input (#21), alpha confirm (#47), smoke and diagnostics (#41), CI follow-up (#37/#38), recovery checks (#26), this checkpoint (#40) | **Owns the Wi-Fi-off run on the judging laptop** (#39 handoff, `docs/devops/judging-build.md`). Run it with simulated input too, and with audio on. | #2 needs the headset slot |

## Remaining live blocker

**Live EEG isn't wired into the app.** `python -m signal2speech.app --input live` refuses to start. This PR updates that refusal message to name the real gap, because the old one blamed #46 and #47, which are merged. What's missing is the #23 wiring:

1. Open one `HybridBlack(enable_oscar=True)` pipeline in `App`. Hang the P300 branch and `AlphaConfirm(pipeline=, upstream=)` off it, because the Unicorn opens only once.
2. Connect the chooser to the tile flasher (`P300Chooser.attach(FlashScheduler)`) and label the input **Live EEG**.
3. Set `handler.live_eeg_confirm_armed = True` only after #23 verifies the round boundary.
4. At the slot: pair, calibrate the P300 and the alpha threshold on the wearer, then run one deliberate preview and confirm.

Other risks for Block 3:
- The app's tile timing (175 ms SOA, 10 flashes per tile) hasn't been validated against the chooser's synthetic settings (250 ms, 5 per tile). See #77.
- #78 conflicts with `main`.
- Nothing notices a headset that goes silent without disconnecting (#26 gap).

**Fallback if live isn't ready by 8:15:** demo the reveal with keyboard and simulated input, labelled as such. If the headset is at least paired, the evidence view (#48) can show **Live EEG** OSCAR on and off and the eyes-closed alpha peak. Otherwise show it labelled **Simulated** or **Recorded**. Never present Generator output as live.
