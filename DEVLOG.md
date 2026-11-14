# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 4:46 PM - MagicJester2764 (with Claude) - #21 Simulated input ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The app can be driven by a fake brain running through the real g.Pype pipeline, so the team can rehearse the whole flow without the headset
    - `python -m signal2speech.eeg.simulated --picks 2,1` chooses tile 2, then confirms. Every event is labelled "simulated"
    - `--ui` opens the selection window, where Ctrl+1 and Ctrl+2 decide for the "brain"
- A late decision from an old round is thrown away before it can land in the next round. Without this, a slow answer could have confirmed something the wearer never meant to confirm
- Added a drop-in replacement for the app's placeholder simulator. Swapping it in is one line for the #25 owner
- Found that tests must create the Qt app as `QApplication`. Otherwise the UI tests crash the whole test run. This is recorded in MEMORY.md
- Verified on a Linux laptop with simulated input only, not yet on the judging laptop

## 11/14/26 - 4:56 PM - MagicJester2764 (with Claude) - #47 Alpha-switch confirm ([PR #58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58))
- The wearer can now confirm by closing their eyes for about 2 seconds. That raises the brain's alpha rhythm, and one closure sends exactly one Confirm
    - It only listens while a "Say this?" preview is on screen. The eyes have to be open for a moment first, so a blink or closure from the previous screen can't confirm by accident
- Calibration takes 10 seconds with eyes open and 10 seconds with eyes closed. It refuses if the two aren't clearly different
- On simulated brain data (normal and weak alpha), there were no false triggers in 60 seconds of eyes-open rest. Every closure gave exactly one confirm, about 1.2–1.5 seconds after the eyes closed
- The alpha switch can share the headset with the P300 chooser (#46), because the Unicorn can only be opened once
- Still to do at the headset slot: calibrate on a real wearer (#23). Live confirm stays switched off in the app until #23 says it's safe

## 11/14/26 - 5:01 PM - MagicJester2764 (with Claude) - #41 Smoke command and diagnostics ([PR #61](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/61))
- Added one command that checks the demo without a headset, internet, or screen: `python -m signal2speech.app --smoke`
    - It runs a confirm and a cancel through the real app with fake output, checks that the spoken AQI numbers match the EPA data, and checks that g.Pype can stream
    - Pieces that aren't built yet (the NASA/EPA files from #29 and the map from #30) show as SKIP, so nothing looks finished when it isn't. `--smoke=judging` treats a SKIP as a failure for the final build
    - It lists the checks that need a person: headset, live calibration, audio, Wi-Fi off
- Every run writes a timing log to `logs/` (not committed) with the input mode and connection state. The log refuses raw EEG data on purpose
- Breaking the app on purpose so it spoke twice made the smoke check fail, which shows it catches real problems

## 11/14/26 - 5:15 PM - In Young Song (with Claude) - #29 NASA and EPA dataset ([PR #65](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/65))
- The OpenOrbit demo now has its real data, bundled in the repo so it works with Wi-Fi off
    - `data/openorbit/`: two NASA satellite images of southeast Michigan (June 26 and 28, 2023), the EPA air-quality rows, map marker places, and `SOURCES.md` with every link
- The EPA numbers were checked against EPA's own file: Washtenaw 32 to 218 (+186), Wayne 58 to 226 (+168). `python data/openorbit/build_dataset.py --verify-only` re-checks the files offline
- June 26 is mostly cloud on both NASA satellites, so the "before" picture shows little ground. The AQI numbers carry the before and after. The team can decide later whether to change it
- Verified on Windows with no headset. NASA's coastline map lines up with the image, and the markers sit where EMU and Detroit really are

## 11/14/26 - 5:15 PM - In Young Song (with Claude) - #30 Offline wildfire comparison view ([PR #65](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/65))
- After a confirm, the app now shows the real map instead of the "not built yet" placeholder
    - "Show the satellite view" shows June 28 with EMU and Detroit marked. "Compare counties" shows both days side by side with the AQI table and which county rose most versus which ended highest
- The numbers on screen come from the EPA file, and a test checks that they match the spoken line, so the screen and the voice can't disagree
- Sized to fit next to the selection tiles on a 1920x1080 laptop at 125% scaling. Before this, the window ran off the screen
- If the data folder is missing, the panel says so clearly instead of crashing the app
- Verified on Windows with keyboard input and every network call blocked: one map change and one spoken line per confirm. Still needs a real Wi-Fi-off run on the judging laptop (#39)
## 11/14/26 - 5:15 PM - MagicJester2764 (with Claude) - #21 Code review fixes ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The full app now runs on the fake g.Pype brain: `python -m signal2speech.app --input simulated` (wired in by #60)
- A code review found that pressing Esc during a scripted run threw the script out of order. Now a cancelled step is retried, and a step the keyboard already did is skipped
- Picking with Ctrl+1/Ctrl+2 now waits until the tiles finish flashing, the same as the real P300 will
- The headless runner handles longer scripts, and a run that times out now reports failure instead of success
- Closing the simulator fully disconnects it, so a restarted app can't end up with two simulators
- Verified on simulated input: 82 tests pass, and the integrated app gave one preview, then one reveal and one spoken line
