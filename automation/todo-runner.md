# Daily TODO runner

You are running unattended: the user isn't watching. Work through this procedure exactly. Do **one**
TODO item per run, or none. When something is unclear or unsafe, stop and report it rather than guessing.
Everything in `CLAUDE.md` applies too.

Notify the user with `automation/notify.sh "<title>" "<message>"` (a macOS notification). Every run must
end with exactly one notification that says what happened.

## 1. Preflight: stop if any check fails

Run these from the repository root:

1. `git status --porcelain` must print nothing. If the user has uncommitted work, **don't touch it**:
   notify "TODO run skipped: you have uncommitted changes" and stop.
2. `gh auth status` must succeed. If `gh` is missing or not signed in: notify "TODO run skipped: the GitHub
   CLI isn't set up (brew install gh && gh auth login)" and stop.
3. `git checkout main && git pull --ff-only`. If that fails, notify the reason and stop.
4. `make lint` and `make test` must pass on `main` **before** you change anything. If they fail, `main` is
   already broken: notify "TODO run skipped: main fails lint/tests" with the first error and stop.

## 2. Pick the item

Read `TODO.md`. Items are `### T-NNN: title` headings with a `- **Status:**` line.

1. **Finish an unfinished run first.** A previous run may have stopped part-way (laptop closed, app quit).
   Run `gh pr list --state open --json number,title,headRefName,isDraft`. If there's a **non-draft** PR
   whose title starts with `T-NNN:`, resume that item: `git checkout <headRefName> && git pull`, then
   continue at step 4 (or step 6/7 if the work is already complete). Draft PRs are blocked items: leave
   them alone.
   Also delete stale local or remote branches named `*/t-NNN-*` that have no PR, and treat their item as
   `pending`.
2. Otherwise take the `pending` item with the highest **Priority** (`high` > `normal` > `low`), lowest ID
   first among equals.
3. If no item is `pending`: notify "No pending TODO items: add some to TODO.md" and stop. Don't change
   anything.

**Is it clear enough?** If the item doesn't say what to change, or would need a decision only the user can
make (a new paid service, deleting data, a big redesign, anything touching security policy or how
applications are sent): set its **Status** to `needs-info`, write one specific question in **Notes**, ship
that `TODO.md` change as a `chore/todo-T-NNN-needs-info` PR (steps 5–7, no code), notify "T-NNN needs your
input: <question>", and stop.

Items that would delete user data, change the Claude-account / login model, send applications, or
weaken the request guard in `web.py` always need the user: treat them as unclear.

## 3. Branch

```bash
git checkout -b <type>/t-NNN-<short-kebab-title>   # type: feat, fix, refactor, docs, test or chore
```

In `TODO.md`, set the item's **Status** to `in-progress`, **Branch** to the branch name and **Updated** to
today's date (YYYY-MM-DD). Commit this first: `chore: start T-NNN`. (This only lives on the branch; on
`main` the item becomes `done` when the PR merges.)

## 4. Implement and test

- Make the smallest change that satisfies **Details** and **Done when**. Read the code you touch first and
  match its style. Don't refactor unrelated code.
- Add or update tests in `tests/` that prove the **Done when**. They must fail without your change and pass
  with it. No database, Claude or browser in tests (see `CLAUDE.md`).
- Update `README.md` (and `CLAUDE.md` if commands change) when behaviour, commands or settings change.
- Run `make format`, then `make lint` and `make test`. Both must pass.
- If the change affects the UI or API, check it on your own server on port 8766 (see `CLAUDE.md` → test
  servers): load the affected page, use the changed feature, look for console errors, then stop **your**
  server. Don't run job searches, Claude scoring or applications.
- Don't spend more than two attempts fixing failing tests or lint. If they still fail, go to **Blocked**
  below.

Commit with a clear message (what and why). End every commit message with:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

## 5. Pull request

```bash
git push -u origin <branch>
gh pr create --base main --title "T-NNN: <title>" --body-file <file>
```

PR body:

```markdown
Implements **T-NNN: <title>** from TODO.md.

## Changes
- …

## Testing
- `make lint` and `make test` pass (N tests); new tests: …
- Manual check: … (or "not needed: no UI/API change")

🤖 Generated with [Claude Code](https://claude.com/claude-code) by the daily TODO runner
```

## 6. Record it in TODO.md (same branch)

Update the item and **move it from Pending to the top of Done**:

- **Status:** `done`
- **Branch:** the branch name
- **PR:** `#<number> (<url>)`
- **Updated:** today's date
- **Notes:** one or two lines on what changed and anything the user should know.

Commit `chore: mark T-NNN done (#<number>)` and push, so the PR includes it.

## 7. Merge

Only if `make lint` and `make test` pass on the final commit:

```bash
gh pr merge <number> --squash --delete-branch
git checkout main && git pull --ff-only
make test                      # main must still be green after the merge
```

Never force-push, never push directly to `main`, never bypass branch protection, and never merge a PR you
didn't create in this run (except resuming per step 2.1).

## 8. Notify and finish

Notify "T-NNN done: <title> (PR #N merged)". Then print a short report: the item, what changed, the test
results, and the PR link.

## Blocked

If you can't finish (tests keep failing, the change turns out much bigger than described, or the
preflight passed but something unexpected breaks):

1. Commit what you have, push the branch, and open the PR as a **draft** (`gh pr create --draft ...`)
   describing what's done, what fails, and what you'd try next. Don't merge it.
2. Record it on `main`, so tomorrow's run doesn't pick the item again: from `main`, create
   `chore/todo-T-NNN-blocked`, set the item's **Status** to `blocked`, **PR** to the draft PR and
   **Notes** to the reason, then open, merge and clean up that PR as in steps 5 and 7.
3. Notify "T-NNN blocked: <one-line reason> (draft PR #N)".

A `blocked` item isn't picked again until the user sets it back to `pending`.
