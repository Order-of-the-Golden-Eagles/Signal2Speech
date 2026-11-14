# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 4:46 PM - MagicJester2764 - #21 Simulated input ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The app can be driven by a fake brain running through the real g.Pype pipeline, so the team can rehearse the whole flow without the headset
    - `python -m signal2speech.eeg.simulated --picks 2,1` chooses tile 2, then confirms. Every event is labelled "simulated"
    - `--ui` opens the selection window, where Ctrl+1 and Ctrl+2 decide for the "brain"
- A late decision from an old round is thrown away before it can land in the next round. Without this, a slow answer could have confirmed something the wearer never meant to confirm
- Added a drop-in replacement for the app's placeholder simulator. Swapping it in is one line for the #25 owner
- Found that tests must create the Qt app as `QApplication`. Otherwise the UI tests crash the whole test run. This is recorded in MEMORY.md
- Verified on a Linux laptop with simulated input only, not yet on the judging laptop

## 11/14/26 - 4:56 PM - MagicJester2764 - #47 Alpha-switch confirm ([PR #58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58))
- The wearer can now confirm by closing their eyes for about 2 seconds. That raises the brain's alpha rhythm, and one closure sends exactly one Confirm
    - It only listens while a "Say this?" preview is on screen. The eyes have to be open for a moment first, so a blink or closure from the previous screen can't confirm by accident
- Calibration takes 10 seconds with eyes open and 10 seconds with eyes closed. It refuses if the two aren't clearly different
- On simulated brain data (normal and weak alpha), there were no false triggers in 60 seconds of eyes-open rest. Every closure gave exactly one confirm, about 1.2–1.5 seconds after the eyes closed
- The alpha switch can share the headset with the P300 chooser (#46), because the Unicorn can only be opened once
- Still to do at the headset slot: calibrate on a real wearer (#23). Live confirm stays switched off in the app until #23 says it's safe

## 11/14/26 - 5:01 PM - MagicJester2764 - #41 Smoke command and diagnostics ([PR #61](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/61))
- Added one command that checks the demo without a headset, internet, or screen: `python -m signal2speech.app --smoke`
    - It runs a confirm and a cancel through the real app with fake output, checks that the spoken AQI numbers match the EPA data, and checks that g.Pype can stream
    - Pieces that aren't built yet (the NASA/EPA files from #29 and the map from #30) show as SKIP, so nothing looks finished when it isn't. `--smoke=judging` treats a SKIP as a failure for the final build
    - It lists the checks that need a person: headset, live calibration, audio, Wi-Fi off
- Every run writes a timing log to `logs/` (not committed) with the input mode and connection state. The log refuses raw EEG data on purpose
- Breaking the app on purpose so it spoke twice made the smoke check fail, which shows it catches real problems

## 11/14/26 - 5:15 PM - MagicJester2764 - #21 Code review fixes ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The full app now runs on the fake g.Pype brain: `python -m signal2speech.app --input simulated` (wired in by #60)
- A code review found that pressing Esc during a scripted run threw the script out of order. Now a cancelled step is retried, and a step the keyboard already did is skipped
- Picking with Ctrl+1/Ctrl+2 now waits until the tiles finish flashing, the same as the real P300 will
- The headless runner handles longer scripts, and a run that times out now reports failure instead of success
- Closing the simulator fully disconnects it, so a restarted app can't end up with two simulators
- Verified on simulated input: 82 tests pass, and the integrated app gave one preview, then one reveal and one spoken line

## 11/14/26 - 5:20 PM - MagicJester2764 - #41 Code review fixes ([PR #61](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/61))
- A code review found the asset check was too easy to fool: it would pass if the right numbers appeared anywhere in the data. Now Washtenaw's and Wayne's AQI values have to be on their own rows
- The spoken-line check now needs the exact rise next to each county, so a typo like "1860" can't pass
- The raw-EEG guard on the log can no longer be sidestepped by nesting data or using another container type
- The judging check now fails on the wrong Python version. A weird g.Pype version string gives a clear failure instead of a crash
- Two smoke runs at the same moment get separate log files, and the log no longer claims to time how long speech plays (it only times starting it)
- Verified: 89 tests pass, and `python -m signal2speech.app --smoke` reports 5 pass, 2 skip (#29, #30)
- Follow-up: CI on Python 3.13 caught that the new version warning broke a test. Fixed; the smoke check still passes in dev mode on 3.13 and only fails in judging mode
