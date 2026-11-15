# Submission checklist and status (#34)

Deadlines are Eastern time: **draft on Devpost and the event app by Saturday midnight**, **final on Devpost by Sunday noon**, and a separate **g.tec submission by Nov. 30** if we enter it.

## Submission fields

| Field | Value | Status |
| --- | --- | --- |
| Project name | Signal2Speech | Ready |
| Repo link | https://github.com/Order-of-the-Golden-Eagles/Signal2Speech | Public (checked 11/14, 7:45 PM) |
| Team (all four) | Vasanth Anbukumar (`vas2000-personal`), Long Le (`LongNguyenThanhLe`), Nate (`MagicJester2764`), In Young Song (`InYoung-Song`) | Names ready. Confirm Devpost invites |
| Main track | **Mind and Machine** (the g.tec track). Pick exactly one. | Ready (#105) |
| Sponsor and special prizes | Select every prize we actually qualify for; unselected prizes aren't entered. **Include Beyond the Horizon** (space and Earth data, NASA-backed): the [science note](../openorbit-data/science-note.md) (#153) is our evidence. Don't select ones we don't use (Gemini, Solana, MongoDB, and so on). Ask Vasanth before adding Best Beginner or Computer Science. | Decide on Devpost |
| Schools | Ask each teammate. Don't guess. | Ask |
| Video link | YouTube or Vimeo, 2:30 or less: a screen recording with simulated input, no headset. Vasanth records it from [#160](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/160). Leave it empty for the draft. | Assigned (#160) |
| Thumbnail | `docs/demo-submission/media/app-compare-reveal.jpg` (JPG, PNG, or GIF up to 5 MB) | Ready |
| Tagline | Answer without speaking or typing: pick, preview, and confirm the exact words with a brain-computer interface. | Draft |
| Built with | `Python`, `g.Pype`, `g.tec Unicorn Hybrid Black`, `PySide6`, `Qt`, `Qt TextToSpeech`, `pyttsx3`, `scikit-learn`, `NumPy`, `SciPy`, `Claude`, `Anthropic API`, `NASA MODIS`, `NASA GIBS`, `EPA AirData`, `pytest`, `GitHub Actions`. Type each and pick it from the dropdown. NASA MODIS imagery is fetched through GIBS, matching the video credits. | Ready |
| AI disclosure | See below | Draft, needs team sign-off |

### AI disclosure (draft)

Paste this into "Generative AI in your hack", and select Claude under "AI tools used". It matches `main` since #116 merged on 11/14 (Sonnet 5.5, grounded prompt):

> We used Claude (Anthropic) as a coding assistant during the hackathon. In the app, AI Answering uses Claude (`claude-sonnet-5-5`, through the Anthropic API) to suggest two short reply options for a typed question. Its prompt carries only our verified NASA/EPA facts and tells it not to state any others. When it picks a map answer, the app speaks our own fixed line instead of the model's words, and any AQI numbers in that line come from the dataset. The wearer always previews and explicitly confirms the exact words before anything is spoken, and offline saved phrases are used when the AI is unavailable. The EEG decoding (P300 with an LDA classifier, and the alpha switch) is our own g.Pype signal-processing pipeline, not a generative model.

Why this wording: an ordinary reply is the model's own text, so the prompt keeps it to the facts but can't guarantee it. Only map answers speak fixed text: the county comparison is built from the dataset, and the satellite line comes from `contracts/demo-round.json` (`signal2speech/ai/replies.py`). Earlier drafts said it "can't invent numbers". Don't use that.

<details><summary>Superseded: the version from before #116 (Opus, not grounded)</summary>

> We used Claude (Anthropic) as a coding assistant during the hackathon. In the app, AI Answering uses Claude (`claude-opus-5-5`, through the Anthropic API) to suggest two short reply options for a typed question. The wearer always previews and explicitly confirms the exact words before anything is spoken, and offline saved phrases are used when the AI is unavailable. The EEG decoding (P300 with an LDA classifier, and the alpha switch) is our own g.Pype signal-processing pipeline, not a generative model.

</details>

## Devpost draft tonight (#105)

**Due:** Saturday 12:00 AM ET on Devpost (hack-the-nest.devpost.com) **and** in the event app. The final locks Sunday 12:00 PM ET, with no late entries. Edits are allowed until then, so submit a complete draft first and polish after. The steps follow the organizers' "How to submit on Devpost" guide.

1. **Join.** Every teammate signs in to Devpost, opens hack-the-nest.devpost.com, clicks **Join hackathon**, and accepts the rules.
2. **Start the project.** Only MagicJester2764 clicks **Start project**. There's one project per team.
3. **Add the team.** Invite Vasanth, Long, and In Young. Each accepts from their own account. In Young is offline until about 8–9 AM: send the invite tonight and confirm in the morning.
4. **Fill in the project:**
   - name, tagline, and thumbnail from the table above
   - the story below
   - Built with
   - the repo link, never any keys or partner codes
   - the video: empty for the draft
5. **Additional info:**
   - Main track: Mind and Machine.
   - Prizes: only the ones we qualify for.
   - Schools.
   - AI tools: Claude.
   - The AI answer above. The story's AI bullet already matches it.
6. **Submit.** Review the team, links, and prizes. Tick the terms box, click **Submit project**, and check that the confirmation appears. Then add the project to the **event app**.
7. **Log it** in the status log below: when, who, and the result.

### Paste-ready story

Fact-checked against `main` at `da6e00d` (see the table after the story). **Updated 11/15, 7:45 AM:** recorded g.tec EEG now drives the app (#104), the accuracy figures are measured (#151), the voice is new (#206), and the test count is over 500. The rows added at the end of the table cover those. Paste this version into Devpost for the final.

**Inspiration**
People who can't speak or type still have things to say. Most assistive tools either take a long time to spell a sentence or put words in the user's mouth. We wanted a brain-computer interface where the person stays in control: the app suggests, and the wearer decides exactly what gets said.

**What it does**
A conversation partner asks a question. Signal2Speech offers two answers. The wearer picks one by looking at a flashing tile (the P300 brain response), sees exactly what will be said, and confirms by closing their eyes for two seconds (the alpha rhythm). Nothing is spoken or shown until they confirm, and then it happens exactly once. The same controls drive OpenOrbit, a view of NASA satellite imagery and EPA air-quality data. In our demo, the wearer answers "Which county's AQI rose more when wildfire smoke reached southeast Michigan?" and the app shows the map and says "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."

**The problem it solves**
Communication without speech or movement, with consent built in. Every answer is previewed and explicitly confirmed, so a stray, late, or repeated brain signal can never speak for the wearer.

**How we built it**
- **Signal processing:** g.tec's g.Pype (Python) for the Unicorn Hybrid Black. It provides OSCAR artifact removal, filtering, flash-locked epochs, and an LDA classifier for the P300. A separate alpha-band threshold, from eyes closed for two seconds, is the confirm switch. It's a different brain signal from the choice, and a confirm only counts in its own, separate step after the preview. Both run on one headset connection.
- **Real brain data without a headset:** g.tec's own P300 Speller recordings, made on a g.tec amplifier, drive the app's choice. Each tile flash is answered with one real recorded brain response, and the same pipeline and classifier a live headset would use calibrate on them and pick the tile. On those recordings our classifier picks the right tile out of two 94 % of the time from a single flash and 100 % from five, tested on stretches of data it never trained on.
- **One selection contract:** keyboard, simulated signals, recorded EEG, and live EEG all feed the same small state machine (choose → preview → confirm), which rejects stale, duplicate, and late inputs.
- **App:** one Python process with a PySide6 interface, a natural-sounding voice that runs on the laptop, and bundled NASA and EPA data. Reply suggestions come from Claude over the internet, with saved phrases as the fallback when there is no connection.
- **Evidence view:** live scopes, the frequency spectrum, and the averaged target vs. non-target brain response, so judges can see the signal and not just the result.
- **AI Answering:** Claude suggests two short replies from our verified facts. Map answers speak our own fixed lines, with numbers from the dataset, not the model's words. The wearer still previews and confirms.
- **Engineering:** over 500 automated tests, CI on Windows, macOS, and Linux for every code change, and git hooks that block secrets and raw EEG.

**Challenges we ran into**
- We switched from Unity/C# to Python and g.Pype mid-hackathon to get a visible, cross-platform signal pipeline.
- Our headset was lost in transit, so nobody wears one at the judged demo. We didn't want to show only a simulation, so the app's choice is made from real human EEG that g.tec recorded. Which tile counts as "looked at" is scripted, because the recorded person was using g.tec's speller and not our app, and the screen says Recorded. The eye-closure confirm at the table is simulated and labelled Simulated. Every screen labels its input (Keyboard, Simulated, Recorded, Live EEG). The live path is built: `python -m signal2speech.app --input live` calibrates and runs the demo on a Unicorn. It has never run on a headset, and we don't claim it has.
- Flash timing: the P300 needs the marker to line up with the real on-screen flash within milliseconds. We built a tool to measure it, and measured 0.03 ms of jitter on the judging laptop.
- Four people were merging fast, so we used CI on every pull request, auto-merge, and a shared contract so the tracks didn't collide.

**Accomplishments that we're proud of**
- A complete choose → preview → confirm flow where a confirmed answer produces exactly one spoken line and one map action.
- A guided calibration session with on-screen and spoken cues, so one person can run it alone.
- Real recorded human EEG choosing the tile through the live pipeline, with a classifier that can and sometimes does get it wrong.
- Honest labelling: nothing simulated or recorded is ever presented as live.

**What we learned**
How P300 and alpha signals work in practice, why stimulus timing matters, how to build real-time pipelines in g.Pype, and that a small shared contract with tests lets a team work in parallel without breaking each other.

**What's next**
Verify on a real wearer with the Unicorn, add more than two choices per round, stream decisions to other apps over UDP or LSL so any g.tec device can drive any app, and test with people who use assistive communication.

### Fact check (against `main` at `da6e00d`)

| Claim | Status | Source |
| --- | --- | --- |
| Live path built | ✅ On main. On live input, eye-closure confirm stays off and key 1 confirms until #23. The Challenges bullet says so. | #124 (`--input live`, #103). **Not run on a wearer.** The text never claims it was. |
| 0.03 ms flash jitter on the judging laptop | ✅ Measured with `--tiles gl` on Vasanth's laptop, which he confirmed is the judging laptop | #101 |
| Over 400 tests; CI on Windows, macOS, and Linux for every code change | ✅ 408 collected. Every PR and every push to `main` runs CI on Windows, Ubuntu, and macOS. PRs run the full suite on Windows and Ubuntu (py3.12), and the fast suite on macOS and Ubuntu (py3.13). `main` runs the full suite everywhere. A docs-only change skips the test steps (#184), so the story says "every code change". | `.github/workflows/tests.yml` |
| Alpha confirm is a different signal from the P300 choice | ✅ The story doesn't claim one can't affect the other, only that a confirm counts only in its own separate step | `SelectionHandler` rounds |
| "Required CI" | ✅ Now true: the `main` ruleset requires a pull request, linear history, and the four `ci` jobs (Windows, Ubuntu, macOS on py3.12, Ubuntu py3.13). The story says "CI on every pull request", which holds either way. | repo ruleset `main` |
| Grounded replies, Sonnet 5.5 | ✅ #116 merged 11/14. The prompt carries only the verified facts, and map answers speak fixed lines (the comparison from the dataset, the satellite line from the contract). An ordinary reply is still model text, so the story and the AI answer don't claim it can't invent numbers. | #116, `signal2speech/ai/replies.py` |
| Spoken calibration cues | ✅ In the guided live run | `signal2speech/eeg/live.py` (#78) |
| Recorded g.tec EEG drives the app's choice | ✅ `python -m signal2speech.app --input recorded`. Each flash is answered with one real recorded response; the live path's pipeline and classifier decide. Run on the judging laptop: 4 scripted exchanges, 4 right. | #104 (PR #214), `docs/integration/README.md` |
| "94 % from a single flash and 100 % from five" | ✅ Mean over g.tec's five subjects, two-way choice, cross-validated on separate blocks of time. Scrambled labels give 42–46 %. Offline, not our wearer: the story says "on those recordings". | #151 (PR #218), `python -m signal2speech.evidence.dataset <folder> --curve` |
| "Which tile is looked at is scripted" | ✅ Stated in the story, on the strip ("re-mapped to our tiles"), and in the stage script | `RecordedEegInput.strip_text` |
| Natural-sounding offline voice | ✅ Piper, on the judging laptop. Machines without it fall back to the operating system's voice. Non-commercial voice licence, noted in the docs. | #206 (PR #207) |
| Over 500 automated tests | ✅ 503 passed and 1 skipped on the judging laptop at `f544beb` | local full run, 11/15 |
| No mention of the PiEEG board | ✅ Deliberate. It gave no usable EEG on two people, so it isn't in the story or the video. The findings are in the repo for anyone who asks. | `docs/eeg-hardware/README.md` |
| Headset lost in transit | Team statement (Vasanth). Not something the repo can check. | #105 plan |

## Before the final

- [ ] Judging commit frozen and tagged (#42). Put the hash here: `________`
- [ ] Security review of that commit and the video passed (#33): no keys, personal data, raw EEG, or trained models
- [ ] `python -m signal2speech.app --smoke=judging` passes on the judging laptop with Wi-Fi off (#41)
- [ ] Video reviewed: every non-live EEG shot labelled, 2:30 or less (g.tec's cap, #160), real AQI numbers only
- [ ] The repo README run command matches the judging build
- [ ] Video link added to Devpost (#34)
- [ ] All four teammates show on the project (In Young accepts in the morning)
- [ ] The story still matches `main` at the frozen commit. Re-run the fact check above: test count, CI rules, and any live EEG result
- [ ] Re-open **Additional info** and re-check the prizes and required answers (the organizers' guide says to revisit it after an early submit)
- [ ] Mind and Machine: hardware teams also submit to g.tec's GitHub by Nov 30 (#108)

## Status log

| When (ET) | Step | Who | Result |
| --- | --- | --- | --- |
| | Devpost draft submitted | | |
| | Event app draft submitted | | |
| | Video uploaded (link) | | |
| | Final submitted on Devpost | | |
| | Confirmation emails saved | | |
| | g.tec Nov. 30 submission: decide yes/no, then submit | | |

## Rehearsal log

Record each timed run of the [stage script](stage-script.md) (test matrix in [rehearsal.md](rehearsal.md)). Keep live EEG results separate from simulated or keyboard runs (#36, #13).

| When (ET) | Input | Choice | Result (preview / confirm / cancel / late or duplicate input) | Time | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
