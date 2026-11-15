# Demo and Submission

Own the two-minute walkthrough, live recording, and submission checklist.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13) · [#36](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/36) · [#34](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/34)

## Demo kit (#13, #34, #36)

| Doc | Use it for |
| --- | --- |
| [Stage script](stage-script.md) | **The** two-minute table demo, second by second: roles, the live and keyboard tracks, exact label lines, and a fallback for every beat |
| [Shot list](shot-list.md) | Points to **the** submission video plan in [#160](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/160) (screen recording, 2:30 or less). Keeps the original wearer-on-camera cut, the Recorded backup using g.Pype replay, and an AI Answering alternate shot |
| [Rehearsal](rehearsal.md) | Launch commands, timing targets, the test matrix (both options, cancel, duplicate, late, disconnect), and the failure-recovery script |
| [Judge Q&A](judge-qa.md) | Short answers mapped to g.tec's must-have and bonus criteria |
| [Pre-flight](preflight.md) | What to do before and during the 8:15 PM headset slot |
| [Submission checklist](submission-checklist.md) | The one home for Devpost fields, the AI disclosure, final checks, the draft and final status, and the rehearsal log |

**Honest status (2026-11-15):** keyboard and simulated runs work end to end, including the OpenOrbit map (#30). Live EEG runs in the app (`--input live`, #103): the P300 chooser picks and key 1 confirms. Eye-closure confirm inside the app stays off until #23. The alpha confirm (#47) also runs standalone (`python -m signal2speech.eeg.alpha_confirm --source hybrid-black`). A real-wearer P300 average needs the P300 chooser's tiles to drive the evidence view's markers (the #46 ↔ #48 seam). Nothing here has been run with a real headset yet.

**Still open:** recording the video waits on live input (#23). The team still has to confirm the exact track names on the event page and sign off on the AI disclosure.
- [Q&A bank](qa-bank.md): suggested spoken answers to judges' questions, and questions to type into the app
