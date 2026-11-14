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

## 11/14/26 - 5:45 PM - Vasanth Anbukumar (with Claude) - #23 Guided live-run harness ([PR #78](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/78))
- Added one command for the headset slot: `python -m signal2speech.eeg.live --source hybridblack`. It walks through the device check, signal quality, P300 calibration, confirm calibration, 10 live attempts, and a summary
- If the headset isn't paired, it says how to pair it and exits cleanly. If signal quality is bad, it names the bad channels and stops unless you choose to continue
- The summary says whether it's safe to arm live EEG confirm. It only says yes on a live run where the alpha switch did the confirming, with no late decisions crossing rounds and no false confirms. A dry run never says yes
- Every outcome, accuracy, and time per selection goes to `logs/` (not committed). The log refuses raw EEG on purpose
- A dry run with the alpha switch from #47 showed that the P300 and alpha inputs both start their event IDs at 1, so the second one was thrown away as a duplicate. The harness tags them apart, and the app will need the same fix
- Verified on simulated input only: `--source generator` now uses the merged alpha switch and ran start to finish in about 160 s (10/10 confirmed by simulated eye closures, 0 false triggers, 0 false confirms). Tests also inject a wrong decode to check the cancel, timeout, and false-confirm paths, and 194 tests pass. Nothing has run on the real headset yet

## 11/14/26 - 5:59 PM - Long Le (with Claude) - #4 Real map in the app, bigger reveal ([PR #81](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/81))
## 11/14/26 - 5:59 PM - Long Le - #4 Real map in the app, bigger reveal ([PR #81](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/81))
- The app now shows the real NASA/EPA map from #30 after a confirm. No code change was needed for that, and the stand-in panel is gone
    - `python -m signal2speech.app --input keyboard`. Press 2, then 1, to see the county comparison
- After a map reveal, the map takes most of the window and stays up for 8 seconds before the next question, so judges can read the AQI table. The input label stays visible the whole time
- Checked with the real map: preview and cancel leave it blank, a confirm changes it once, and a repeated confirm changes nothing. One spoken line per confirm
- Still to do for #4: the final run on the judging laptop with Wi-Fi off, and #26 (recovery checks)

## 11/14/26 - 5:58 PM - MagicJester2764 - #26 Recovery checks ([PR #80](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/80))
- Proved that nothing goes wrong when things go wrong: cancelling, a headset drop, repeated keys, and late or replayed brain decisions never cause an extra map change or spoken line
    - Covers keyboard, the g.Pype simulator, and replayed recordings: `pytest tests/test_recovery.py`
- Added the confirm timeout the rules always promised: if nobody confirms within 15 seconds, the preview cancels quietly (`--confirm-timeout`, 0 turns it off)
- Found and fixed a hidden test problem: a leftover 30-second timer from one test could end a later test early. It only showed up once the test suite got long enough
- Still open for the headset slot (#23): if the headset goes silent without disconnecting, nothing notices yet

## 11/14/26 - 5:45 PM - MagicJester2764 - #38 Proved the PR check passes and fails ([PR #75](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/75))
- Pushed a test that fails on purpose. CI went red on all four systems and pointed straight at the failing test. Then I removed it to get green again
- That closes out #14: every PR now shows a clear pass or fail without needing the headset
- Explained in the workflow why Ubuntu runs twice: Python 3.12 is what the judging laptop uses, and 3.13 is an early warning for newer Python. It caught a real bug on its first day
- Recorded a flaky evidence test on macOS (#48) so nobody chases it as a real failure

## 11/14/26 - 6:08 PM - MagicJester2764 - #38 Review follow-up ([PR #83](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/83))
- Filled in the green CI run that proves the check passes again, instead of "expected green"
- The flaky evidence test on macOS is now in living memory, with a firmer rule: re-run once, and if it fails twice it's a real problem
- The CI matrix explanation lives in one place (the workflow file) and no longer claims Python versions CI doesn't test

## 11/14/26 - 5:58 PM - In Young Song (with Claude) - #7 Wildfire comparison works offline ([PR #79](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/79))
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

## 11/14/26 - 6:06 PM - Vasanth Anbukumar - #22 Fix duplicate event IDs between headset decoders ([PR #82](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/82))
- The live flow (P300 picks, eyes-closed alpha switch confirms) can now actually confirm
- Why: the P300 chooser (#46) and the alpha switch (#47) each make their own live-EEG adapter. Both numbered events `e1`, `e2`…, so the app rejected the alpha confirm as a repeat of the P300 preview. I found this while reviewing #47 after it merged
- Event IDs now come from one counter shared by every adapter, so they're unique for the whole run
- Verified with a new test where two live-EEG adapters preview and then confirm (`tests/test_contract.py`). `tests/test_app.py` and `tests/test_recovery.py` no longer assume IDs like `k1`. Full suite: 176 passed
- Still needs the headset: the combined P300 + alpha flow on a real wearer (#23)

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
