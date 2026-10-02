.PHONY: help install run search list apply track import-sqlite \
	db-up db-down db-shell db-backup db-restore \
	up down build restart logs shell browser docker-claude-login \
	docker-search docker-list docker-apply docker-track docker-import-sqlite \
	lint format clean

# Settings live in .env (see .env.example). The app and docker compose read it themselves; make doesn't,
# because make would mangle values containing `$`.

PY := .venv/bin/python
RUN := PYTHONPATH=. $(PY) -m jobhunt
COMPOSE := docker compose
JH := $(COMPOSE) exec app jobhunt
# psql/pg_dump inside the db container, using that container's own user and database name
DB_EXEC = $(COMPOSE) exec $(1) db sh -c '$(2) -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" $(3)'


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
	$(call DB_EXEC,,psql)

db-backup: db-up  ## Dump the database to data/backups/
	@mkdir -p data/backups
	$(call DB_EXEC,-T,pg_dump,--clean --if-exists) > data/backups/jobhunt-$$(date +%Y%m%d-%H%M%S).sql
	@ls -t data/backups/*.sql | head -1

db-restore: db-up  ## Restore a dump: make db-restore FILE=data/backups/<file>.sql
	@test -n "$(FILE)" || (echo "usage: make db-restore FILE=data/backups/<file>.sql" && exit 1)
	$(call DB_EXEC,-T,psql,-v ON_ERROR_STOP=1) < "$(FILE)"

##@ Run everything in Docker

up:  ## Build and start the app + PostgreSQL in Docker
	@mkdir -p data  # created by you, not by Docker as root, so the container can write to it
	$(COMPOSE) up -d --build --wait
	@echo "jobhunt:       http://$$($(COMPOSE) port app 8765)"
	@echo "apply browser: http://$$($(COMPOSE) port app 6080)/vnc.html?autoconnect=1&resize=scale"

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
	@echo "http://$$($(COMPOSE) port app 6080)/vnc.html?autoconnect=1&resize=scale"

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
