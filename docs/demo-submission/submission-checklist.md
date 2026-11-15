# Submission checklist and status (#34)

Deadlines are Eastern time: **draft on Devpost and the event app by Saturday midnight**, **final on Devpost by Sunday noon**, and a separate **g.tec submission by Nov. 30** if we enter it.

## Submission fields

| Field | Value | Status |
| --- | --- | --- |
| Project name | Signal2Speech | Ready |
| Repo link | https://github.com/Order-of-the-Golden-Eagles/Signal2Speech (must be public before the final) | Check visibility before the final |
| Team (all four) | Vasanth Anbukumar (`vas2000-personal`), Long Le (`LongNguyenThanhLe`), `MagicJester2764` (name to confirm), `InYoung-Song` (name to confirm) | Confirm names and Devpost invites |
| Tracks | To confirm from the event page (g.tec / BCI track, plus any general track) | **Open** |
| Video link | Under 3:00, see [video-shot-list.md](video-shot-list.md) | Not recorded |
| Tagline | Answer without speaking or typing: pick, preview, and confirm the exact words with a brain-computer interface. | Draft |
| Built with | Python, g.Pype, g.tec Unicorn Hybrid Black, PySide6, scikit-learn, Qt TextToSpeech, NASA MODIS imagery, EPA AQI data, Claude | Draft |
| AI disclosure | See below | Draft, needs team sign-off |

### AI disclosure (draft)

> We used Claude (Anthropic) as a coding assistant during the hackathon; the devlog marks each change made "with Claude". In the app, AI Answering can suggest reply options using Claude (`claude-opus-5-5`) when an API key is configured. The wearer always previews and explicitly confirms the exact words before anything is spoken, and offline saved phrases are used when the AI is unavailable. The EEG decoding (P300 with LDA, the alpha switch) is our own g.Pype pipeline, not an AI model.

## Before the final

- [ ] Judging commit frozen and tagged (#42). Put the hash here: `________`
- [ ] Security review of that commit and the video passed (#33): no keys, personal data, raw EEG, or trained models
- [ ] `python -m signal2speech.app --smoke=judging` passes on the judging laptop with Wi-Fi off (#41)
- [ ] Video reviewed: every non-live EEG shot labelled, under 3:00, real AQI numbers only
- [ ] The repo README run command matches the judging build

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

Record each timed run of the [run of show](run-of-show.md). Keep live EEG results separate from simulated or keyboard runs (#36, #13).

| When (ET) | Input | Choice | Result (preview / confirm / cancel / late or duplicate input) | Time | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
