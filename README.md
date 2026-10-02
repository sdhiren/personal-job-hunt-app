# jobhunt

A local job-search app. Upload your resume and it will **find jobs** (from company career boards and Claude web search), **match them to you**, **fill in applications**, and **track everything** on your computer.

```bash
make run        # starts the app and opens http://127.0.0.1:8765
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

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and, for the Claude account option, [Claude Code](https://claude.com/claude-code).

```bash
make install   # virtualenv, dependencies, Chromium for form filling
make run       # start the app at http://127.0.0.1:8765
make help      # every command (search, list, apply, track, lint, format…)
```

Data is stored in SQLite under `data/`, so it survives restarts.

## Your data

Everything is stored locally in `data/`:

| File | Contents |
|---|---|
| `jobhunt.db` | Jobs, applications and history (SQLite) |
| `profile.yaml` | Your profile |
| `settings.json` | Claude connection and sources |
| `resume/` | Your resume |
| `screenshots/` | Screenshots of each filled form |

`config/` holds the shipped template and the company list.
