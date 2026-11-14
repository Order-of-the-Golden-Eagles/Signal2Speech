# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 4:28 PM - Long Le (with Claude) - #24 Keyboard preview screen ([PR #51](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/51))
- The wearer's screen exists: two big choice tiles, then a "Say this?" preview with Confirm and Cancel
    - `python -m signal2speech.ui`. Press 1 or 2 to pick, 1 to confirm, 2 or Esc to cancel
- A strip along the bottom shows judges the input type (Keyboard, Simulated, Recorded, Live EEG), the round, and the last result, so simulated input is never mistaken for the headset
- The tiles can flash, and each flash tells the P300 chooser (#46) which tile lit, at the moment it lit
- Holding a key down doesn't repeat. Otherwise a held 2 would pick a reply and then immediately cancel it
- Verified with the keyboard on a Mac (macOS 12), not yet on the judging laptop

## 11/14/26 - 4:39 PM - Long Le (with Claude) - #4 One complete choose, preview, and confirm flow ([PR #54](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/54))
- The whole demo flow runs in one app: choose, preview, then confirm (the map changes and the line is spoken once) or cancel (nothing happens)
    - `python -m signal2speech.app --input keyboard` or `--input simulated`. Press D to fake a headset disconnect
- Only one place in the code can speak or change the map, so a repeated or late signal can't make the app talk twice
- A transcript panel shows every round, preview, and result, so judges can follow what happened
- The map is a clearly labelled stand-in until the OpenOrbit view (#30) is built
- Verified with Wi-Fi off on a Mac: one map change and one spoken line per confirm, and silence on cancel. Not yet on the judging laptop

## 11/14/26 - 4:46 PM - MagicJester2764 - #21 Simulated input ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The app can be driven by a fake brain running through the real g.Pype pipeline, so the team can rehearse the whole flow without the headset
    - `python -m signal2speech.eeg.simulated --picks 2,1` chooses tile 2, then confirms. Every event is labelled "simulated"
    - `--ui` opens the selection window, where Ctrl+1 and Ctrl+2 decide for the "brain"
- A late decision from an old round is thrown away before it can land in the next round. Without this, a slow answer could have confirmed something the wearer never meant to confirm
- Added a drop-in replacement for the app's placeholder simulator. Swapping it in is one line for the #25 owner
- Found that tests must create the Qt app as `QApplication`. Otherwise the UI tests crash the whole test run. This is recorded in MEMORY.md
- Verified on a Linux laptop with simulated input only, not yet on the judging laptop

## 11/14/26 - 4:50 PM - Long Le (with Claude) - #5 AI reply suggestions ([PR #57](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/57))
- A judge types a question, and the wearer gets two short replies to pick from. The chosen one is previewed, then spoken once
    - `python -m signal2speech.ai`. "Other replies" asks for a new pair, and "Saved phrases" switches to offline backups like "Yes." / "No."
- The screen always says where the replies came from: Claude, Stub (practice replies when no API key is set), or Saved phrases
- If the AI is slow (over 9 seconds), offline, or fails, saved phrases appear with the reason. A late AI answer can never swap the choices while the wearer is picking
- Verified with the Stub and with a forced timeout. A real Claude reply is still unverified because there's no API key yet (`ANTHROPIC_API_KEY` in `.env`)

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
## 11/14/26 - 5:02 PM - Long Le (with Claude) - #25 Speech and the confirmed action ([PR #60](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/60))
- Speech moved to `signal2speech/speech/`. It plays a recorded clip for the two fixed OpenOrbit lines if one exists, otherwise uses the computer's built-in offline voice
- Fixed a bug where a recorded clip could have played instead of an AI reply. AI replies always speak the exact approved words
- `--input simulated` uses the g.Pype simulator from #21 when it's installed, and the screen says why when it falls back to the scripted version
- Verified on a Mac with scripted simulated input: one map action and one spoken line, nothing during the preview. This Mac can't run g.Pype (macOS 12), so the g.Pype path was checked with a test stand-in. Still needs the real map (#30) and recorded clips (#29)

## 11/14/26 - 5:15 PM - MagicJester2764 - #21 Code review fixes ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The full app now runs on the fake g.Pype brain: `python -m signal2speech.app --input simulated` (wired in by #60)
- A code review found that pressing Esc during a scripted run threw the script out of order. Now a cancelled step is retried, and a step the keyboard already did is skipped
- Picking with Ctrl+1/Ctrl+2 now waits until the tiles finish flashing, the same as the real P300 will
- The headless runner handles longer scripts, and a run that times out now reports failure instead of success
- Closing the simulator fully disconnects it, so a restarted app can't end up with two simulators
- Verified on simulated input: 82 tests pass, and the integrated app gave one preview, then one reveal and one spoken line

## 11/14/26 - 5:24 PM - MagicJester2764 - #37 CI follow-up ([PR #68](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/68))
- Took over the CI that Vasanth drafted in #64 and fixed what its code review found
- CI now installs the versions pinned in `requirements-lock.txt` (g.Pype, Qt, numpy, scikit-learn, and the rest), so it tests what the judging laptop runs instead of whatever is newest that day
- Each run's summary shows the test result, every skipped test and why, the smoke check report, and the list of checks a person still has to do by hand
- Merging two PRs back to back no longer cancels the first one's test run on `main`
- The Linux setup steps in the docs now match what CI actually installs, and the docs only claim the Python versions CI really tests
- Code review follow-up: the summary is now written even when tests or the smoke check fail, and an app that can't start fails CI instead of looking like a skipped smoke check. The check is renamed `ci (...)` because it runs more than pytest
