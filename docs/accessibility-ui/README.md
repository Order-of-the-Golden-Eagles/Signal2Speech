# Accessibility and UI

Keep choices stable during a round. Show the preview, confirm and cancel controls, connection state, and input mode.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

**Consolidated issues** · [#3](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/3)

## UI stack and layout

**Choice tiles are the vendor's `ERPFlashTag3D` 3D objects with TextMeshPro (3D) labels. Use uGUI (Canvas) with TextMeshPro for everything else, not UI Toolkit.** The **BCI Visual ERP 3D** prefab ships 5 flash tags. Use 2 for `target-1` and `target-2`, and disable the other 3 (or leave them unmapped in `EegClassMap` so the handler never sees them). The preview text, judge strip, OpenOrbit panel, and question input are uGUI overlays. The code lives in `unity/Signal2Speech/Assets/Signal2Speech/UI/` ([#24](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/24)). Build and test in `Scenes/Dev/UI.unity`; only #25 edits `Demo.unity`.

| Screen region | Content | Driven by |
| --- | --- | --- |
| **Choice tiles** | Two large `ERPFlashTag3D` tags, `target-1` and `target-2`, relabelled per round. Keys 1 and 2 select the same tags. | `RoundOpened` |
| **Preview** | The exact reply or action text in large type. The tiles relabel to **Confirm** and **Cancel**. | `PreviewShown` |
| **Judge strip** | Input label (Keyboard / Simulated / Recorded / Live EEG), connection state, current round ID, last outcome | `Handled`, `Cleared` |
| **OpenOrbit panel** | June 26 and June 28 imagery with county AQI and separate attribution. Revealed only after a confirm. | `IActionSink` ([#30](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/30), [#25](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/25)) |
| **Question input** | A typed question from the conversation partner, on the judge side | [#27](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/27) |

**Rules**

- The UI only renders handler events and calls `InputAdapter`. It never maps targets to actions, starts audio, or changes the map. See the [selection contract](../architecture/selection-contract.md).
- Freeze tile labels and positions for the whole round. Don't animate or reorder tiles while stimuli flash.
- A preview produces no audio and no map change. Cancel, disconnect, and reset return to a clean screen.
- Always show the input label so simulated input is never mistaken for live EEG.
- Use high contrast and large type (at least 48 px on tiles) so text is readable from the judge table.
