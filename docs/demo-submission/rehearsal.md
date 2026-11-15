# Rehearsal checklist and failure recovery (#36, #13)

Rehearse on the **judging laptop** with the **frozen judging commit**. Write the commit SHA here: `________`.

## Launch commands

| Input | Command | Judge strip shows |
| --- | --- | --- |
| Keyboard | `python -m signal2speech.app --input keyboard` | `Input: Keyboard` (blue) |
| Simulated (g.Pype Generator) | `python -m signal2speech.app --input simulated --sim 2,1` | `Input: Simulated` (amber). Ctrl+1 and Ctrl+2 pick for the simulated brain. |
| Live EEG | `python -m signal2speech.app --input live` | **Blocked on `main` until #23.** Today it prints "Live EEG is blocked" and exits. |
| Evidence, Simulated | `python -m signal2speech.evidence --source generator` | Banner `INPUT: SIMULATED` |
| Evidence, Live | `python -m signal2speech.evidence --source hybridblack` | Banner `INPUT: LIVE EEG` |
| Evidence, Recorded | `python -m signal2speech.evidence --source replay recordings/evidence_<timestamp>` | Banner `INPUT: RECORDED` |
| P300 chooser on its own | `python -m signal2speech.eeg.p300 --source hybridblack` | Bare test tiles, Live EEG |

Use `--mute` only for silent dry runs. Rehearse at least once with audio on.

**Keys in the app:** `1` picks the left tile or confirms. `2` picks the right tile or cancels. `Esc` cancels. `D` simulates a headset drop.

**One headset, one process:** the Unicorn can only be opened by one program at a time. Don't launch the evidence view on `hybridblack` while the P300 chooser or the app holds the headset. Whether one headset can stream to two apps is still a question for the g.tec mentor. Until it's answered, show the evidence view from a **Recorded** replay of the 8:15 PM session, or close the app before opening it live.

## Timing targets

| Segment | Target | Hard limit | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- | --- |
| Whole run of show | 1:50 | 2:00 | | | |
| Question read → tiles start flashing | 10 s | 15 s | | | |
| Flashes start → preview shown (P300: about 2.5 s per chooser sequence; 3.5 s at the unvalidated app timing) | 8 s | 15 s | | | |
| Preview → confirm lands (alpha, about 2 s eyes closed) | 6 s | 12 s | | | |
| Confirm → speech starts | 1 s | 2 s | | | |
| Switch to evidence view | 3 s | 5 s | | | |
| Headset drop → fallback running and labelled | 10 s | 20 s | | | |

Measured on 2026-11-14 on Windows, headless, muted: keyboard `2,1` from launch to confirm in 2.7 s, simulated `2,1` in 10.4 s. These are plumbing times, not live EEG times.

## Test matrix

Run each row with keyboard first, then with simulated input, then live when #23 allows. Tick a box only for the input you actually used.

| # | Scenario | Steps | Expected | Kbd | Sim | Live |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Option 1, confirm | `1`, then `1` | Preview "Show the satellite view", then one map action and one spoken line | ☐ | ☐ | ☐ |
| 2 | Option 2, confirm | `2`, then `1` | Preview "Compare counties", then one `compare_air_quality` action and "Washtenaw's AQI rose 186 points. Wayne's rose 168 points." | ☐ | ☐ | ☐ |
| 3 | Cancel at preview | `2`, then `2` (or `Esc`) | No map action and no speech. Question reopens. | ☐ | ☐ | ☐ |
| 4 | Duplicate confirm | `2`, then `1`, `1` fast | Exactly one output | ☐ | ☐ | ☐ |
| 5 | Late input | Old-round decision arrives after a new round opens | `RejectedStaleRound` in the log. No output. | ☐ | ☐ | ☐ |
| 6 | Disconnect during preview | `2`, then `D` | No output. Connection label changes. Question reopens. | ☐ | ☐ | ☐ |
| 7 | Live confirm disarmed | Live EEG confirm before #23 arms it | `RejectedLiveConfirmDisarmed`. Keyboard can still confirm. | — | — | ☐ |

Cases 4 and 5 are also covered by `pytest` (`tests/test_app.py` and the contract scenarios). Run `pytest` on the judging laptop before rehearsing. Expect all tests to pass with 2 skipped (124 passed, 2 skipped on Windows on 2026-11-14).

## Live rehearsal log

| Time (ET) | Wearer | Input | Choose correct? | Confirm correct? | Choose → confirm (s) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
| | | | | | | |

Goal (#13): two deliberate EEG choices in a row, plus one clean live run recorded and labelled as backup. Record how many live runs succeeded out of how many tried.

## Failure-recovery script

The Spotter calls it, the Narrator says it, and the Operator does it. Say the new input label out loud every time.

| Failure | Spotter signal | Narrator says | Operator does |
| --- | --- | --- | --- |
| **Headset drops** (Connection label changes, flat or railing traces) | "Fallback." | "The headset just lost its connection. The app saw it and spoke nothing, which is the safe behaviour. I'll finish on the keyboard, and the strip now says Keyboard." | Close the app. Run `python -m signal2speech.app --input keyboard`. Press `2`, then `1`. |
| **P300 picks the wrong tile** | — | "It picked the other tile, which is why preview exists. We cancel and nothing is said." | Wearer or O presses `2` to cancel, then retries once. On a second miss, switch to keyboard and say so. |
| **Alpha confirm doesn't fire within 10 s** | "Keys." | "I'll confirm by keyboard. The alpha switch needs a calibrated wearer." | Press `1`. |
| **No live data at all** | "Simulated." | "We'll show the same pipeline on g.Pype's simulated signal. This is not a real brain." | `python -m signal2speech.app --input simulated --sim 2,1` |
| **Evidence average is flat on the headset** | — | "Expected: these flash markers have no visible flash yet. Here's the live signal that does respond: W, close your eyes." Then: "And here's what the P300 average looks like on g.Pype's simulator, labelled Simulated." | Point at the spectrum's 10 Hz peak. Then run `python -m signal2speech.evidence --source generator`, started 60 s earlier if possible. |
| **No audio** | — | "The audio isn't coming through. The line it spoke is in the log on the right." | Point at the transcript. Check volume and the output device afterwards. |
| **App crashes** | "Restart." | "Restarting. This takes three seconds." | Relaunch the last command from the terminal history. |

Never claim live EEG for a run that the judge strip doesn't label `Live EEG`.
