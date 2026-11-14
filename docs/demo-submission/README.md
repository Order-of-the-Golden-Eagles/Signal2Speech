# Demo and Submission

Own the two-minute walkthrough, live recording, and submission checklist.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13) · [#36](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/36) · [#34](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/34)

## Submission kit (#34)

- [Run of show](run-of-show.md): the two-minute table demo, minute by minute, with a fallback for every step
- [Video shot list](video-shot-list.md): nine shots under 2:45, each with its input label, capture command, and what it waits on
- [Submission checklist](submission-checklist.md): the Devpost fields, a draft AI disclosure, final checks, the draft/final status log, and the rehearsal log

## Stage and rehearsal kit (#13, #36)

| Doc | Use it for |
| --- | --- |
| [Stage script](stage-script.md) | The same two-minute demo, second by second, with who says and does what. Has a live track and a keyboard track. |
| [Shot list](shot-list.md) | The submission video (under 3:00), the Recorded backup using g.Pype replay, and the Devpost fields |
| [Rehearsal](rehearsal.md) | Launch commands, timing targets, the test matrix (both options, cancel, duplicate, late, disconnect), and the failure-recovery script |
| [Judge Q&A](judge-qa.md) | Short answers mapped to g.tec's must-have and bonus criteria |
| [Pre-flight](preflight.md) | What to do before and during the 8:15 PM headset slot |

**Honest status (2026-11-14):** keyboard and simulated runs work. Live EEG in the app is blocked on #23. The alpha confirm (#47) is merged and runs standalone (`python -m signal2speech.eeg.alpha_confirm --source hybrid-black`), but live confirm inside the app still waits on #23. The OpenOrbit map (#30) is in an open PR. A real-wearer P300 average needs the P300 chooser's tiles to drive the evidence view's markers (the #46 ↔ #48 seam). Nothing here has been run with a real headset yet.

**Still open:**
- **Recording:** the video can't be recorded until live input (#23) and the real map (PR #65) land. The alpha confirm is on `main` (#47) but only runs standalone until #23.
- **Team decisions:** the tracks, two teammates' full names, and sign-off on the AI disclosure.
