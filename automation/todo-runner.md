# Daily TODO runner

You are running unattended: the user isn't watching. Work through this procedure exactly. Do **one**
TODO item per run, or none. When something is unclear or unsafe, stop and report it rather than guessing.
Everything in `CLAUDE.md` applies too.

**You open pull requests; you never merge them.** The user reviews and merges every PR. Never run
`gh pr merge`, never push to `main`, never approve or enable auto-merge.

Notify the user with `automation/notify.sh "<title>" "<message>"` (a macOS notification). Every run must
end with exactly one notification that says what happened.

## How progress is tracked

`TODO.md` on `main` only changes when the user merges a PR. So an item's status on `main` stays `pending`
until its PR is merged, and **an open PR whose title starts with `T-NNN:` means that item is waiting for
the user**: for review, for an answer (`needs-info`), or because it's `blocked`. Skip such items; never
work on an item that already has an open PR.

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

1. List open PRs: `gh pr list --state open --json number,title,headRefName,isDraft,url`. Collect the IDs
   of PRs titled `T-NNN: …`; those items are **waiting for the user**.
2. If **3 or more** `T-NNN` PRs are open, don't start new work: notify "N TODO PRs are waiting for your
   review" (with their numbers) and stop.
3. Clean up after interrupted runs: delete local and remote branches named `*/t-NNN-*` that have **no**
   open PR (`git branch -D …`, `git push origin --delete …`). Their items count as `pending` again.
4. Read `TODO.md` on `main`. Items are `### T-NNN: title` headings with a `- **Status:**` line. Ignore
   the template inside the code block. Take the `pending` item that isn't waiting for the user, with the
   highest **Priority** (`high` > `normal` > `low`), lowest ID first among equals.
5. If there's none: notify "No pending TODO items: add some to TODO.md" (add "N PRs waiting for your
   review" if any are open) and stop. Don't change anything.

**Is it clear enough?** If the item doesn't say what to change, or would need a decision only the user can
make (a new paid service, deleting data, a big redesign, anything touching security policy or how
applications are sent), go to **Needs info** below instead of implementing it. Items that would delete
user data, change the Claude-account / login model, send applications, or weaken the request guard in
`web.py` always need the user.

## 3. Branch

```bash
git checkout -b <type>/t-NNN-<short-kebab-title>   # type: feat, fix, refactor, docs, test or chore
```

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

## 5. Pull request (do not merge)

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

## How to review
- What to look at first, and how to try it (e.g. "run `make run`, open Jobs, …").

Merging this PR also marks T-NNN done in TODO.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code) by the daily TODO runner
```

## 6. Record it in TODO.md (same branch)

Edit the item **in place**: don't move it to another section, so open PRs for different items don't
conflict in `TODO.md`. Change only these fields of this item:

- **Status:** `done` (true once the user merges the PR)
- **Branch:** the branch name
- **PR:** `#<number> (<url>)`
- **Updated:** today's date (YYYY-MM-DD)
- **Notes:** one or two lines on what changed and anything the user should check.

Commit `chore: record T-NNN in TODO.md (#<number>)` and push, so the PR includes it. Run `make lint` and
`make test` once more on the final commit.

## 7. Notify and finish

`git checkout main`. Notify "T-NNN ready for review: PR #N <title>". Then print a short report: the item,
what changed, the test results, and the PR link.

## Needs info

The item isn't clear enough, or needs a decision only the user can make:

1. From `main`, create `chore/t-NNN-needs-info`. In `TODO.md`, set the item's **Status** to `needs-info`,
   **Updated** to today, and write one specific question in **Notes**.
2. Push and open a PR titled `T-NNN: needs info: <title>`, with the question in the body and: "Answer in
   TODO.md on this branch (set Status back to `pending`) and merge, or edit the item on `main` and close
   this PR."
3. Notify "T-NNN needs your input: <question> (PR #N)" and stop.

## Blocked

You can't finish: tests keep failing, the change turns out much bigger than described, or something
unexpected breaks.

1. In `TODO.md` on the branch, set the item's **Status** to `blocked`, **Updated** to today, and explain in
   **Notes**. Commit what you have and push.
2. Open the PR as a **draft** (`gh pr create --draft …`), titled `T-NNN: <title>`, describing what's done,
   what fails, and what you'd try next.
3. `git checkout main`. Notify "T-NNN blocked: <one-line reason> (draft PR #N)".

The open draft PR keeps later runs off this item until the user deals with it.
