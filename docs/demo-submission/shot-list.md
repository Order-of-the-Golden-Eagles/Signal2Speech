# Submission video shot list (#34, #13)

**Hard limit: under 3:00. Target: 2:45.** That leaves 15 seconds of margin for titles and export rounding. Check the exported file's length, not the editor timeline.

Every shot that shows EEG carries an on-screen caption naming its source: **Live EEG**, **Recorded**, **Simulated** or **Keyboard**. The app's judge strip and the evidence banner already show it, so the caption must agree with them. Never cut a Simulated or Keyboard shot under narration that says "live".

## Primary cut (2:45)

| # | Time | Picture | Narration (voice-over or on camera) | Caption |
| --- | --- | --- | --- | --- |
| 1 | 0:00–0:10 | Wearer in the Unicorn Hybrid Black, looking at the screen. | "Some people can't speak or type. Signal2Speech lets them answer with brain signals." | Signal2Speech · Hack the Nest 2026 |
| 2 | 0:10–0:20 | Partner reads the question card. Cut to the two tiles. | "A partner asks a question. The app offers two short answers." | — |
| 3 | 0:20–0:40 | Tiles flashing, close on the screen, with the wearer's face in picture-in-picture. | "Each flash of the tile the wearer is watching makes a P300, a small response about 300 milliseconds later. g.Pype cuts out each flash and an LDA classifier picks the tile." | Input label from the strip |
| 4 | 0:40–0:50 | *Say this?* preview card. | "That's only a preview. Nothing is spoken yet." | — |
| 5 | 0:50–1:02 | Wearer closes their eyes for about 2 s. The confirm lands. | "To confirm, the wearer closes their eyes. The alpha rhythm rises, which is a different brain signal from the P300." | Live EEG, Recorded, or **Keyboard confirm** if #47 isn't live |
| 6 | 1:02–1:22 | Map switches to June 28. App speaks the line. | App audio: "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." | NASA MODIS · EPA AirData (stand-in panel until #30) |
| 7 | 1:22–1:50 | g.Pype evidence window. (a) OSCAR off/on panels during a blink, then the spectrum's 10 Hz peak rising with eyes closed (Live or Recorded). (b) Slow zoom onto the averaged target vs non-target plot. | (a) "OSCAR, g.tec's artifact removal, cleans out blinks in real time. When the wearer closes their eyes, their alpha rhythm jumps. That's the confirm signal." (b) "Averaging every flash brings out the P300 around 300 milliseconds." | Banner text for each part. (b) is **Simulated** until the #46 ↔ #48 seam lets the chooser's tiles drive the evidence markers. |
| 8 | 1:50–2:05 | Cancel: pick a tile, then cancel at the preview. Empty output. | "Changed your mind? Cancel, and nothing is spoken." | — |
| 9 | 2:05–2:25 | Diagram from [the architecture walkthrough](../architecture/README.md): device → g.Pype → selection contract → app. Then the CI matrix with three green OS checks. | "Every input speaks one selection contract: keyboard, simulator, P300, alpha switch, or any g.tec device through a g.Pype pipeline. It runs on Windows, macOS and Linux, and CI tests all three." | Platform, not a product |
| 10 | 2:25–2:45 | Team of four at the table. Repo URL on screen. | "Built in one weekend by the Order of the Golden Eagles. Code, docs and the AI-use disclosure are in the repo." | Repo link · AI disclosure |

## Backup path: Recorded (g.Pype replay)

Use this if live capture fails or is too noisy to read. It's honest as long as every frame says **Recorded**.

1. At the 8:15 PM headset slot, record a session (see [pre-flight](preflight.md)):
   `python -m signal2speech.evidence --source hybridblack --record`
   This writes EEG and flash markers as HDF5 under `recordings/evidence_<timestamp>/`. That folder is gitignored. Never commit it, and don't upload it anywhere. During the recording the wearer blinks a few times, then alternates 10 s eyes open and 10 s eyes closed.
2. Replay it for shot 7:
   `python -m signal2speech.evidence --source replay recordings/evidence_<timestamp>`
   The window title and banner say **Recorded**. Use `--speed 2` if the shot is short, and say so in the caption ("Recorded, 2× speed").
   **What this recording can honestly show:** OSCAR off against on during blinks, and the alpha peak in the spectrum during eyes closed. **What it can't show:** a real P300 average. On `hybridblack`, the built-in `Flasher` sends markers with no visible flash, so the target trace has no brain response to lock onto. A Recorded P300 average needs the #46 ↔ #48 seam first (the chooser's visible tiles emitting on the evidence graph's marker, with `--no-flasher`). Until then, the P300-average part of shot 7 is **Simulated** and captioned that way.
3. Shots 3 to 6 then come from the app with `--input keyboard` or `--input simulated`, captioned **Keyboard** or **Simulated**. Recorded replay inside the app (`--input recorded`) is still blocked on `main`. It prints "Recorded replay is blocked: needs record/replay (#48)".
4. Narration for shot 7 changes to: "This is a recording of our real headset session, replayed through the same g.Pype pipeline."

**Last-resort path, no headset data at all:** all of shot 7 uses `python -m signal2speech.evidence --source generator`, captioned **Simulated: synthetic P300, not a brain**. Run it for at least 60 seconds before you start the shot. An 8-second run doesn't build a readable average yet.

## Capture settings

- Screen at 1920×1080. Use OBS or the OS recorder. Turn off notifications and Wi-Fi (the demo runs offline).
- Record app audio directly, not through a microphone near the speakers.
- Record each shot on its own and assemble afterwards. Keep two good takes of shots 3 to 7.
- Export as H.264 MP4. Check that the length is under 3:00 and that the audio is in sync on the confirm-to-speech cut.

## Submission fields (#34)

| Field | Value | Done |
| --- | --- | --- |
| Public repo | https://github.com/Order-of-the-Golden-Eagles/Signal2Speech (check it's public) | ☐ |
| Team | All four teammates added on Devpost | ☐ |
| Tracks | Sponsor track(s) selected, including g.tec | ☐ |
| AI disclosure | Claude (Anthropic) used for coding help and for reply suggestions in the app (the Stub provider when there's no key) | ☐ |
| Video | Under 3:00, linked, plays without sign-in | ☐ |
| Draft on Devpost and event app | By midnight Saturday | ☐ |
| Final on Devpost | By Sunday noon ET | ☐ |
| Separate g.tec submission | Nov. 30, if it applies. Track it in #13. | ☐ |
