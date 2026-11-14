# Living memory

## Product

- **Signal2Speech** is a hands-free communication prototype. AI Answering suggests replies to a question. The EEG wearer selects, previews, and confirms the exact words before the app speaks.
- **OpenOrbit** uses the same controls to explore NASA imagery and EPA air quality. Its MVP is one confirmed map-and-speech reveal. From June 26 to June 28, 2023, Washtenaw AQI rose from 32 to 218 and Wayne AQI from 58 to 226.

## Decisions and open questions

- Start with g.tec Unicorn Hybrid Black and the Unity ERP starter. Use keyboard or simulated input before live headset access.
- Use platform APIs and hardware-required packages. Bundle OpenOrbit data and demo audio locally.
- Selection contract is final in [#22](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/22). It covers the event shape, IDs, round rules, folder ownership, and dependency order. See [selection-contract.md](architecture/selection-contract.md). `core/` holds the plain C# handler, and `dotnet test core/DotNetTests~` must stay green. Live EEG confirm stays disarmed until #23.
- **The SDK needs Unity 2022.3 (2022.3.11f1), not Unity 6.** The judging build is Unity-only: vendor `ERPFlashTag3D` tags plus uGUI overlays, with no browser UI or bridge. [Launch path](dev-setup-docs/README.md#unity-launch-path-19).
- **Blocker (#19):** Vasanth's laptop has no Unity Hub, no Unity 2022.3, and no Unicorn Suite. The leftover 6000.0.40f1 folder is unused. Install them, then create and commit `unity/Signal2Speech`.
- Vendor simulator `UN-0000.00.00` drives the real ERP pipeline without a headset, so use it for #21.
- The AI provider is TBD. See the [architecture walkthrough and input contract](architecture/README.md) and [AI Answering](ai-answering/README.md).

## Verification and next checkpoint

- The initial docs record the plan. Live EEG and app behavior are pending verification.
- See the [sprint issue](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/16) for the current checkpoint and priorities.

Replace outdated notes when a decision, blocker, or verified result changes. Link to the issue or commit for details.
