# Submission checklist and status (#34)

Deadlines are Eastern time: **draft on Devpost and the event app by Saturday midnight**, **final on Devpost by Sunday noon**, and a separate **g.tec submission by Nov. 30** if we enter it.

## Submission fields

| Field | Value | Status |
| --- | --- | --- |
| Project name | Signal2Speech | Ready |
| Repo link | https://github.com/Order-of-the-Golden-Eagles/Signal2Speech | Public (checked 11/14, 7:45 PM) |
| Team (all four) | Vasanth Anbukumar (`vas2000-personal`), Long Le (`LongNguyenThanhLe`), Nate (`MagicJester2764`), In Young Song (`InYoung-Song`) | Names ready. Confirm Devpost invites |
| Main track | **Mind and Machine** (the g.tec track). Pick exactly one. | Ready (#105) |
| Sponsor and special prizes | Select every prize we actually qualify for; unselected prizes aren't entered. Don't select ones we don't use (Gemini, Solana, MongoDB, and so on). Ask Vasanth before adding Best Beginner or Computer Science. | Decide on Devpost |
| Schools | Ask each teammate. Don't guess. | Ask |
| Video link | YouTube or Vimeo, 3:00 or less (g.tec's rules cap it at 2:30). See [shot-list.md](shot-list.md). Leave it empty for the draft. | Not recorded (#34) |
| Thumbnail | `docs/demo-submission/media/app-compare-reveal.jpg` (JPG, PNG, or GIF up to 5 MB) | Ready |
| Tagline | Answer without speaking or typing: pick, preview, and confirm the exact words with a brain-computer interface. | Draft |
| Built with | `Python`, `g.Pype`, `g.tec Unicorn Hybrid Black`, `PySide6`, `Qt`, `Qt TextToSpeech`, `pyttsx3`, `scikit-learn`, `NumPy`, `SciPy`, `Claude`, `Anthropic API`, `NASA MODIS`, `NASA GIBS`, `EPA AirData`, `pytest`, `GitHub Actions`. Type each and pick it from the dropdown. NASA MODIS imagery is fetched through GIBS, matching the video credits. | Ready |
| AI disclosure | See below | Draft, needs team sign-off |

### AI disclosure (draft)

Paste one of these into "Generative AI in your hack", and select Claude under "AI tools used". **Check #116 first:** use the first version while #116 is open, and the second only once it's merged.

**While #116 is open** (what `main` does today: `claude-opus-5-5`, replies not grounded):

> We used Claude (Anthropic) as a coding assistant during the hackathon. In the app, AI Answering uses Claude (`claude-opus-5-5`, through the Anthropic API) to suggest two short reply options for a typed question. The wearer always previews and explicitly confirms the exact words before anything is spoken, and offline saved phrases are used when the AI is unavailable. The EEG decoding (P300 with an LDA classifier, and the alpha switch) is our own g.Pype signal-processing pipeline, not a generative model.

**Only after #116 merges:**

> We used Claude (Anthropic) as a coding assistant during the hackathon. In the app, AI Answering uses Claude (`claude-sonnet-5-5`, through the Anthropic API) to suggest two short reply options for a typed question, grounded in our verified NASA/EPA dataset so it can't invent numbers. The wearer always previews and explicitly confirms the exact words before anything is spoken, and offline saved phrases are used when the AI is unavailable. The EEG decoding (P300 with an LDA classifier, and the alpha switch) is our own g.Pype signal-processing pipeline, not a generative model.

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
   - The AI answer above. **Check #116 first:** if it's still open, use the first AI answer and leave the story's AI bullet as written. If it has merged, use the second answer and add the grounding sentence from the note under the story.
6. **Submit.** Review the team, links, and prizes. Tick the terms box, click **Submit project**, and check that the confirmation appears. Then add the project to the **event app**.
7. **Log it** in the status log below: when, who, and the result.

### Paste-ready story

Fact-checked against `main` at `758f830` (see the table after the story).

**Inspiration**
People who can't speak or type still have things to say. Most assistive tools either take a long time to spell a sentence or put words in the user's mouth. We wanted a brain-computer interface where the person stays in control: the app suggests, and the wearer decides exactly what gets said.

**What it does**
A conversation partner asks a question. Signal2Speech offers two answers. The wearer picks one by looking at a flashing tile (the P300 brain response), sees exactly what will be said, and confirms by closing their eyes for two seconds (the alpha rhythm). Nothing is spoken or shown until they confirm, and then it happens exactly once. The same controls drive OpenOrbit, a view of NASA satellite imagery and EPA air-quality data. In our demo, the wearer answers "Which county's AQI rose more when wildfire smoke reached southeast Michigan?" and the app shows the map and says "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."

**The problem it solves**
Communication without speech or movement, with consent built in. Every answer is previewed and explicitly confirmed, so a stray, late, or repeated brain signal can never speak for the wearer.

**How we built it**
- **Signal processing:** g.tec's g.Pype (Python) for the Unicorn Hybrid Black. It provides OSCAR artifact removal, filtering, flash-locked epochs, and an LDA classifier for the P300. A separate alpha-band threshold, from eyes closed for two seconds, is the confirm switch. It's a different brain signal from the choice, and a confirm only counts in its own, separate step after the preview. Both run on one headset connection.
- **One selection contract:** keyboard, simulated signals, recorded sessions, and live EEG all feed the same small state machine (choose → preview → confirm), which rejects stale, duplicate, and late inputs.
- **App:** one offline Python process with a PySide6 interface, offline speech, and bundled NASA and EPA data.
- **Evidence view:** live scopes, the frequency spectrum, and the averaged target vs. non-target brain response, so judges can see the signal and not just the result.
- **AI Answering:** Claude suggests two short replies. The wearer still previews and confirms.
- **Engineering:** over 280 automated tests, CI on Windows, macOS, and Linux for every change, and git hooks that block secrets and raw EEG.

**Challenges we ran into**
- We switched from Unity/C# to Python and g.Pype mid-hackathon to get a visible, cross-platform signal pipeline.
- Our headset was lost in transit, so the judged demo runs on simulated brain signals through the real pipeline. Every screen labels its input (Keyboard, Simulated, Recorded, Live EEG). The live path is built: `python -m signal2speech.app --input live` calibrates and runs the demo on a Unicorn.
- Flash timing: the P300 needs the marker to line up with the real on-screen flash within milliseconds. We built a tool to measure it, and measured 0.03 ms of jitter on the judging laptop.
- Four people were merging fast, so we used CI on every pull request, auto-merge, and a shared contract so the tracks didn't collide.

**Accomplishments that we're proud of**
- A complete choose → preview → confirm flow where a confirmed answer produces exactly one spoken line and one map action.
- A guided calibration session with on-screen and spoken cues, so one person can run it alone.
- Honest labelling: nothing simulated is ever presented as live.

**What we learned**
How P300 and alpha signals work in practice, why stimulus timing matters, how to build real-time pipelines in g.Pype, and that a small shared contract with tests lets a team work in parallel without breaking each other.

**What's next**
Verify on a real wearer with the Unicorn, add more than two choices per round, stream decisions to other apps over UDP or LSL so any g.tec device can drive any app, and test with people who use assistive communication.

**Note, not part of the paste:** if #116 has merged when you submit, add this sentence to the AI Answering bullet above: "The replies are grounded in our verified dataset, so it can't state a fact that isn't in the data."

### Fact check (against `main` at `758f830`)

| Claim | Status | Source |
| --- | --- | --- |
| Live path built | ✅ On main | #124 (`--input live`, #103). **Not run on a wearer.** The text never claims it was. |
| 0.03 ms flash jitter on the judging laptop | ✅ Measured with `--tiles gl` on Vasanth's laptop, which he confirmed is the judging laptop | #101 |
| Over 280 tests; CI on Windows, macOS, and Linux | ✅ 283 collected. Every PR and every push to `main` runs on Windows, Ubuntu, and macOS. PRs run the full suite on Windows and Ubuntu (py3.12), and the fast suite on macOS and Ubuntu (py3.13). `main` runs the full suite everywhere. | `.github/workflows/tests.yml` |
| Alpha confirm is a different signal from the P300 choice | ✅ The story doesn't claim one can't affect the other, only that a confirm counts only in its own separate step | `SelectionHandler` rounds |
| "Required CI" | ❌ Not used. `main` has no branch protection, so the story says "CI on every pull request". Auto-merge is enabled. | repo settings |
| Grounded replies, Sonnet 5.5 | ⏳ Only after #116 merges. Until then, use the conditional wording above. | #116 |
| Spoken calibration cues | ✅ In the guided live run | `signal2speech/eeg/live.py` (#78) |
| Headset lost in transit | Team statement (Vasanth). Not something the repo can check. | #105 plan |

## Before the final

- [ ] Judging commit frozen and tagged (#42). Put the hash here: `________`
- [ ] Security review of that commit and the video passed (#33): no keys, personal data, raw EEG, or trained models
- [ ] `python -m signal2speech.app --smoke=judging` passes on the judging laptop with Wi-Fi off (#41)
- [ ] Video reviewed: every non-live EEG shot labelled, under 3:00, real AQI numbers only
- [ ] The repo README run command matches the judging build
- [ ] Video link added to Devpost (#34)
- [ ] All four teammates show on the project (In Young accepts in the morning)
- [ ] The story still matches `main` at the frozen commit. Re-run the fact check above: #116 status, test count, and any live EEG result
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
