# Signal2Speech Devlog

Plain-language notes on what changed and why, one entry per finished issue. The newest entry goes at the bottom. Times are Eastern. The format is in [CLAUDE.md](CLAUDE.md#devlog-after-every-issue).

## 11/14/26 - 2:37 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - Project kickoff
- Created the repo and wrote the pitch: Signal2Speech lets someone who can't speak or type answer questions with an EEG headset
- Two features share the same controls: AI Answering suggests replies, and OpenOrbit shows NASA satellite images next to EPA air-quality data
- Picked the live demo question: which Michigan county's AQI rose more when wildfire smoke arrived on June 26–28, 2023 (Washtenaw 32→218, Wayne 58→226)
- Wrote down a first tech stack (g.tec Unicorn headset, the g.tec Unity starter, local NASA/EPA data)

## 11/14/26 - 3:12 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - Team docs and issue board
- Added `CLAUDE.md` and `docs/`, so every teammate's coding agent starts from the same instructions, living memory, and issue categories
- Merged the issue list into 16 big issues, one per area, each with small tasks and a prompt to paste into a coding agent
- Wrote the plain-language walkthrough of one answer: choose, preview, then confirm in a separate step, so nothing is ever said by accident

## 11/14/26 - 3:52 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #22 Selection contract and #1 architecture ([PR #44](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/44)) ([PR #45](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/45))
- Defined the one shape every input uses (keyboard, simulator, headset), plus the rules that make a stale, duplicate, or leftover choice do nothing
- Wrote those rules as a test file (`contracts/selection-scenarios.json`) that the code must pass
- Settled the first plan as Unity 2022.3 with the g.tec starter, the only Unity version the SDK supports
- Added a `.gitignore` that keeps raw EEG, recordings, and secrets out of git

## 11/14/26 - 4:13 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - Pivot to Python and g.Pype ([PR #49](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/49)) ([PR #50](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/50))
- Switched the whole project from Unity/C# to Python 3.12, g.Pype 4.2, and PySide6, to match what the g.tec judges look for: visible pipelines, OSCAR artifact removal, and evidence
- Ported the selection contract to Python. The same scenario file still passes
- Rewrote the docs and opened new issues for the P300 chooser (#46), alpha confirm (#47), and evidence view (#48)
- Unblocked the board so no track waits on environment setup or data

## 11/14/26 - 4:28 PM - Long Le (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #24 Selection screen ([PR #51](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/51))
- Built the wearer's screen: two big tiles, a "Say this?" preview with Confirm and Cancel, and a judge strip showing the input type, connection, and last result
- Keys 1 and 2 pick tiles and Esc cancels, so the team can rehearse without a headset: `python -m signal2speech.ui`
- Added the tile flasher the P300 needs, with a hook that fires on the exact frame a tile lights up
- The screen only displays things. It never speaks or changes the map itself

## 11/14/26 - 4:39 PM - Long Le (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #4 One app, one output ([PR #54](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/54))
- Wired everything into one app: `python -m signal2speech.app`. A confirm changes the map and speaks the line exactly once, and previews and cancels do nothing
- Added a visible transcript and a D key that fakes a headset drop for recovery rehearsals
- Speech works offline (a bundled clip if one exists, otherwise the computer's voice)
- Checked it with Wi-Fi off on a dev Mac. The map is a labelled stand-in until #30

## 11/14/26 - 4:41 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #19 Environment verified ([PR #52](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/52)) ([PR #55](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/55))
- Installed and pinned exact versions in `requirements-lock.txt`, so every laptop gets the same setup
- Confirmed g.Pype's scope window opens and shows a moving signal
- Noted that the install can fail partway on flaky Wi-Fi, and the flag that fixes it

## 11/14/26 - 4:46 PM - MagicJester2764 (with Claude) - #21 Simulated input ([PR #53](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/53))
- The app can be driven by a fake brain running through the real g.Pype pipeline, so the team can rehearse the whole flow without the headset
    - `python -m signal2speech.eeg.simulated --picks 2,1` chooses tile 2, then confirms. Every event is labelled "simulated"
    - `--ui` opens the selection window, where Ctrl+1 and Ctrl+2 decide for the "brain"
- A late decision from an old round is thrown away before it can land in the next round. Without this, a slow answer could have confirmed something the wearer never meant to confirm
- Added a drop-in replacement for the app's placeholder simulator. Swapping it in is one line for the #25 owner
- Found that tests must create the Qt app as `QApplication`. Otherwise the UI tests crash the whole test run. This is recorded in MEMORY.md
- Verified on a Linux laptop with simulated input only, not yet on the judging laptop

## 11/14/26 - 4:50 PM - Long Le (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #5 AI Answering ([PR #57](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/57))
- A typed question now becomes two short reply tiles. The wearer previews one, and confirming speaks it once
- Uses Claude when an API key is set, and otherwise a clearly labelled stub. Any failure (offline, timeout, bad key) falls back to saved phrases and says why
- "Other replies" and "Saved phrases" buttons, and a late AI answer can never replace the tiles on screen

## 11/14/26 - 4:51 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #48 Evidence view for judges ([PR #56](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/56))
- Added a g.Pype window that shows judges the brain signal: raw and filtered EEG, the spectrum, OSCAR on vs off, and the averaged response to target flashes
- The window always says whether the input is Simulated, Recorded, or Live EEG
- Runs can be recorded and replayed (recordings stay out of git): `python -m signal2speech.evidence --source generator`

## 11/14/26 - 4:56 PM - MagicJester2764 (with Claude) - #47 Alpha-switch confirm ([PR #58](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/58))
- The wearer can now confirm by closing their eyes for about 2 seconds. That raises the brain's alpha rhythm, and one closure sends exactly one Confirm
    - It only listens while a "Say this?" preview is on screen. The eyes have to be open for a moment first, so a blink or closure from the previous screen can't confirm by accident
- Calibration takes 10 seconds with eyes open and 10 seconds with eyes closed. It refuses if the two aren't clearly different
- On simulated brain data (normal and weak alpha), there were no false triggers in 60 seconds of eyes-open rest. Every closure gave exactly one confirm, about 1.2–1.5 seconds after the eyes closed
- The alpha switch can share the headset with the P300 chooser (#46), because the Unicorn can only be opened once
- Still to do at the headset slot: calibrate on a real wearer (#23). Live confirm stays switched off in the app until #23 says it's safe

## 11/14/26 - 4:57 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - Trimmed dependencies ([PR #59](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/59))
- Installs only the g.Pype parts we use, and adds scikit-learn, which the P300 classifier needs. Its tests had been silently skipping without it
- Dropped LSL and EDF, which nothing used. That also frees Windows from being stuck on Python 3.12
- Everyone needs to rerun `pip install -e ".[dev]"` after pulling

## 11/14/26 - 5:01 PM - MagicJester2764 (with Claude) - #41 Smoke command and diagnostics ([PR #61](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/61))
- Added one command that checks the demo without a headset, internet, or screen: `python -m signal2speech.app --smoke`
    - It runs a confirm and a cancel through the real app with fake output, checks that the spoken AQI numbers match the EPA data, and checks that g.Pype can stream
    - Pieces that aren't built yet (the NASA/EPA files from #29 and the map from #30) show as SKIP, so nothing looks finished when it isn't. `--smoke=judging` treats a SKIP as a failure for the final build
    - It lists the checks that need a person: headset, live calibration, audio, Wi-Fi off
- Every run writes a timing log to `logs/` (not committed) with the input mode and connection state. The log refuses raw EEG data on purpose
- Breaking the app on purpose so it spoke twice made the smoke check fail, which shows it catches real problems

## 11/14/26 - 5:02 PM - Long Le (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #25 Speech module ([PR #60](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/60))
- Moved speech into its own module: bundled clips for the fixed OpenOrbit lines, the computer's voice for everything else, and pyttsx3 as a last resort
- Fixed a bug where one audio clip would have played for every AI reply
- `--input simulated` now uses the g.Pype simulator from #21 when it's available, and says so when it isn't

## 11/14/26 - 5:08 PM - MagicJester2764 (with Claude) - Devlog ([PR #62](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/62))
- Started this devlog: one plain-language entry per finished issue, written in the same PR
- `CLAUDE.md` now tells every teammate's coding agent to add an entry the same way, so the log stays complete without anyone having to remember

## 11/14/26 - 5:13 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #46 P300 chooser ([PR #63](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/63))
- The headset can now pick a tile: it learns what the wearer's brain does when the tile they're looking at flashes, and averages over several flashes before deciding
- Calibrate first, then choose. Decisions reach the app the same way the keyboard's do
- Verified on synthetic brain data only. Live accuracy on the wearer is still to do at the headset slot

## 11/14/26 - 5:14 PM - Vasanth Anbukumar (filled in 11/14/26, 5:21 PM, by MagicJester2764 with Claude, from git history) - #37 Tests on every PR ([PR #64](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/pull/64))
- GitHub now runs the full test suite on Windows, macOS, and Linux for every pull request
- It already caught a Windows-only bug: Qt returns forward-slash paths there, so tests should compare `Path` objects, not strings
- Headset pairing, audio, the g.Pype window, and the Wi-Fi-off launch stay manual checks
