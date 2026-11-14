# Two-minute run of show (#34, rehearsed in #36)

**The judge's question:** "Which county's AQI rose more between June 26 and June 28, 2023?"
**The spoken answer:** "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."

Run everything from the frozen judging commit (#42) with Wi-Fi off. The judge strip at the bottom of the app always shows the input type. Say it out loud whenever it isn't **Live EEG**.

| Time | Who | What the judges see | Command or action | Fallback |
| --- | --- | --- | --- | --- |
| 0:00–0:15 | Presenter | The problem: someone who can't speak or type still needs to answer. Signal2Speech lets them pick, preview, and confirm the exact words before anything is spoken. | App open on the first question | — |
| 0:15–0:35 | EEG lead | **Evidence view:** signal quality, OSCAR cleanup off vs. on, and the averaged P300 response | `python -m signal2speech.evidence --source hybridblack` | `--source replay recordings/evidence_<timestamp>`. The window says **Recorded**, and the presenter says so too |
| 0:35–0:50 | Judge | Asks the question. Two tiles appear: **Show the satellite view** and **Compare counties** | `python -m signal2speech.app --input live` (after #23) | `--input simulated`, labelled **Simulated** on screen |
| 0:50–1:10 | Wearer | The tiles flash. The P300 chooser picks **Compare counties**, and the preview shows the exact words. **No sound, no map change yet** | Wearer looks at the right tile | Keys 1/2 (labelled Keyboard), or the step-through fallback: options shown one at a time, each confirmed with the alpha switch |
| 1:10–1:30 | Wearer | Eyes closed for about 2 s. The alpha switch confirms, the map shows June 26 vs. June 28 with the county AQI, and the line is spoken **once** | Eyes closed | Key 1 confirms (labelled Keyboard) |
| 1:30–1:45 | Presenter | **Safety:** cancel or a late signal does nothing. Point at the transcript, which shows one preview, one confirm, and one spoken line | Optional: preview, then key 2 to cancel | Show the transcript only |
| 1:45–2:00 | Presenter | Close: one Python process on g.Pype (Windows, macOS, Linux). The same controls answer typed questions with AI reply suggestions (#5) | — | — |

## Before the judges arrive

- [ ] Judging build launched from the frozen commit (#42), with `python -m signal2speech.app --smoke=judging` passing (#41)
- [ ] Wi-Fi off. Volume up. Headset paired and calibrated (#23, #47)
- [ ] The backup recording is on the laptop and labelled **Recorded**. Raw EEG stays out of git
- [ ] One full dry run timed under 2:00. Record the time in [submission-checklist.md](submission-checklist.md#rehearsal-log)

## Rules on stage

- Never present simulated, keyboard, or recorded input as live EEG. The judge strip and the evidence window show the label, and the presenter says it.
- If a step fails, switch to its fallback, say which one, and keep going. Don't retry live more than once on stage.
