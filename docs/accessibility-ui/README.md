# Accessibility and UI

Keep choices stable during a round. Show the preview, confirm and cancel controls, connection state, and input mode.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

**Consolidated issues** · [#3](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/3)

## UI stack and layout

**Use PySide6 (Qt for Python), the same toolkit g.Pype's GUI is built on.** The choice tiles are our own Qt widgets. They flash for the P300 and send g.Pype `Marker` codes at each flash ([#46](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/46)). The g.Pype evidence scopes ([#48](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/48)) sit in the same window or a second one. The code lives in `signal2speech/ui/` ([#24](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/24)). Run it standalone with keyboard input while the EEG tracks are in progress.

| Screen region | Content | Driven by |
| --- | --- | --- |
| **Choice tiles** | Two large flashing tiles, `target-1` and `target-2`, relabelled per round. Keys 1 and 2 select the same tiles. | `on_round_opened` |
| **Preview** | The exact reply or action text in large type, with **Confirm** (close your eyes for 2 s, or key 1) and **Cancel** (key 2 or Esc). | `on_preview` |
| **Judge strip** | Input label (Keyboard / Simulated / Recorded / Live EEG), connection state, current round ID, last outcome | `on_handled`, `on_cleared` |
| **OpenOrbit panel** | June 26 and June 28 imagery with county AQI and separate attribution. Revealed only after a confirm. | sink `execute` ([#30](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/30), [#25](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/25)) |
| **Question input** | A typed question from the conversation partner, on the judge side | [#27](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/27) |

**Rules**

- The UI only renders handler events and calls `InputAdapter`. It never maps targets to actions, starts audio, or changes the map. See the [selection contract](../architecture/selection-contract.md).
- Freeze tile labels and positions for the whole round. Don't animate or reorder tiles while they flash. Flash timing must be steady, so send the `Marker` on the same frame the tile changes.
- A preview produces no audio and no map change. Cancel, disconnect, and reset return to a clean screen.
- Always show the input label so simulated input is never mistaken for live EEG.
- Use high contrast and large type (at least 48 px on tiles) so text is readable from the judge table.
