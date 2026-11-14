# Demo and Submission

Own the two-minute walkthrough, live recording, and submission checklist.

**Active work** · [#13](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/13) · [#36](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/36) · [#34](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/34)

| Doc | Use it for |
| --- | --- |
| [Run of show](run-of-show.md) | The two-minute table demo, second by second, with roles. Has a live track and a keyboard track. |
| [Shot list](shot-list.md) | The submission video (under 3:00), the Recorded backup using g.Pype replay, and the Devpost fields |
| [Rehearsal](rehearsal.md) | Launch commands, timing targets, the test matrix (both options, cancel, duplicate, late, disconnect), and the failure-recovery script |
| [Judge Q&A](judge-qa.md) | Short answers mapped to g.tec's must-have and bonus criteria |
| [Pre-flight](preflight.md) | What to do before and during the 8:15 PM headset slot |

**Honest status (2026-11-14):** keyboard and simulated runs work. Live EEG in the app is blocked on #23. The alpha confirm (#47) is merged and runs standalone (`python -m signal2speech.eeg.alpha_confirm --source hybrid-black`), but live confirm inside the app still waits on #23. The OpenOrbit map (#30) is in an open PR. A real-wearer P300 average needs the P300 chooser's tiles to drive the evidence view's markers (the #46 ↔ #48 seam). Nothing here has been run with a real headset yet.
