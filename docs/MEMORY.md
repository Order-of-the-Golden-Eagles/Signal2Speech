# Living memory

## Product

- **Signal2Speech** is a hands-free communication prototype. AI Answering suggests replies to a question. The EEG wearer selects, previews, and confirms the exact words before the app speaks.
- **OpenOrbit** uses the same controls to explore NASA imagery and EPA air quality. Its MVP is one confirmed map-and-speech reveal. From June 26 to June 28, 2023, Washtenaw AQI rose from 32 to 218 and Wayne AQI from 58 to 226.

## Decisions and open questions

- **Stack (pivoted 2026-11-14):** Python 3.12, g.Pype 4.2, and PySide6 in one process. We use the Unicorn Hybrid Black through the `HybridBlack` source with OSCAR on. No Unity, no Unicorn Suite, and no licence needed. Use keyboard or `Generator` input before live headset access.
- Use platform APIs and hardware-required packages. Bundle OpenOrbit data and demo audio locally.
- Selection contract is final in [#22](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/22). It covers the event shape, IDs, round rules, folder ownership, and dependency order. See [selection-contract.md](architecture/selection-contract.md). `signal2speech/core/` holds the pure-Python handler, and `pytest` must stay green. Live EEG confirm stays disarmed until #23.
- **Decoding:** choose with P300 (our flashing tiles → `Epochs` → `Sklearn` LDA, #46). Confirm with an alpha switch, eyes closed for about 2 s (#47). Fallback: step through options one at a time and confirm each with the alpha switch. Judges see evidence scopes (#48).
- **Ask the g.tec mentor:** Paradigm Presenter licence, MCP visualizer access, and whether one headset can stream to two apps at once.
- The AI provider is TBD. See the [architecture walkthrough and input contract](architecture/README.md) and [AI Answering](ai-answering/README.md).

## Verification and next checkpoint

- The initial docs record the plan. Live EEG and app behavior are pending verification.
- See the [sprint issue](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/16) for the current checkpoint and priorities.

Replace outdated notes when a decision, blocker, or verified result changes. Link to the issue or commit for details.
