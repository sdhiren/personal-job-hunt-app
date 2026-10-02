.PHONY: help install run search list apply track import-sqlite \
	db-up db-down db-shell db-backup db-restore \
	up down build restart logs shell browser docker-claude-login \
	docker-search docker-list docker-apply docker-track docker-import-sqlite \
	lint format clean

# Settings come from .env when present (see .env.example)
-include .env
POSTGRES_USER ?= jobhunt
POSTGRES_PASSWORD ?= jobhunt
POSTGRES_DB ?= jobhunt
POSTGRES_PORT ?= 5432
JOBHUNT_PORT ?= 8765
JOBHUNT_VNC_PORT ?= 6080
DATABASE_URL ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)
export DATABASE_URL

PY := .venv/bin/python
RUN := PYTHONPATH=. $(PY) -m jobhunt
COMPOSE := docker compose
JH := $(COMPOSE) exec app jobhunt
PSQL := $(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

help:  ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^##@/ {printf "\n%s\n", substr($$0, 5)} /^[a-z-]+:.*## / {printf "  make %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Run locally (Python on your machine, PostgreSQL in Docker)

install:  ## Create the virtualenv and install dependencies + Chromium
	uv venv --python 3.12 .venv
	uv pip install -e ".[dev]"
	$(PY) -m playwright install chromium

run: db-up  ## Start the app at http://127.0.0.1:8765
	$(RUN) app

search: db-up  ## Find and score jobs from the command line
	$(RUN) scrape

list: db-up  ## Show current matches
	$(RUN) list

apply: db-up  ## Fill applications for the top 5 matches
	$(RUN) apply -n 5

track: db-up  ## Show the application tracker
	$(RUN) track

import-sqlite: db-up  ## Copy data from the old SQLite file (data/jobhunt.db) into PostgreSQL
	$(RUN) import-sqlite

##@ Database

db-up:  ## Start PostgreSQL (waits until it accepts connections)
	$(COMPOSE) up -d --wait db

db-down:  ## Stop PostgreSQL (data is kept)
	$(COMPOSE) stop db

db-shell: db-up  ## Open psql on the jobhunt database
	$(COMPOSE) exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db-backup: db-up  ## Dump the database to data/backups/
	@mkdir -p data/backups
	$(COMPOSE) exec -T db pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) --clean --if-exists \
		> data/backups/jobhunt-$$(date +%Y%m%d-%H%M%S).sql
	@ls -t data/backups/*.sql | head -1

db-restore: db-up  ## Restore a dump: make db-restore FILE=data/backups/<file>.sql
	@test -n "$(FILE)" || (echo "usage: make db-restore FILE=data/backups/<file>.sql" && exit 1)
	$(PSQL) -v ON_ERROR_STOP=1 < $(FILE)

##@ Run everything in Docker

up:  ## Build and start the app + PostgreSQL in Docker
	@mkdir -p data  # created by you, not by Docker as root, so the container can write to it
	$(COMPOSE) up -d --build --wait
	@echo "jobhunt:       http://localhost:$(JOBHUNT_PORT)"
	@echo "apply browser: http://localhost:$(JOBHUNT_VNC_PORT)/vnc.html?autoconnect=1&resize=scale"

down:  ## Stop the containers (database and settings are kept)
	$(COMPOSE) down

build:  ## Rebuild the app image
	$(COMPOSE) build app

restart:  ## Restart the app container
	$(COMPOSE) restart app

logs:  ## Follow the app logs
	$(COMPOSE) logs -f app

shell:  ## Open a shell in the app container
	$(COMPOSE) exec app bash

browser:  ## Print the address of the in-container application browser
	@echo "http://localhost:$(JOBHUNT_VNC_PORT)/vnc.html?autoconnect=1&resize=scale"

docker-claude-login:  ## Sign Claude Code (your Pro/Max plan) in inside the container
	$(COMPOSE) exec app claude auth login --claudeai

docker-search:  ## Find and score jobs (in Docker)
	$(JH) scrape

docker-list:  ## Show current matches (in Docker)
	$(JH) list

docker-apply:  ## Fill applications for the top 5 matches; watch at `make browser` (in Docker)
	$(JH) apply -n 5

docker-track:  ## Show the application tracker (in Docker)
	$(JH) track

docker-import-sqlite:  ## Copy data from data/jobhunt.db into PostgreSQL (in Docker)
	$(JH) import-sqlite

##@ Development

lint:  ## Lint and check formatting
	$(PY) -m ruff check jobhunt
	$(PY) -m ruff format --check jobhunt

format:  ## Auto-format and fix lint issues
	$(PY) -m ruff format jobhunt
	$(PY) -m ruff check --fix jobhunt

clean:  ## Remove caches (keeps your data/ folder and the database)
	find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	rm -rf .ruff_cache *.egg-info
