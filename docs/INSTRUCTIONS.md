# Agent instructions

- Read [living memory](MEMORY.md), the relevant [category](README.md), and the assigned GitHub issue. Read the root README when you need the pitch or proposed stack.
- GitHub issues own priorities, status, and acceptance criteria. Category pages hold implementation notes. Living memory holds shared decisions and blockers.
- Use the checked-out code and reproducible evidence to confirm what works. Mark untested behavior and open decisions explicitly.
- Follow the issue's acceptance criteria, verify the smallest relevant flow, and report the result and any blocker. Preserve existing work.
- Use platform APIs and hardware-required packages. Keep the OpenOrbit demo usable offline. Label keyboard, simulated, recorded, and live EEG input accurately. Keep secrets and raw EEG out of git and public logs.
- When an issue is done, append a plain-language entry to [DEVLOG.md](../DEVLOG.md) in the same PR. The format is in [CLAUDE.md](../CLAUDE.md#devlog-after-every-issue).
- After a verified change, update the category when it helps the next developer. Update memory when a shared decision, setup step, blocker, or demo checkpoint changes. Replace stale notes and link to the issue or commit for detail.
- After a PR merges, update the project board: link the PR, set the status by the issue's "Done when", and keep sub-issue progress current. The steps are in [CLAUDE.md](../CLAUDE.md#project-board-after-every-merge).
