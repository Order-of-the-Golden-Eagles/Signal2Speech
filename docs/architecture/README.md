# How Signal2Speech works

Signal2Speech helps someone answer without speaking or typing. A conversation partner enters a question. The app shows a few possible replies or actions. The wearer uses the headset to pick one, sees exactly what the app will say or show, and makes a second choice to confirm it.

**AI Answering** supplies possible replies. **OpenOrbit** is a feature that can show NASA imagery alongside EPA air-quality readings. Both use the same controls.

## Follow one answer

1. A judge asks, “Which county’s AQI rose more between June 26 and June 28, 2023?”
2. Signal2Speech offers **Show the satellite view** and **Compare counties**.
3. The wearer selects **Compare counties**. The app previews the reply and shows **Confirm** and **Cancel**.
4. The wearer selects **Confirm** in a new round. OpenOrbit updates the map and speaks, “Washtenaw’s AQI rose 186 points. Wayne’s rose 168 points.”

A **round** is one chance to choose from the options currently on screen. Choosing a reply and confirming it are two separate rounds. The headset’s software reports which on-screen target the wearer selected. The app decides what that target means in the current round.

```mermaid
flowchart TD
    Q["Question and reply choices"] --> S["Selection handler"]
    K["Keyboard"] --> A["Input adapter"]
    M["Simulator"] --> A
    G["g.tec headset and decoder"] --> A
    A --> S
    S --> P["Preview and ask for confirmation"]
    P -->|Confirm in a new round| O["Speak reply and show evidence"]
    P -->|Cancel| S
    O --> T["Speech"]
    O --> E["OpenOrbit map when requested"]
```

## First demo host

**Use the sponsor’s Unity ERP scene and C# for the first live build.** Keep the sponsor’s stimulus layout while verifying target IDs. Run keyboard and simulated input through the same app handler, so the rest of the team can work while the headset is unavailable. The first hardware rehearsal starts by opening the sponsor scene in Unity and pressing **Play**. Signal2Speech’s scene path and launch instructions are pending implementation.

A separate browser UI and localhost bridge are **TBD**. The in-process contract below applies whether the demo stays in Unity or later gains a bridge. [g.tec Unity ERP starter](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/build-your-first-erp-application.md)

## Developer handoff

**The finalized contract, code, and tests are in [selection-contract.md](selection-contract.md).** It also covers folder ownership and issue dependencies. This section is the short version.

**Input adapter → selection handler → confirmed action → speech or OpenOrbit.**

The input adapter maps keys, simulated choices, and decoded headset classes to the same event. The following are three alternative inputs for the same visible option in the same example round. The app issues the round ID. The adapter issues the event ID and maps the source-specific input to an app target.

| Source | Example event |
| --- | --- |
| Keyboard | `{"source":"keyboard","roundId":"r1","eventId":"k1","targetId":"target-2"}` |
| Simulator or test input | `{"source":"simulated","roundId":"r1","eventId":"s1","targetId":"target-2"}` |
| Live headset | `{"source":"live-eeg","roundId":"r1","eventId":"e1","targetId":"target-2"}` |

- The app owns the visible options and their mapping. Example choice round `r1` maps `target-1` to `show_satellite` and `target-2` to `compare_air_quality`. Example confirmation round `r2` maps `target-1` to Confirm and `target-2` to Cancel. Verify the vendor’s numeric class mapping in the installed scene.
- Freeze options for the round. Accept one valid target from the active input source and consume the round before updating the UI or running an effect. Drop unknown targets, duplicate events, and events for any other round.
- On a preview, keep the exact text and action ID together. On a fresh Confirm, consume that pending choice before sending it to speech or the map, so a repeated callback cannot run it twice. Cancel, reset, or disconnect closes the round and clears the preview.
- g.tec documents an `On Class Selection` callback with a decoded class. The published callback example supplies no app round ID. The adapter must establish the round at capture time or verify a starter transition that isolates callbacks from the previous round. Assigning the current round at callback arrival could mistake an old choice for a confirmation. Keep live confirmation disarmed until the boundary is verified. [g.tec callback example](https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Unity-Interface/blob/main/tutorial/build-your-first-erp-application.md#advance-unity-event-callbacks)

| Confirmed action | What happens |
| --- | --- |
| `speak_reply` | Speak the exact previewed reply the wearer approved. |
| `show_satellite` | Show the June 28 NASA MODIS image and speak its short explanation. |
| `compare_air_quality` | Show the June 26–28 NASA imagery and county AQI comparison, then speak the computed result. |

### First integration check

Send any one of the example events for `r1`. Expect a preview and no speech or map change. Replay it while `r2` is active. Expect no change. Send a fresh `r2` selection of `target-1`. Expect the AQI reveal and one spoken reply. Repeat that confirmation to check for duplicate output. In a separate run, select Cancel or disconnect during preview. Expect silence and no map change.

These are the handoff examples for [headset input (#2)](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/2) and [integration (#4)](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4). Device class mapping, callback boundaries, and the end-to-end app still need verification in the running starter. [Architecture issue #1](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/1)
