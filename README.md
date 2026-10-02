# jobhunt

A local job-search app. Upload your resume and it will **find jobs** (from company career boards and Claude web search), **match them to you**, **fill in applications**, and **track everything** on your computer.

```bash
make up         # everything in Docker: app at http://localhost:8765
make run        # or run the app natively (PostgreSQL still runs in Docker)
```

## Pages

| Page | What's there |
|---|---|
| **Dashboard** | Your profile at a glance (details, pay, notice period, target titles, skills), job counts, the application pipeline, matches by region, top matches and recent activity. |
| **Jobs** | Matches, Needs review and Filtered out tabs, with search, region and WFH filters. Each job shows its score, WFH, visa and rating. Click a job for the reasons behind its score, Claude's strengths/gaps, and the description. Apply singly or select several jobs to apply in bulk. |
| **Applications** | A Kanban board (To do → Applied → Screening → Interviewing → Offer → Closed). Drag cards to change status, open a card for its history and notes, and export to CSV. |
| **My profile** | Upload a resume (PDF, DOCX or TXT). **Fill profile from resume** has Claude extract your details, target titles and weighted skills. You can edit everything: salary (current, expected, currency), notice period, visa and relocation, regions, preferred cities, matching thresholds and apply mode. Saving re-scores all stored jobs. |
| **Settings** | Connect Claude, choose what Claude does, and pick job sources. |

## Connecting Claude

Pick one in **Settings**:

- **Claude account (Pro/Max)**: uses your subscription through the locally installed [Claude Code](https://claude.com/claude-code) CLI, running in headless mode (`claude -p`). **Sign in with Claude** opens `claude auth login` in Terminal, and the login happens in your browser on claude.ai. The app never handles your password or tokens. Usage counts toward your plan's limits.
- **API key**: paste a key from console.anthropic.com (tested before it's saved). Default model is `claude-opus-5`. It's stored only in `data/settings.json` (mode 600). Billed per token.
- **Off**: keyword matching only.

What Claude does (each can be switched off):
1. **Reads your resume** and fills in your profile and skills.
2. **Searches the web** for open roles in each region you chose (about 10 per region per search). It prefers direct ATS links, so those can be auto-filled too.
3. **Scores your best matches** against your resume, plus every job it found itself, about 40 per search.
4. **Drafts answers** to free-text application questions, using only facts from your resume.

## Job rules (editable on the Profile page)

| Rule | Default |
|---|---|
| India | WFH roles from score 55. On-site/hybrid only on a strong match (72 or higher). Delhi NCR, Bengaluru and Pune get a bonus. |
| Abroad (Europe, Canada, Australia) | The job description must offer sponsorship or relocation, or the company must be a known sponsor. Jobs saying "no sponsorship" are rejected. |
| Company rating | 3.5 or higher, relaxed to 3.3 for strong matches. Unknown ratings go to **Needs review**. Ratings are estimates (`config/companies.yaml`, or Claude's estimate for jobs it found). |

## Applying

**Apply** queues the job. A Chromium window opens, the form is filled (details, resume, sponsorship questions, Claude-drafted answers) and then:
- **Review first** (default): you check the form and click Submit. The app detects the confirmation page and moves the card to *Applied*. If it can't tell, the card waits in *To do* with an **I submitted it** button.
- **Auto-submit**: submits only when every required field is filled and no CAPTCHA is showing.

CAPTCHAs are never bypassed. The daily cap defaults to 15. LinkedIn, Naukri and Indeed aren't automated because their terms forbid it. For jobs you apply to there, open the job and click **I applied myself**.

## Setup

There are two ways to run it. Both store jobs and applications in PostgreSQL (in Docker) and keep your profile, resume and settings in `data/`, so you can switch between them.

### Option 1: everything in Docker

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env    # optional: change the database password or ports
make up                 # build and start the app + PostgreSQL
```

- App: http://localhost:8765
- Application browser: http://localhost:6080/vnc.html (or `make browser`). Chromium runs on a virtual display inside the container. When you click **Apply**, open this page to review the form and click Submit. The app links to it while applications are running.
- Claude account (Pro/Max): run `make docker-claude-login` once. The sign-in is kept in a Docker volume. Alternatively, run `claude setup-token` on your computer and put the token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`. The API key option works as usual from **Settings**.
- Commands: `make docker-search`, `docker-list`, `docker-apply`, `docker-track`, plus `make logs`, `make shell` and `make down`.

### Option 2: run the app on your computer

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker (for PostgreSQL) and, for the Claude account option, [Claude Code](https://claude.com/claude-code).

```bash
make install   # virtualenv, dependencies, Chromium for form filling
make run       # starts PostgreSQL in Docker, then the app at http://127.0.0.1:8765
make help      # every command (search, list, apply, track, database, Docker, lint…)
```

To use a PostgreSQL you already run, set `DATABASE_URL` in `.env` (for example `postgresql://user:pass@localhost:5432/jobhunt`) and start the app with `PYTHONPATH=. .venv/bin/python -m jobhunt app`. The tables are created automatically on first start.

### Moving from the SQLite version

Earlier versions stored everything in `data/jobhunt.db`. Copy it into PostgreSQL once:

```bash
make import-sqlite          # or: make docker-import-sqlite
```

It can be run again safely, because rows that already exist are skipped. The SQLite file isn't changed or deleted.

### Database commands

| Command | What it does |
|---|---|
| `make db-up` / `make db-down` | Start or stop PostgreSQL. The data is kept in the `jobhunt_pgdata` Docker volume. |
| `make db-shell` | Open `psql` on the database |
| `make db-backup` | Write a dump to `data/backups/` |
| `make db-restore FILE=…` | Restore a dump |

All ports are published to `127.0.0.1` only, so nothing is reachable from your network.

## Your data

| Where | Contents |
|---|---|
| PostgreSQL (`jobhunt_pgdata` volume) | Jobs, applications and history |
| `data/profile.yaml` | Your profile |
| `data/settings.json` | Claude connection and sources |
| `data/resume/` | Your resume |
| `data/screenshots/` | Screenshots of each filled form |
| `data/backups/` | Database dumps from `make db-backup` |

`config/` holds the shipped template and the company list. `make down` keeps all of this. Only `docker compose down -v` deletes the database volume.
