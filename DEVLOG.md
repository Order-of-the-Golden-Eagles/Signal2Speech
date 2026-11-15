# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 2:37 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - Project kickoff
- Created the repo and wrote the pitch: Signal2Speech lets someone who can't speak or type answer questions with an EEG headset
- Two features share the same controls: AI Answering suggests replies, and OpenOrbit shows NASA satellite images next to EPA air-quality data
- Picked the live demo question: which Michigan county's AQI rose more when wildfire smoke arrived on June 26–28, 2023 (Washtenaw 32→218, Wayne 58→226)
- Wrote down a first tech stack (g.tec Unicorn headset, the g.tec Unity starter, local NASA/EPA data)

## 11/14/26 - 3:12 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - Team docs and issue board
- Added `CLAUDE.md` and `docs/`, so every teammate's coding agent starts from the same instructions, living memory, and issue categories
- Merged the issue list into 16 big issues, one per area, each with small tasks and a prompt to paste into a coding agent
- Wrote the plain-language walkthrough of one answer: choose, preview, then confirm in a separate step, so nothing is ever said by accident

## 11/14/26 - 3:52 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - #22 Selection contract and #1 architecture ([PR #44](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/44)) ([PR #45](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/45))
- Defined the one shape every input uses (keyboard, simulator, headset), plus the rules that make a stale, duplicate, or leftover choice do nothing
- Wrote those rules as a test file (`contracts/selection-scenarios.json`) that the code must pass
- Settled the first plan as Unity 2022.3 with the g.tec starter, the only Unity version the SDK supports
- Added a `.gitignore` that keeps raw EEG, recordings, and secrets out of git

## 11/14/26 - 4:13 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - Pivot to Python and g.Pype ([PR #49](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/49)) ([PR #50](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/50))
- Switched the whole project from Unity/C# to Python 3.12, g.Pype 4.2, and PySide6, to match what the g.tec judges look for: visible pipelines, OSCAR artifact removal, and evidence
- Ported the selection contract to Python. The same scenario file still passes
- Rewrote the docs and opened new issues for the P300 chooser (#46), alpha confirm (#47), and evidence view (#48)
- Unblocked the board so no track waits on environment setup or data

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

## 11/14/26 - 4:41 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - #19 Environment verified ([PR #52](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/52)) ([PR #55](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/55))
- Installed and pinned exact versions in `requirements-lock.txt`, so every laptop gets the same setup
- Confirmed g.Pype's scope window opens and shows a moving signal
- Noted that the install can fail partway on flaky Wi-Fi, and the flag that fixes it

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

## 11/14/26 - 4:51 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - #48 Evidence view for judges ([PR #56](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/56))
- Added a g.Pype window that shows judges the brain signal: raw and filtered EEG, the spectrum, OSCAR on vs off, and the averaged response to target flashes
- The window always says whether the input is Simulated, Recorded, or Live EEG
- Runs can be recorded and replayed (recordings stay out of git): `python -m signal2speech.evidence --source generator`

## 11/14/26 - 4:56 PM - MagicJester2764 - #47 Alpha-switch confirm ([PR #58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58))
- The wearer can now confirm by closing their eyes for about 2 seconds. That raises the brain's alpha rhythm, and one closure sends exactly one Confirm
    - It only listens while a "Say this?" preview is on screen. The eyes have to be open for a moment first, so a blink or closure from the previous screen can't confirm by accident
- Calibration takes 10 seconds with eyes open and 10 seconds with eyes closed. It refuses if the two aren't clearly different
- On simulated brain data (normal and weak alpha), there were no false triggers in 60 seconds of eyes-open rest. Every closure gave exactly one confirm, about 1.2–1.5 seconds after the eyes closed
- The alpha switch can share the headset with the P300 chooser (#46), because the Unicorn can only be opened once
- Still to do at the headset slot: calibrate on a real wearer (#23). Live confirm stays switched off in the app until #23 says it's safe

## 11/14/26 - 4:57 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - Trimmed dependencies ([PR #59](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/59))
- Installs only the g.Pype parts we use, and adds scikit-learn, which the P300 classifier needs. Its tests had been silently skipping without it
- Dropped LSL and EDF, which nothing used. That also frees Windows from being stuck on Python 3.12
- Everyone needs to rerun `pip install -e ".[dev]"` after pulling

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

## 11/14/26 - 5:08 PM - MagicJester2764 - Devlog ([PR #62](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/62))
- Started this devlog: one plain-language entry per finished issue, written in the same PR
- `CLAUDE.md` now tells every teammate's coding agent to add an entry the same way, so the log stays complete without anyone having to remember

## 11/14/26 - 5:13 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - #46 P300 chooser ([PR #63](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/63))
- The headset can now pick a tile: it learns what the wearer's brain does when the tile they're looking at flashes, and averages over several flashes before deciding
- Calibrate first, then choose. Decisions reach the app the same way the keyboard's do
- Verified on synthetic brain data only. Live accuracy on the wearer is still to do at the headset slot

## 11/14/26 - 5:14 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764, from git history) - #37 Tests on every PR ([PR #64](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/64))
- GitHub now runs the full test suite on Windows, macOS, and Linux for every pull request
- It already caught a Windows-only bug: Qt returns forward-slash paths there, so tests should compare `Path` objects, not strings
- Headset pairing, audio, the g.Pype window, and the Wi-Fi-off launch stay manual checks

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

## 11/14/26 - 5:15 PM - In Young Song - #29 NASA and EPA dataset ([PR #65](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/65))
- The OpenOrbit demo now has its real data, bundled in the repo so it works with Wi-Fi off
    - `data/openorbit/`: two NASA satellite images of southeast Michigan (June 26 and 28, 2023), the EPA air-quality rows, map marker places, and `SOURCES.md` with every link
- The EPA numbers were checked against EPA's own file: Washtenaw 32 to 218 (+186), Wayne 58 to 226 (+168). `python data/openorbit/build_dataset.py --verify-only` re-checks the files offline
- June 26 is mostly cloud on both NASA satellites, so the "before" picture shows little ground. The AQI numbers carry the before and after. The team can decide later whether to change it
- Verified on Windows with no headset. NASA's coastline map lines up with the image, and the markers sit where EMU and Detroit really are

## 11/14/26 - 5:15 PM - In Young Song - #30 Offline wildfire comparison view ([PR #65](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/65))
- After a confirm, the app now shows the real map instead of the "not built yet" placeholder
    - "Show the satellite view" shows June 28 with EMU and Detroit marked. "Compare counties" shows both days side by side with the AQI table and which county rose most versus which ended highest
- The numbers on screen come from the EPA file, and a test checks that they match the spoken line, so the screen and the voice can't disagree
- Sized to fit next to the selection tiles on a 1920x1080 laptop at 125% scaling. Before this, the window ran off the screen
- If the data folder is missing, the panel says so clearly instead of crashing the app
- Verified on Windows with keyboard input and every network call blocked: one map change and one spoken line per confirm. Still needs a real Wi-Fi-off run on the judging laptop (#39)

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

## 11/14/26 - 5:32 PM - Long Le - #34 Submission plan and checklist ([PR #73](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/73))
- The team has a plan for the demo and the submission in `docs/demo-submission/`
    - `run-of-show.md`: the two-minute table demo, with a fallback for every step
    - `video-shot-list.md`: nine shots under 2:45 for the video
    - `submission-checklist.md`: the Devpost fields, a draft AI disclosure, and logs for submission status and rehearsals
- Every shot and step says which input it uses, so simulated or recorded EEG is never passed off as live
- Not done yet: the video itself. It needs the live headset (#23), the alpha confirm (PR #58), and the real map (PR #65). The team still has to confirm the tracks, two teammates' names, and the AI disclosure

## 11/14/26 - 5:33 PM - Vasanth Anbukumar - #13 Run of show and submission prep ([PR #74](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/74))
- Added the demo playbook in `docs/demo-submission/`: a second-by-second two-minute run of show with four roles, a shot list for a video under three minutes, a rehearsal checklist, judge Q&A, and an 8:15 PM headset pre-flight
- Each beat has two tracks. The live track is the goal. The keyboard track is what `main` can do today, and the label you say out loud must match the one on screen
- Found that the evidence view can't show a real P300 average yet. On the headset its flash markers have no visible flash, so the backup recording is for OSCAR and the eyes-closed alpha peak, and the P300 average stays labelled Simulated until the P300 chooser drives those markers
- Checked the commands on Windows: keyboard and simulated runs work, and `--input live` refuses as expected. `pytest` passes 124 with 2 skipped after merging the latest `main`
- Review fixes: marked the alpha confirm (#47) as merged with its real command (`--source hybrid-black`, plus `--demo`), and noted that the app's 175 ms, 10-flash tile timing has not been checked with the classifier, which was tested at 250 ms and 5 flashes
- Merged with the #34 submission kit from PR #73: its `run-of-show.md` stays as the minute-by-minute plan, and this PR's second-by-second version with roles is now `stage-script.md`
- Nothing here has been run with a real headset yet

## 11/14/26 - 5:35 PM - Vasanth Anbukumar - #1 Sync the architecture docs with main ([PR #71](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/71))
- Added a "Current status" table to the selection contract: what is merged and checked on simulated or synthetic data, what is still in an open PR (#29/#30 OpenOrbit), and what still needs the live headset (P300 accuracy, the alpha-switch threshold, live Unicorn input)
- Fixed stale lines: the P300 pipeline now matches the code (Trigger per tile, LDA score, sequence vote), the folder table names the real files, and the tests section gives today's count (111 passed, 2 skipped after merging main, with a note that the number grows) and the 3-OS CI
- Matched the dependency graph to GitHub's "Blocked by" links: added #22 to #30 and #21 to #23, and marked closed issues
- `docs/MEMORY.md` no longer says simulated input still needs a one-line swap in `app.py`: it already uses the g.Pype stream
- Docs only. No code changed, and pytest still passes

## 11/14/26 - 5:38 PM - Vasanth Anbukumar - #48 Evidence view driven by the P300 chooser ([PR #76](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/76))
- New flag: `python -m signal2speech.evidence --source generator --p300` (or `--source hybridblack --p300`) builds the judge window around the real P300 chooser instead of the stand-in flasher
- The chooser's filter, scorers and calibration collectors now live in the same g.Pype pipeline as the scopes, and its flash markers go on the evidence view's marker
- The target vs non-target average uses the calibration flashes, from the very Trigger nodes whose epochs train the classifier, so judges see what the classifier learns from
- Two test tiles flash in the window header, and each decision (with the round's outcome from the SelectionHandler) shows next to them
- The old mode without `--p300` works as before
- Verified on simulated input only: new headless tests pass, and a 22 s offscreen run calibrated, trained, and made 2 of 2 correct simulated selections. Not tried with a headset

## 11/14/26 - 5:41 PM - Vasanth Anbukumar - #46 Flash timing check ([PR #77](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/77))
- Added a tool that checks whether the P300 flash markers line up with what the screen actually shows: `python -m signal2speech.eeg.flash_timing --seconds 30`
    - It flashes the same kind of tiles the chooser uses and compares each marker with the moment the frame reaches the display. Then it prints the average and worst gap, the jitter, and the refresh rate, plus PASS or WARN (WARN above 20 ms of jitter)
- Wrote a step-by-step check with a phone slow-motion camera or a cheap light sensor, so we can confirm the real screen timing on the judging laptop before 8:15. The tool compares those light times with its markers, so the two clocks don't need to match
- Tested the maths and the PASS/WARN rules without a screen (18 tests), and ran the tool briefly in headless mode to show it works. Headless numbers mean nothing, so the tool always says WARN there
- Not done yet: a run on the judging laptop's real display, and the camera or light-sensor check

## 11/14/26 - 5:45 PM - MagicJester2764 - #38 Proved the PR check passes and fails ([PR #75](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/75))
- Pushed a test that fails on purpose. CI went red on all four systems and pointed straight at the failing test. Then I removed it to get green again
- That closes out #14: every PR now shows a clear pass or fail without needing the headset
- Explained in the workflow why Ubuntu runs twice: Python 3.12 is what the judging laptop uses, and 3.13 is an early warning for newer Python. It caught a real bug on its first day
- Recorded a flaky evidence test on macOS (#48) so nobody chases it as a real failure

## 11/14/26 - 5:45 PM - Vasanth Anbukumar - #23 Guided live-run harness ([PR #78](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/78))
- Added one command for the headset slot: `python -m signal2speech.eeg.live --source hybridblack`. It walks through the device check, signal quality, P300 calibration, confirm calibration, 10 live attempts, and a summary
- If the headset isn't paired, it says how to pair it and exits cleanly. If signal quality is bad, it names the bad channels and stops unless you choose to continue
- The summary says whether it's safe to arm live EEG confirm. It only says yes on a live run where the alpha switch did the confirming, with no late decisions crossing rounds and no false confirms. A dry run never says yes
- Every outcome, accuracy, and time per selection goes to `logs/` (not committed). The log refuses raw EEG on purpose
- A dry run with the alpha switch from #47 showed that the P300 and alpha inputs both start their event IDs at 1, so the second one was thrown away as a duplicate. The harness tags them apart, and the app will need the same fix
- Verified on simulated input only: `--source generator` now uses the merged alpha switch and ran start to finish in about 160 s (10/10 confirmed by simulated eye closures, 0 false triggers, 0 false confirms). Tests also inject a wrong decode to check the cancel, timeout, and false-confirm paths, and 194 tests pass. Nothing has run on the real headset yet

## 11/14/26 - 5:58 PM - MagicJester2764 - #26 Recovery checks ([PR #80](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/80))
- Proved that nothing goes wrong when things go wrong: cancelling, a headset drop, repeated keys, and late or replayed brain decisions never cause an extra map change or spoken line
    - Covers keyboard, the g.Pype simulator, and replayed recordings: `pytest tests/test_recovery.py`
- Added the confirm timeout the rules always promised: if nobody confirms within 15 seconds, the preview cancels quietly (`--confirm-timeout`, 0 turns it off)
- Found and fixed a hidden test problem: a leftover 30-second timer from one test could end a later test early. It only showed up once the test suite got long enough
- Still open for the headset slot (#23): if the headset goes silent without disconnecting, nothing notices yet

## 11/14/26 - 5:58 PM - In Young Song - #7 Wildfire comparison works offline ([PR #79](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/79))
- A teammate can now run the whole OpenOrbit reveal with Wi-Fi off and explain it
    - `python -m signal2speech.app --input keyboard`: press 2 then 1 to compare counties, or 1 then 1 for the satellite view
- The compare view shows the two numbers judges confuse: Washtenaw had the biggest jump (+186), but Wayne ended highest (226)
- Verified with Wi-Fi actually disconnected on InYoung-Song's laptop, on `main` after PR #65: one map change and one full spoken line per confirm, and nothing on cancel. Keyboard input only, not live EEG

## 11/14/26 - 5:58 PM - In Young Song - #35 Secret, AI key, and network checks ([PR #79](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/79))
- Checked how the app handles keys and the network. Results are in `docs/security-privacy/README.md`
- No local bridge exists (the app is one process), so the bridge checks don't apply
- The AI key is read only from `.env` or the environment and never logged. Only the typed question goes to the AI, never EEG
- `python tools/release_check.py` re-runs the checks, including secrets in every branch's history (none found)

## 11/14/26 - 5:59 PM - Long Le - #4 Real map in the app, bigger reveal ([PR #81](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/81))
- The app now shows the real NASA/EPA map from #30 after a confirm. No code change was needed for that, and the stand-in panel is gone
    - `python -m signal2speech.app --input keyboard`. Press 2, then 1, to see the county comparison
- After a map reveal, the map takes most of the window and stays up for 8 seconds before the next question, so judges can read the AQI table. The input label stays visible the whole time
- Checked with the real map: preview and cancel leave it blank, a confirm changes it once, and a repeated confirm changes nothing. One spoken line per confirm
- Still to do for #4: the final run on the judging laptop with Wi-Fi off, and #26 (recovery checks)

## 11/14/26 - 6:06 PM - Vasanth Anbukumar - #22 Fix duplicate event IDs between headset decoders ([PR #82](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/82))
- The live flow (P300 picks, eyes-closed alpha switch confirms) can now actually confirm
- Why: the P300 chooser (#46) and the alpha switch (#47) each make their own live-EEG adapter. Both numbered events `e1`, `e2`…, so the app rejected the alpha confirm as a repeat of the P300 preview. I found this while reviewing #47 after it merged
- Event IDs now come from one counter shared by every adapter, so they're unique for the whole run
- Verified with a new test where two live-EEG adapters preview and then confirm (`tests/test_contract.py`). `tests/test_app.py` and `tests/test_recovery.py` no longer assume IDs like `k1`. Full suite: 176 passed
- Still needs the headset: the combined P300 + alpha flow on a real wearer (#23)

## 11/14/26 - 6:08 PM - MagicJester2764 - #38 Review follow-up ([PR #83](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/83))
- Filled in the green CI run that proves the check passes again, instead of "expected green"
- The flaky evidence test on macOS is now in living memory, with a firmer rule: re-run once, and if it fails twice it's a real problem
- The CI matrix explanation lives in one place (the workflow file) and no longer claims Python versions CI doesn't test

## 11/14/26 - 6:20 PM - Long Le - #33 First security pass ([PR #85](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/85))
- Did a first privacy and security check of the current code, ahead of making the repo and video public
    - `python tools/release_check.py --quick --all-branches`, plus manual checks for trained models, network use, and image metadata
- No keys, raw EEG, recordings, or trained models are in git on any branch. Nothing sends EEG over the network. The only outbound call is the optional AI request, which sends the typed question only
- One warning: two teammates' personal email addresses appear in commit history. They'll be public if the repo goes public. Results and fix steps are in `docs/security-privacy/README.md`
- Not final: the check has to be repeated on the frozen judging commit (#42) and the actual video and screenshots (#34). The checklist for that is in the same doc

## 11/14/26 - 6:45 PM - Long Le - #42 Rollback that works with Wi-Fi off ([PR #86](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/86))
- If the final build breaks at the table, the team can switch back to the draft build without Wi-Fi, even when the two builds need different packages
    - Make a ready-to-run fallback copy when freezing: `git worktree add ../Signal2Speech-fallback judging-draft`, then set up its own `.venv` while still online. Steps are in `docs/devops/judging-build.md`
- Why: the old switch-back step said to run `pip install` when the lock file changed, and that fails with Wi-Fi off
- Switch-back rehearsal on a Mac: 3 seconds from `main` to the known-good build `eecc31a` and one map reveal (keyboard input; the lock file was the same)
- Also updated the runbook for the smoke check (#41) and the 8-second map reveal (#81). Still needed: tag `judging-draft` and `judging-final` and rehearse the switch on the judging laptop

## 11/14/26 - 6:55 PM - In Young Song - #32 Verified June 2023 fire detections ([PR #89](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/89))
- The team has a small, checked sample of NASA fire detections for the demo dates, bundled for offline use
    - `data/openorbit/firms/`: about 10,000 VIIRS detections for June 26 and 28, 2023, from the Great Lakes to Quebec. `SOURCES.md` explains what a detection means
- Southeast Michigan itself had no wildfire detections on either day, only a few industrial hot spots. The fires were in Quebec and Ontario
- `python data/openorbit/firms/build_firms.py --verify-only` re-checks every date and coordinate offline

## 11/14/26 - 6:55 PM - In Young Song - #31 Where the smoke came from ([PR #89](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/89))
- "Show the satellite view" now also shows where the smoke came from: a NASA map with the Quebec and Ontario fires as dots and southeast Michigan circled
- It has its own heading, legend, and credit, so fire detections are never confused with smoke or air quality, and it never appears on the AQI comparison
- It's optional. Without the fire files, the view looks exactly as before. Tested with the files missing and with them broken
- Verified in the real app on Windows with keyboard input. No headset needed

## 11/14/26 - 6:55 PM - In Young Song - #8 NASA FIRMS fire view ([PR #89](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/89))
- The FIRMS stretch goal is done: a verified sample (#32) and an optional map (#31). The core OpenOrbit comparison and the spoken lines didn't change

## 11/14/26 - 6:56 PM - Long Le - #39 #4 #42 Judging laptop session script ([PR #88](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/88))
- Whoever sits at the judging laptop now has one ordered 40-minute checklist: `docs/devops/judging-laptop-session.md`
    - Wi-Fi on: install, release check, smoke check, and the fallback copy. Wi-Fi off: keyboard and simulated runs, the AI fallback, the evidence view, and a timed switch-back
- One sitting produces the evidence to close #39 and #4 and rehearses #42's rollback. Each step has a ready-to-paste result comment for the right issue
- Turned on GitHub's "delete branch after merge" setting, and cleaned up the merged branches
- Not run yet: it needs the judging laptop

## 11/14/26 - 7:01 PM - MagicJester2764 - #40 Pre-headset checkpoint ([PR #90](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/90))
- Wrote down where the demo stands before the headset arrives: `docs/sprint-operations/pre-headset-checkpoint.md`
- The reveal works with no headset: InYoung's Wi-Fi-off keyboard run on her laptop (a slightly older build), plus a fresh simulated run on today's build where the real NASA/EPA view appears and one line is sent to speech (muted, so not heard)
- Not yet checked: the simulated run with Wi-Fi off, and hearing the line on the judging laptop. That's my next job, since the judging laptop is mine
- The smoke check is now fully green (7 of 7), now that the map and data have landed
- The one thing left for a live demo: the headset isn't connected to the app yet. The P300 chooser and the eyes-closed confirm both work on their own, but nothing wires them into the app (#23)
- Each developer is asked to confirm their row in #40

## 11/14/26 - 7:12 PM - Long Le - #93 Judge-facing README ([PR #99](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/99))
- A judge opening the repo now sees what Signal2Speech does, a screenshot, and a three-command offline quickstart at the top of `README.md`
    - `pip install -r requirements-lock.txt`, then `python -m signal2speech.app --input keyboard`
- A status table says honestly what works with keyboard, simulated, recorded, and live EEG input. The live headset tools are built but haven't run on a real wearer yet
- Added team and data credits (NASA GIBS MODIS, EPA AirData) and a short AI-use note. The screenshot is 180 KB in `docs/demo-submission/media/`
- Checked: every relative link resolves, and `tools/release_check.py --quick` passes apart from the known commit-email warning (#33)

## 11/14/26 - 7:12 PM - Vasanth Anbukumar - #37 Faster PR checks, required CI, auto-merge ([PR #100](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/100))
- PR checks are faster: the six slow real-time tests (live-run, evidence, alpha, and P300 pipelines, about 150 seconds) run on Windows and Ubuntu py3.12 for every PR, and on every OS when code lands on `main`
    - Locally, `pytest -m "not slow"` runs the rest in about 40 seconds. Plain `pytest` still runs everything
- `main` now requires all four CI jobs to pass before a PR can merge, and GitHub auto-merge is on: run `gh pr merge <n> --auto --squash` and GitHub merges once the checks are green
- Why: the full suite had grown to about 3 minutes, and teammates merging during long CI runs kept forcing re-runs
- The slow tests are listed in one place, `tests/conftest.py`, so no test files changed. Windows, the judging laptop, still runs everything on every PR

## 11/14/26 - 7:25 PM - Long Le - #94 Fits the judging laptop screen, plus fullscreen and key help ([PR #111](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/111))
- The app now fits a 1080p laptop at 150% scaling (1280×720) without cutting anything off. Before, it needed 1400 px of width
    - `python -m signal2speech.app --fullscreen`. F11 toggles fullscreen, and F1 shows the keys for whoever runs the demo
- The input label in the bottom strip always shows in full, so simulated input can't look live on a small screen. Longer connection and outcome text clips instead, and the transcript keeps it
- Checked with screenshots at 1280×720, 1366×768, and 1536×864 (preview, reveal, and help overlay), and tests assert the size limit in every state. Not yet seen on the judging laptop itself

## 11/14/26 - 7:33 PM - MagicJester2764 - #26 Review fixes that missed the merge ([PR #115](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/115))
- My code-review fixes for #26 were pushed a few minutes after its PR merged, so they never reached main. This puts them back
- If a preview times out or is cancelled, the simulator repeats the whole choose-then-confirm step instead of getting out of order
- The app's timers stop when it closes, the screenshot timer can't fire into a later run, and `--confirm-timeout` refuses values that would quietly turn it off

## 11/14/26 - 7:35 PM - Long Le - #95 Long replies fit their tiles ([PR #112](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/112))
- Long AI replies now shrink to fit the tiles and the preview instead of getting cut off. The text never goes below 32 px, so it stays readable from the judge table
- The size is only recalculated when the label or the window size changes, never during a flash, so the P300 flash timing isn't affected
- Checked with screenshots at 1280×720 and 1536×864 using 12-word replies: they fit at 54–56 px. The demo labels stay at full size. Tests cover the 32 px floor, the flash, and the preview

## 11/14/26 - 7:44 PM - Long Le - #96 Confirm countdown on the preview ([PR #114](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/114))
- The "Say this?" screen now shows how long is left before an unanswered preview cancels itself: "No answer cancels in 15 s"
- It counts down from the same timer that does the cancelling (#26), so the number on screen always matches what happens
- It disappears on confirm, cancel, disconnect, or the next question, and never appears with `--confirm-timeout 0`. Tests cover each case, including a real 2.5 s countdown that ends in the cancel. Fits 1280×720

## 11/14/26 - 7:58 PM - Long Le - #98 Tests pass on machines without g.Pype ([PR #117](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/117))
- `pytest` is now green on machines that can't install g.Pype, such as macOS 12 and Intel Macs. The 8 tests that need g.Pype skip with a reason that says how to install it
- Why: those 8 always failed on such machines, so the shared push hook blocked every push, and people had to skip it with `SKIP_TESTS=1`
- Only the tests that really need g.Pype are skipped. The rest of `test_diagnostics.py` and `test_recovery.py` still runs everywhere, and CI still runs all of them on Windows, macOS, and Linux
- Checked on macOS 12 without g.Pype: 183 passed, 0 failed, and the push hook passes again

## 11/14/26 - 7:58 PM - Vasanth Anbukumar - #106 Grounded Claude replies and map actions ([PR #116](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/116))
- AI Answering now uses `claude-sonnet-5-5`, which answered in about 1.4–1.9 s, against 2–3 s for Opus. Low effort, the server-side fallback, the 8 s timeout, and saved phrases all stay the same
- Claude now gets a "Verified facts" block built from the OpenOrbit data: the four EPA AQI rows, the changes, where EMU and Detroit are, and the sources. It's told to state only those facts and to say "I don't know" otherwise
- Before, every model answered "Wayne" to "Which county's AQI rose more?". That was wrong: Washtenaw rose 186 points and Wayne rose 168. Claude now offers the Compare counties map action for it
- A reply can now be a map action (compare counties or show the satellite view). The spoken line for those comes from the dataset and the demo contract, never from Claude's words, so the numbers always match the map
- Checked with real calls: the AQI question, "Do you want water or juice?", and a question the data can't answer, which got an honest "I don't know". All 247 tests pass

## 11/14/26 - 8:01 PM - MagicJester2764 - #103 Live EEG inside the app ([PR #124](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/124))
- The headset can now drive the real demo app: `python -m signal2speech.app --input live`
    - It calibrates on the app's own tiles first (look at the named tile, then eyes open and eyes closed), then the brain's response picks a tile and closing your eyes confirms
- The P300 chooser and the eye-closure switch share one headset connection, because the Unicorn can only be opened once
- Eye-closure confirm stays off until the #23 live run says it's safe. Until then key 1 confirms, and the screen says so
- With no headset, it now stops within about 15 seconds with pairing steps, instead of freezing forever (the headset library waits indefinitely when no device is there)
- Rehearse the exact same path without the headset: `--input simulated --p300`. That run worked end to end (one preview, one eye-closure confirm, one spoken line). Nothing has been tried on a real wearer yet
- After two code reviews: a failed calibration switches that part off and the on-screen hints say so (keys still work); closing the window, a busy headset, a missing driver, or a crash all exit cleanly and release the headset; if the brain gives no answer, the tiles flash again, then hand over to the keys

## 11/14/26 - 8:07 PM - Long Le - #5 AI demo shows the map for map suggestions ([PR #118](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/118))
- When Claude suggests a map answer (from #106), the AI demo window now shows the map and speaks the line once, just like the main app
- Why: the AI demo had no map on purpose, because replies used to be spoken words only. With #106, picking "Compare counties (shows the map)" would have spoken the line but shown nothing, and logged a BUG line
- Checked with a test that confirms a map suggestion: the map changes once and the line is spoken once, with nothing during the preview. Not yet run with a real Claude key in the window

## 11/14/26 - 8:10 PM - Long Le - #92 One demo script and one shot list ([PR #119](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/119))
- The team now has one two-minute script (`stage-script.md`) and one video shot list (`shot-list.md`) in `docs/demo-submission/`. The duplicate `run-of-show.md` and `video-shot-list.md` are gone
- Folded in what only the old files had: a fallback for every beat of the table demo, a pre-judge checklist (frozen build, smoke check, Wi-Fi off, fallback folder), and an AI Answering alternate shot for the video
- Updated the script for what's on `main` now: the real map with its 8 s reveal, fullscreen, F1 key help, and the confirm countdown. Submission fields live only in `submission-checklist.md`
- Checked: every relative link in the folder resolves. Docs only

## 11/14/26 - 8:33 PM - MagicJester2764 - #10 Git hook tests no longer touch your real repo ([PR #126](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/126))
- Found a nasty bug: when the pre-push hook runs the tests, one of them (`tests/test_githooks.py`) was making commits and changing settings in the developer's *real* repository instead of its own scratch copy
    - It switched the repo to "bare" (so `git status` stopped working), replaced your name and email with "Hook Test", and left a fake `.env` staged
- Fixed by giving that test a clean environment, plus a new test that proves it can't reach an outer repo even when git's hook variables are set
- The hook itself now clears git's variables before running the tests, so no other test or tool can do the same thing
- Verified by pushing through the real pre-push hook: the tests passed, and the repo's settings, history, and staged files were unchanged afterwards. A new test also checks this on every run, in both ways a hook can set git's variables
- If you pushed with the hooks turned on, check your repo with the steps in `docs/MEMORY.md`

## 11/14/26 - 8:13 PM - Vasanth Anbukumar - #23 Plain-language prompts in the live-run guide ([PR #127](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/127))
- The guided headset test (`python -m signal2speech.eeg.live --source hybridblack`) now speaks to the wearer in plain words: "WEARER: look at the tile with the YELLOW border… count it silently", "If YES, close your eyes for about 2 seconds"
- Steps read as what's happening ("checking the signal", "learning how your brain reacts to the flashes", "learning your eyes-closed YES signal") instead of jargon
- Error messages say what to do next (adjust the headset, re-run with `--flashes 12`, or use `--confirm keyboard`)
- Only the wording changed; the steps, timing, and safety rules are the same. Checked with a dry run on simulated data; the wearer prompts appear only with the real headset

## 11/14/26 - 8:30 PM - In Young Song - #107 Code tour ([PR #123](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/123))
- Any teammate can now walk a judge through the code in five minutes: `docs/demo-submission/code-tour.md`
    - It goes flash to P300 decision, eye-closure confirm, why nothing is spoken twice, where the map and voice run, then CI and the git hooks, with one sentence to say at each stop
- Every pointer links to the exact line on `main` and was checked against the code
- It ends with honest answers to the three hardest judge questions: accuracy (simulated only so far, live not yet measured), proof the brain is responding, and stimulus timing

## 11/14/26 - 8:31 PM - Long Le - #97 Same voice on every laptop for the map lines ([PR #125](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/125))
- The two OpenOrbit answers now play from bundled recordings, so they sound the same on every laptop, with or without Wi-Fi
    - `data/openorbit/audio/compare_air_quality.wav` and `show_satellite.wav`, about 7 s each
- They're made with espeak-ng, an open-source voice whose output we can share freely. It sounds robotic but clear. `python data/openorbit/audio/make_audio.py` regenerates them
- A test fails if the contract wording or the dataset's comparison line changes without regenerating the audio, so the words heard always match the words on screen. AI replies still use the live OS voice
- Checked on a Mac: the app played the bundled clip (Qt status Ready, played to the end), and the phonemes say "A-Q-I" and "Washtenaw" correctly. Not yet heard through the judging laptop's speakers

## 11/14/26 - 8:44 PM - Vasanth Anbukumar - #23 On-screen and spoken cues for the wearer ([PR #127](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/127))
- The guided test now tells the wearer what to do on the tile window itself (a big yellow instruction line) and out loud with the laptop's offline voice: "Look at the yellow tile", "Close your eyes", "The app picked tile 2. If that's right, close your eyes"
    - So one person can wear the headset without watching the terminal, and eyes-closed steps work because the cues are spoken
- New `--show` flag: `python -m signal2speech.eeg.live --source generator --show` opens the same window and cues on simulated data, so judges can watch the flow without hardware. `--no-voice` keeps the banner but mutes speech
- Tiles now read "Tile 1" and "Tile 2" instead of internal IDs
- Only prompts and the window changed; the EEG decoding and safety rules are the same. Checked with a simulated run (2/2 correct, 0 false confirms) and the fast EEG tests (50 passed). Whether the voice is audible was checked by ear on the judging laptop

## 11/14/26 - 8:51 PM - Long Le - #5 Live AI replies verified in the app ([PR #137](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/137))
- A typed question now gets real Claude replies in the AI demo window in about 2 seconds, and the confirmed reply is spoken once
    - `python -m signal2speech.ai`, with `ANTHROPIC_API_KEY` in `.env`
- Found a demo risk: without #116's grounding, Claude answered the AQI question wrongly ("Wayne"), when Washtenaw rose more. Don't ask data questions in the AI demo until #116 merges
- Verified with keyboard input on a Mac, with a fresh question and the demo question. Not yet tried on the judging laptop

## 11/14/26 - 9:03 PM - Long Le - #129 Fuzz test for "speaks exactly once" ([PR #140](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/140))
- A new test throws millions of random event sequences at the selection logic and checks that it never speaks twice, never speaks without a fresh preview, and never lets an old decision act in a new round
    - `pytest tests/test_contract_fuzz.py` (3 s in CI). `FUZZ_SEQUENCES=50000` for a long run, and `FUZZ_SEED=<n>` reproduces any failure
- A long run of 3,000,000 operations found 0 violations. The judge Q&A now cites it
- To prove the test isn't toothless, it also breaks the handler three ways on purpose (double output, a cancel that keeps the preview, ignored round IDs), and it catches each one
- No product code changed. This is software evidence with keyboard and simulated input, not live-EEG accuracy

## 11/14/26 - 9:17 PM - Long Le - #130 #131 Response times and a session report ([PR #141](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/141))
- Every confirm now shows how fast the app responded: time to the map change and time until speech starts, in the transcript and the bottom strip
    - On a Mac: map 2–30 ms, speech about 15 ms with a bundled clip and about 50 ms with the computer voice
- When the app closes, it writes a short report to `logs/session-<time>.md`: commit, input, counts of previews, confirms, and cancels, the response times, and a timeline. It never contains EEG or keys. `--no-report` turns it off
- The report is ready to paste into the rehearsal log, so every practice run leaves evidence behind
- Found and fixed two bugs while testing: the map time got overwritten in the strip, and closing the app could raise an error from the sound player. Tests use a fake clock. Not yet measured on the judging laptop

## 11/14/26 - 9:33 PM - MagicJester2764 - #105 Devpost draft text, fact-checked ([PR #146](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/146))
- The whole Devpost entry is ready to paste: tonight's steps, the story sections, Built with, the track, and the AI answer
    - In `docs/demo-submission/submission-checklist.md`. A person still has to submit it on Devpost and in the event app before midnight
- Every claim was checked against the code. Two were fixed: we don't have "required" CI checks (just CI on every change), and the AI-reply wording depends on whether #116 is merged when we submit
- The text never says the headset was used on a real wearer, because it hasn't been yet
- Two AI answers are ready, one for each state of #116, so we never claim a feature that isn't merged when we submit

## 11/14/26 - 9:20 PM - In Young Song - #138 PiEEG's simulator drives the eye-closure confirm ([PR #144](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/144))
- PiEEG's own simulated EEG now runs through our g.Pype pipeline: a keyboard preview, then PiEEG's "eyes closed" alpha burst confirms it, and the map changes and the line is spoken once
    - `python python_quickstart.py --sim --lsl` (PiEEG's starter), then `python -m signal2speech.eeg.pieeg_lsl --demo`. Setup is in `docs/eeg-hardware/pieeg.md`
- Why: the Mind and Machine track is led by g.tec with PiEEG, and judging runs on simulation, so this shows PiEEG's tools and g.Pype working together. It's labelled Simulated (PiEEG) everywhere
- PiEEG's simulators have no P300, so the choice is made by keyboard here. The P300 chooser stays on `--input simulated --p300`
- Only the stream from this laptop is used, under a name unique to it, so another team's PiEEG simulator on the venue Wi-Fi can't drive our app
- Verified on Windows with PiEEG's real starter: 250.0 Hz, calibration ratio 26.2, one confirm and one spoken line. The new tests use a fake stream and skip without `pylsl`, which isn't in the team install yet (Vasanth's call, #19). Not tried on the judging laptop, and not in the evidence view yet

## 11/14/26 - 9:26 PM - Long Le - #133 Crash-safe launcher for the judging table ([PR #145](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/145))
- One command starts the demo fullscreen and brings it back by itself if it crashes: `python tools/demo_launcher.py --input keyboard`
    - Restarts after 1 s, then every 2 s, up to 5 times. Closing the window normally just ends it
- Every start and exit is logged to `logs/launcher-<time>.log`. If it gives up, it says to switch to the fallback build
- Checked with real processes: a clean quit stopped the launcher, and a crashing app was restarted after 1 s, then given up on with a clear message. Tests use a fake process. The judging-laptop session and the stage script now use it

## 11/14/26 - 9:43 PM - MagicJester2764 - #110 An AI assistant can read the brain pipeline ([PR #155](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/155))
- Claude (Desktop or Code) can now ask Signal2Speech about its live signal pipeline and get real numbers back: `python -m signal2speech.mcp`
    - It answers questions like "Is the wearer's P300 visible?" from the actual averaged brain response, and can open the evidence window
- Every answer says whether the data is Simulated or Live EEG, and only summaries are sent, never raw brain data
- On the simulator it picked up a clear P300 (about 4.8 µV at 276 ms) and got 3 of 3 choices right
- With the real headset it reports signal quality and the eye-closure signal. The P300 needs tiles on screen, so use the app or the evidence view for that
- Still to do: record the 30-second clip for the video (#34), and try it with a real wearer
- Code review follow-up: the evidence window closes when the assistant disconnects, a missing or busy headset fails cleanly instead of hanging, and the accuracy figure counts every sequence, including ones with no answer

## 11/14/26 - 9:36 PM - Long Le - #132 Video title card, closing card, and diagram ([PR #147](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/147))
- The submission video has its three graphics ready in `docs/demo-submission/media/`: a title card, a closing card with the repo link and AI-use note, and an architecture diagram for shot 9
- They're drawn by a script, so changing a name or a line is one command: `python docs/demo-submission/make_graphics.py`
- The diagram shows the real path: headset → g.Pype (OSCAR) → P300 to choose and alpha to confirm → selection contract → speech and map, with keyboard and simulator input going through the same contract
- Checked by eye at full size, and a test makes sure all three stay 1920×1080, under 500 KB, and linked from the shot list

## 11/14/26 - 9:36 PM - Vasanth Anbukumar - #142 Real recorded brain data in the evidence view ([PR #149](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/149))
- Judges can now see a real human P300 even though our headset was lost in transit: `python -m signal2speech.evidence --source dataset path/to/p300-speller/S4.mat`
    - It plays g.tec's own hackathon recording (five people, 8 channels at 250 Hz like the Unicorn, but with different electrode positions: P3 and P4 where the Unicorn has C3 and C4) through our filters and averaging. The red target line pulls away from the blue non-target line around 300–500 ms within a minute
    - The banner always says "RECORDED… recorded by g.tec, not our headset or wearer". It's never shown as live or as ours
- `python -m signal2speech.evidence.dataset path/to/p300-speller` prints the numbers: a 7–11 µV target vs non-target difference in all five people, and our chooser's method classifies single flashes at 0.59–0.85 balanced accuracy (chance is 0.50)
- The dataset stays out of git. The docs say where to download it; cite g.tec and don't redistribute it
- Verified: the window on the judging laptop with subject S4, and tests that build a small fake file in the same format and check the flashes line up to the sample. Still not a result for our wearer or our two-tile layout

## 11/14/26 - 9:47 PM - Long Le - #134 Saved phrases you can edit ([PR #148](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/148))
- The offline saved phrases now come from `data/phrases.json`, so a user or caregiver can change them without touching code. One pair per line, and each pair is what the two tiles say
- If the file is missing or has a mistake (a phrase too long, the same phrase twice, broken JSON), the app falls back to the built-in phrases and the transcript says exactly why
- The file ships with the same six pairs as before, so nothing changes until someone edits it. Tests cover a good file, every kind of bad file, and no file

## 11/14/26 - 9:57 PM - Long Le - #135 Colour-contrast check ([PR #154](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/154))
- Every text colour in the app is now checked automatically against the WCAG readability standard, including the tiles, the flash, the preview, the countdown, every input label, and the help overlay
- One colour failed: the purple "Recorded" input label was slightly too dark (4.4:1, needs 4.5). It's now a lighter purple (6.6:1). Nothing else changed visually
- All colours now live in one file, `signal2speech/ui/palette.py`, and the test fails if someone adds a raw colour code elsewhere, so new colours get checked too
- The ratios for every pair are listed in `docs/accessibility-ui/README.md`

## 11/14/26 - 10:54 PM - Long Le - #136 One entry point: python -m signal2speech ([PR #156](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/156))
- Judges and teammates no longer need to know module names: `python -m signal2speech` opens a small launcher with a button for each tool (keyboard demo, simulated demo, AI Answering, evidence view, smoke check)
    - Each button says which input it uses. A tool that can't run on this machine is grayed out with the reason
- Each tool runs as its own process, so one crashing can't take the launcher down. The smoke check runs inside it and shows PASS or FAIL
- `python -m signal2speech --help` lists the same tools, and `python -m signal2speech demo-keyboard` runs one directly. The README quickstart uses it now
- Checked on a Mac: the buttons start the right commands, and the evidence view is grayed out here because g.Pype isn't installed. The smoke check correctly shows FAIL for the same reason. It should pass on the judging laptop

## 11/14/26 - 11:08 PM - MagicJester2764 - #153 Science note for the Beyond the Horizon judges ([PR #159](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/159))
- Wrote down exactly what the NASA and EPA data is and what we do and don't claim, for judges who know the science: `docs/openorbit-data/science-note.md`
- Found a subtle point a scientist would catch: Washtenaw's "before" air quality (32) was set by ozone, not by smoke particles. The app now says which pollutant set each number, and the note explains why the comparison still holds
- The June 26 satellite image is mostly cloud, and the screen now says so, so nobody reads white cloud as clean air
- Checked against EPA and NASA documentation and news reports of the June 28 smoke alert. The judge Q&A has three science answers ready
- After review, corrected the fire distances from FIRMS data (most fires about 1,340 km away in Quebec, a few small ones closer, nearest 84 km), made Wayne the like-for-like PM2.5 comparison, and kept the June 26 caption inside the image on small screens. Verified with `pytest tests/test_openorbit.py` (keyboard and offscreen only)

## 11/14/26 - 11:03 PM - Long Le - #128 Judge Q&A cites the response times ([PR #157](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/157))
- The judge Q&A now answers "How fast does it respond?" with the measured times: map change in 2–30 ms and speech starting in about 15–50 ms after a confirm
- It's honest about where the time really goes: the P300 choice takes a flash sequence (about 2.5–3.5 s), and the alpha confirm lands about 1.2–1.5 s after the eyes close. Those EEG numbers come from simulated data until the headset run
- With the fuzz test answer already in the Q&A, every sub-issue of #128 is done and its "done when" is met

## 11/14/26 - 11:22 PM - MagicJester2764 - #160 Video recording plan ([PR #161](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/161))
- Worked out what to record for the demo video and handed it to Vasanth as #160: a screen recording only, no headset, 2:30 or less, which fits both the Devpost and g.tec limits
    - Exact commands, what each shot shows, the narration, and how to export. Every brain-signal shot is labelled Simulated or Keyboard
- The Devpost checklist now uses the grounded-Claude AI answer (#116 merged) and enters the Beyond the Horizon prize (#153)

## 11/14/26 - 11:14 PM - Long Le - #106 Real Claude replies re-checked after grounding ([PR #158](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/158))
- Re-tested the AI demo window on the current code (Claude Sonnet 5.5 with grounded replies): a fresh question got two good replies in about 2 seconds, and the confirmed one was spoken once
- The AQI question now answers correctly with the Compare counties map option, and confirming it shows the map and speaks the right numbers. The wrong "Wayne" answer from earlier is gone
- With the AI provider unreachable, saved phrases appear right away, labelled offline. A real Wi-Fi-off run is still part of the judging-laptop session

## 11/14/26 - 11:56 PM - Vasanth Anbukumar - #37 Docs-only changes skip the slow tests ([PR #184](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/184))
- A PR that only touches docs, the devlog, or images now finishes its checks in under a minute instead of about five: the four test jobs still report (so the PR can merge) but skip install, pytest, and smoke
- A new "quick checks" job runs on every PR in a few seconds with nothing installed: `python tools/quick_check.py`
    - It fails on leftover merge-conflict markers and on a devlog entry duplicated by a merge, the two things that have actually broken doc-only PRs today
- The pre-push hook does the same locally: quick checks always, and the full test suite only when the pushed commits change code, tests, data, or build files
- Anything under `signal2speech/`, `tests/`, `contracts/`, `data/` (except its `.md` notes), `tools/`, `.github/`, `.githooks/`, or the dependency files still runs everything. Pushes to `main` always run the full suite on every OS

## 11/15/26 - 12:11 AM - Vasanth Anbukumar - #150 The program detects the EEG device and picks the right channels ([PR #186](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/186))
- One eyes-closed check now works on different amplifiers without anyone setting channel numbers: `python -m signal2speech.eeg.lsl_source --input live --demo`
    - g.tec devices have a fixed electrode layout, so it uses the three back-of-head electrodes (PO7, Oz, PO8)
    - The PiEEG Octopus 16 is a coin-sized puck with 16 pins on one spot. The check drops pins that aren't touching and averages every pin that responds when the wearer closes their eyes
- Why: the confirm watched channels 6 to 8, which is right for the g.tec Unicorn and wrong for a 16-pin board. g.tec's g.Pype is still the whole pipeline; the PiEEG board is only an extra amplifier, read over LSL
- Live confirm switches on only after a clean check on that wearer: no false triggers at rest and exactly one confirm per eye closure
- Reviewers can reproduce our numbers on g.tec's own data with no hardware: `python -m signal2speech.evidence.dataset path/to/p300-speller` (new README section)
- The library run sheet is in `docs/eeg-hardware/README.md`: power bank only while worn, close PiEEG Cloud first (one Bluetooth connection at a time), puck on the back of the head
- First-run check: `python -m signal2speech.eeg.lsl_source --input live --check` detects the board, measures the sample rate, and reports each pin's contact in about 10 seconds, with no prompts
- Verified against PiEEG's own script (their simulator publishing the real stream): detected as the Octopus 16 at 250 samples per second. Also verified with a stream that really sends 244 per second, as some boards do, and on our simulated 16-pin stream, where it found the flat pin and the loose pin, used the other 14, and confirmed once per closure. Not yet tried on a real board or a real person
## 11/15/26 - 11:59 PM - Long Le - #174 One visual design and redesigned tiles ([PR #185](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/185))
- The app now has one visual design: `signal2speech/ui/theme.py` sets the colours, text sizes, spacing, and corners, and every screen we built uses it
- The two choice tiles are redesigned: an icon, a clear title, a one-line "what happens" line, and the key as a small badge in the corner instead of "[1]" in the title. They have distinct idle, flashing, selected (green check after a confirm), and waiting states
- The flash looks the same as before (plain white with black content), so the brain-signal stimulus doesn't change. The flash timing check still passes, and the new tiles repaint in about 3 ms
- All text still meets WCAG AA. A test fails if any screen uses a colour outside the theme. Before and after screenshots are in `docs/accessibility-ui/README.md`

## 11/15/26 - 12:32 AM - Long Le - #175 Preview screen with a confirm ring ([PR #189](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/189))
- The "Say this?" screen now shows what will happen ("This will be said aloud" or "This will show the map and say"), the exact words as a big quotation, and a ring that fills toward the confirm
- Nothing is spoken until the ring is full. On the keyboard, hold 1 for 2 seconds (a tap no longer confirms). With EEG, the ring follows the eye-closure signal and empties if the eyes open early. After confirming, a "✓ Spoken" state shows until the next question
- The alpha switch got a read-only progress signal for the ring, and its decision logic didn't change. Scripted simulated input fills the same ring
- Checked with tests for each ring state (filling, emptying on early release, completing exactly once) and in screenshots. The live eye-closure ring needs g.Pype, so it hasn't been seen on this Mac
## 11/15/26 - 12:34 AM - MagicJester2764 - #34 Submission checklist matches main again ([PR #188](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/188))
- The Devpost checklist now has one AI answer to paste, and the story's AI bullet already matches it
- The old wording said Claude "can't invent numbers". That's only true for map answers, which speak our own fixed lines. Ordinary replies are the model's own words, kept to the facts by the prompt, so the text now says exactly that
- Every video length check now says 2:30 or less, g.tec's cap (#160). The fact check was redone at `da6e00d`: 408 tests, and `main` now requires the four CI jobs before a merge
- Docs only. If the Devpost draft was already submitted with the old AI answer, replace it before the final
## 11/15/26 - 12:32 AM - MagicJester2764 - #103 README: live input status ([PR #187](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/187))
- The README status table now says the app already takes live headset input (`python -m signal2speech.app --input live`)
- It said live input was switched off, which stopped being true when #103's code merged. A judge reading it would undersell the demo
- Eye-closure confirm is still off on a real headset and key 1 confirms instead. That still needs one wearer run (#23, #103)
- Docs only. Nothing new was run
