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

## Project board after every merge

The [Signal2Speech project board](https://github.com/orgs/Order-of-the-Golden-Eagles/projects/1) must match reality. After a PR merges, or when the developer says it merged, update the board in this order. You need `gh auth login -h github.com -s project,repo` first.

1. **Link the PR.** The board's "Linked pull requests" field fills in only from closing keywords in the PR description. Write `Closes #N` for each issue the PR fully finishes, and `Part of #N` for a parent or partly done issue. To fix a merged PR, edit its description with `gh pr edit <pr> --body-file <file>`. Editing after the merge links the PR but doesn't close the issue.
2. **Set the status by the issue's "Done when", not by the merge.**
   - **Done:** close the issue with a comment that names the PRs, what was verified (keyboard, simulated, recorded, or live EEG), and any blockers other issues still own.
   - **Not met yet:** leave the issue open as **In Progress**, with a comment listing what's left.
   - Never mark simulated or keyboard-only work as a live EEG result.
3. **Keep sub-issue progress real.** Each "Small deliverables" item belongs under its parent as a sub-issue: `gh issue edit <parent> --add-sub-issue <n>`. Tick the matching `- [x] #n` line in the parent's checklist. The "Sub-issues progress" field then updates as children close.
4. **Check the board.** `gh project item-list 1 --owner Order-of-the-Golden-Eagles --format json --limit 200` shows each item's status and linked PRs. `gh api repos/Order-of-the-Golden-Eagles/Signal2Speech/issues/<n>` shows `sub_issues_summary`.

Set the status from the CLI with these IDs:

```bash
# Status options: Todo c01c10ae · In Progress a7a3fcd2 · In Review ac72666e · Done b50673f4
ITEM=$(gh project item-list 1 --owner Order-of-the-Golden-Eagles --format json --limit 200 \
  --jq '.items[] | select(.content.number==<n>) | .id')
gh project item-edit --id "$ITEM" --project-id PVT_kwDOFUMxq84BrozG \
  --field-id PVTSSF_lADOFUMxq84BrozGzhp6lk8 --single-select-option-id <option-id>
```

- Post long comments with `gh issue comment <n> --body-file <file>`, then run `gh issue close <n> --reason completed`. `gh issue close` has no body-file option.
- Closing an issue or editing a teammate's PR is visible to the whole team. Confirm with the developer before doing it.
