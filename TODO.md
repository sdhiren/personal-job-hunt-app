# TODO

Work items for the daily automation. Every day at about 1 PM, Claude picks **one** `pending` item, builds
it on a branch, tests it, opens a pull request, merges it, and updates the item here with the PR link.
If nothing is pending, you get a reminder (once a day) to add something.

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

- **Status**: `pending` → `in-progress` → `done`. `needs-info` means Claude has a question for you (see
  **Notes**); answer it there and set the status back to `pending`. `blocked` means the tests failed or the
  change couldn't be finished; the PR is left open with the details.
- **Priority**: `high`, `normal` or `low`. Claude takes the highest priority first, then the lowest ID.
- Claude fills in **Branch**, **PR**, **Updated** and **Notes**. Don't edit an item while it's
  `in-progress`.

## Pending

<!-- Add new items here. -->

## Done

<!-- Claude moves finished items here, newest first. -->
