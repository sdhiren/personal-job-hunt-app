# TODO

Work items for the daily automation. Every day at about 1 PM, Claude picks **one** `pending` item, builds
it on a branch, tests it, and opens a pull request **for you to review and merge**. The PR also updates
the item here (status, branch, PR link), so merging it marks the item done. If nothing is pending, you get
a reminder (once a day) to add something.

The full rules Claude follows are in [`automation/todo-runner.md`](automation/todo-runner.md).

## How to add an item

Copy the template below into **Pending**, give it the next free ID, and describe the change. Clear
**Details** and **Done when** lines give the best results: if an item is too vague, Claude doesn't
guess. It sets the status to `needs-info` and writes its question under **Notes**.

```markdown
### T-001: Short title of the change
- **Status:** pending
- **Priority:** normal
- **Details:** What to change and why. Mention files, pages or behaviour if you know them.
- **Done when:** How we'll know it works (e.g. "the Jobs page shows a salary column").
- **Branch:** —
- **PR:** —
- **Updated:** —
- **Notes:** —
```

- **Status**: `pending`, then `done` when you merge its PR. While a PR titled `T-NNN: …` is open, Claude
  leaves that item alone. `needs-info` means Claude has a question for you (in **Notes** and in the PR):
  answer it, set the status back to `pending`, and merge (or edit the item here and close the PR).
  `blocked` means the tests failed or the change couldn't be finished: it's a draft PR with the details.
- **Priority**: `high`, `normal` or `low`. Claude takes the highest priority first, then the lowest ID.
- Claude fills in **Branch**, **PR**, **Updated** and **Notes**, editing items in place so open PRs don't
  conflict here. Move finished items to **Done** whenever you like.
- At most 3 of Claude's PRs wait for review at a time. After that, runs pause and remind you to review.

## Pending

<!-- Add new items here. -->

## Done

<!-- Move finished items here when you like. -->
