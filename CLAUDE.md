# Signal2Speech agent index

**Caveman mode.** Keep chat and progress updates terse. Short sentences. Preserve precise technical details. Use normal, readable language for code, docs, and judging material.

1. [Agent instructions](docs/INSTRUCTIONS.md)
2. [Living memory](docs/MEMORY.md)
3. [Issue categories](docs/README.md)

Open only the linked category and issue relevant to your task. Use ordinary links without auto-importing the docs.

## Devlog after every issue

When you finish an issue, append one entry to the bottom of [DEVLOG.md](DEVLOG.md) in the same PR, after the tests pass and the docs are updated. The devlog is for humans, so write in plain language: what changed, why it matters for the demo, and what is still unverified. Leave out implementation detail that the docs or the code already cover.

```markdown
## MM/DD/YY - H:MM AM/PM - <Developer name> - #<issue> <short title> ([PR #<n>](<PR link>))
- What a teammate or judge can now do, in one line
    - Nested bullets for the command to run or one key detail
- Why a change was made, when that isn't obvious (a bug it prevents, a decision)
- What was verified and how (keyboard, simulated, recorded, or live EEG), and what still needs the headset or the judging laptop
```

- Use Eastern time, the hackathon clock, from `date`. For the developer name, use what the developer asked for. If they haven't said, use `git config user.name`.
- Write 3–7 bullets. Name commands and files in backticks. Don't use jargon a teammate outside your track wouldn't know.
- Append only. Never edit or reorder other people's entries. `.gitattributes` sets `merge=union` on DEVLOG.md. When you merge `main` into your branch, keep both sides' entries in time order. `union` duplicates a line when both sides edited it, so check for repeated headings after a merge. GitHub's merge button ignores `union` and reports a DEVLOG conflict. Merge `main` locally and push.
- If you add the entry before the PR exists, write `(PR pending)` and fix it once the PR is open.
