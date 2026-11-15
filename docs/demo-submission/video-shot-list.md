# Submission video shot list (#34)

**Target:** 2:45 or shorter. The hard limit is 3:00. Record the screen at 1080p, plus one camera shot of the wearer. Every shot that shows EEG carries an on-screen label: **Live EEG**, **Recorded**, or **Simulated**. Exports (`.mp4`, `.mov`, `.mkv`) are git-ignored, so share them through the team drive, not the repo.

| # | Time | Shot | Input label | How to capture | Ready? |
| --- | --- | --- | --- | --- | --- |
| 1 | 0:00–0:12 | Title card: Signal2Speech, team, "answer without speaking or typing" | — | Slide | Ready |
| 2 | 0:12–0:25 | Camera: wearer in the Unicorn headset; a judge asks the AQI question | — | Camera | Needs the headset slot |
| 3 | 0:25–0:50 | Evidence view: raw vs. filtered EEG with flash markers, OSCAR off vs. on, spectrum, averaged target vs. non-target P300 | Live EEG (or Recorded) | `python -m signal2speech.evidence --source hybridblack --record` | Code merged (#48). Live needs #23 |
| 4 | 0:50–1:10 | The tiles flash, and the preview shows "Washtenaw's AQI rose 186 points…" with no sound | Live EEG | `python -m signal2speech.app --input live` | P300 chooser merged (#46). Live app input needs #23 |
| 5 | 1:10–1:30 | Eyes closed about 2 s, then confirm; the map changes and the line is spoken once | Live EEG | Same run | Alpha confirm is PR #58 (#47). Real map is PR #65 (#30) |
| 6 | 1:30–1:45 | Close-up of the transcript and judge strip: one preview, one confirm, one spoken line; then cancel does nothing | Same as shot 5 | Same run, then a preview and key 2 to cancel | Ready (keyboard). Live needs #23 |
| 7 | 1:45–2:10 | AI Answering: type a question, pick a suggested reply, preview it, confirm, and it's spoken | Keyboard (say so) | `python -m signal2speech.ai` | Ready with the Stub. A real Claude reply needs `ANTHROPIC_API_KEY` (#5) |
| 8 | 2:10–2:30 | How it works: one diagram showing Unicorn → g.Pype (OSCAR, P300, alpha) → selection handler → speech and map; runs on Windows, macOS, and Linux | — | Diagram from [architecture](../architecture/README.md) | Ready |
| 9 | 2:30–2:45 | Closing card: repo link, team, "built with g.Pype" | — | Slide | Ready |

## Backup plan

- **No clean live run by the recording deadline:** use the best live recording (labelled **Recorded**) for shots 3–5. If there's none, use `--input simulated` with an on-screen **Simulated** label, and say in the voiceover that live EEG is shown at the table demo.
- **Real map not merged:** the app shows a labelled stand-in panel. Don't film it as the final map. Film shot 5 once #30 lands.

## Voiceover rules

- Say which input each shot uses whenever it isn't live EEG.
- Use the real numbers only: Washtenaw 32 → 218 (+186), Wayne 58 → 226 (+168).
