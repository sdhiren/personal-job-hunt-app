# jobhunt: notes for Claude

A local, single-user job-search app: FastAPI + PostgreSQL (Docker) backend in `jobhunt/`, a no-build
ES-module UI in `jobhunt/static/js/`, Playwright form filling in `jobhunt/apply/`, and Claude through
`jobhunt/claude_backend.py` (Claude account via the `claude` CLI, or an API key). All prompts live in
`jobhunt/prompts.py`.

## Commands

- `make lint`: ruff check + format check. Must pass before every commit.
- `make format`: auto-fix formatting and lint issues.
- `make test`: pytest, no database or Claude needed. Must pass before every commit.
- `make run`: the app at http://127.0.0.1:8765 (also starts PostgreSQL in Docker). **That port is the
  user's.** For your own testing use `PYTHONPATH=. .venv/bin/python -m jobhunt app --port 8766 --no-open`.

## Rules

- **Never commit personal data.** `data/`, `.env`, resumes and anything with the user's name, email,
  phone, API keys or tokens stay out of git. Check `git diff --cached` before committing.
- Commits use the repo's configured identity (`sdhiren <sdhiren@users.noreply.github.com>`). Don't change
  git config.
- Every change goes through a branch and a pull request, never a direct push to `main`. Branch names:
  `feat/…`, `fix/…`, `refactor/…`, `docs/…`, `test/…`, `chore/…` plus a short kebab-case description.
- Add or update tests in `tests/` for every behaviour change. Tests must not need PostgreSQL, Claude or a
  browser; use fakes, as in `tests/test_apply_queue.py`.
- **Test servers:** before starting one, check the port is free (`lsof -iTCP:<port> -sTCP:LISTEN`), record
  its PID, test, then stop **only that PID**. Never stop a process you didn't start.
- **Database:** tests against the real database must only read, or roll back. Never delete or rewrite the
  user's jobs or applications.
- **Claude quota:** don't run real job searches, Claude scoring or applications while testing. They spend
  the user's Claude plan, and applications go to real employers.
- If you change a prompt in `prompts.py`, bump that prompt's `version`.
- Keep the README accurate when behaviour, commands or settings change.
- Follow the existing style: ruff (line length 120) for Python, no build step and no new frameworks for
  the UI, and new Python dependencies only when clearly needed (say why in the PR).

## Daily automation

`TODO.md` is the work list and `automation/todo-runner.md` is the procedure a scheduled run follows.
