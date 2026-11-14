# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 4:28 PM - Long Le - #24 Keyboard preview screen ([PR #51](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/51))
- The wearer's screen exists: two big choice tiles, then a "Say this?" preview with Confirm and Cancel
    - `python -m signal2speech.ui`. Press 1 or 2 to pick, 1 to confirm, 2 or Esc to cancel
- A strip along the bottom shows judges the input type (Keyboard, Simulated, Recorded, Live EEG), the round, and the last result, so simulated input is never mistaken for the headset
- The tiles can flash, and each flash tells the P300 chooser (#46) which tile lit, at the moment it lit
- Holding a key down doesn't repeat. Otherwise a held 2 would pick a reply and then immediately cancel it
- Verified with the keyboard on a Mac (macOS 12), not yet on the judging laptop

## 11/14/26 - 4:39 PM - Long Le - #4 One complete choose, preview, and confirm flow ([PR #54](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/54))
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

## 11/14/26 - 4:50 PM - Long Le - #5 AI reply suggestions ([PR #57](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/57))
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

## 11/14/26 - 5:02 PM - Long Le - #25 Speech and the confirmed action ([PR #60](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/60))
- Speech moved to `signal2speech/speech/`. It plays a recorded clip for the two fixed OpenOrbit lines if one exists, otherwise uses the computer's built-in offline voice
- Fixed a bug where a recorded clip could have played instead of an AI reply. AI replies always speak the exact approved words
- `--input simulated` uses the g.Pype simulator from #21 when it's installed, and the screen says why when it falls back to the scripted version
- Verified on a Mac with scripted simulated input: one map action and one spoken line, nothing during the preview. This Mac can't run g.Pype (macOS 12), so the g.Pype path was checked with a test stand-in. Still needs the real map (#30) and recorded clips (#29)

## 11/14/26 - 5:15 PM - MagicJester2764 - #47 Code review fixes ([PR #58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58))
- A code review found a way to confirm too early. A closure that came too soon could still count after the eyes had been open for less than the required second. Now every early closure restarts the clock
- A closure still "in the pipes" from the previous screen can no longer sneak through when the Confirm screen appears
- Calibration now refuses broken readings (for example a flat or noisy electrode) instead of silently making a switch that never fires
- If the app turns down a live confirm, the switch keeps listening on that same screen, so #23 can enable live confirm without a restart
- Long demos no longer grow memory, and the switch works with headset streams other than 250 Hz
- Verified on simulated input: 84 tests pass, and a 10 s rest gave 0 false triggers and 1 confirm per closure

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

## 11/14/26 - 5:20 PM - Vasanth Anbukumar - #37 Git hooks: secret scan and pre-push tests ([PR #66](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/66))
- Every clone can now turn on two shared git hooks with one command, the same on Windows, macOS, and Linux: `git config core.hooksPath .githooks`
    - `pre-commit` blocks API keys and tokens (Anthropic, OpenAI, GitHub, AWS, Google, private keys), raw EEG files (`.edf`, `.bdf`, recordings folders), and `.env`
    - `pre-push` runs `pytest` (about 30 seconds) before anything leaves your laptop. Branch deletions skip it automatically. Skip once with `SKIP_TESTS=1 git push`
- Why: the secret scan used to exist only on one laptop, and the rule about keeping keys and raw EEG out of git had nothing enforcing it
- The hooks are plain `sh` with LF line endings forced in `.gitattributes`, so Git for Windows, macOS, and Linux all run them
- Verified: `tests/test_githooks.py` builds a throwaway repo and confirms a fake key and an `.edf` file get blocked while a clean commit and `.env.example` pass. CI runs it on all three OSes

## 11/14/26 - 5:24 PM - MagicJester2764 - #37 CI follow-up ([PR #68](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/68))
- Took over the CI that Vasanth drafted in #64 and fixed what its code review found
- CI now installs the versions pinned in `requirements-lock.txt` (g.Pype, Qt, numpy, scikit-learn, and the rest), so it tests what the judging laptop runs instead of whatever is newest that day
- Each run's summary shows the test result, every skipped test and why, the smoke check report, and the list of checks a person still has to do by hand
- Merging two PRs back to back no longer cancels the first one's test run on `main`
- The Linux setup steps in the docs now match what CI actually installs, and the docs only claim the Python versions CI really tests
- Code review follow-up: the summary is now written even when tests or the smoke check fail, and an app that can't start fails CI instead of looking like a skipped smoke check. The check is renamed `ci (...)` because it runs more than pytest

## 11/14/26 - 5:45 PM - MagicJester2764 - #38 Proved the PR check passes and fails ([PR #75](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/75))
- Pushed a test that fails on purpose. CI went red on all four systems and pointed straight at the failing test. Then I removed it to get green again
- That closes out #14: every PR now shows a clear pass or fail without needing the headset
- Explained in the workflow why Ubuntu runs twice: Python 3.12 is what the judging laptop uses, and 3.13 is an early warning for newer Python. It caught a real bug on its first day
- Recorded a flaky evidence test on macOS (#48) so nobody chases it as a real failure
