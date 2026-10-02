.PHONY: help install run search list apply track lint format clean

PY := .venv/bin/python
RUN := PYTHONPATH=. $(PY) -m jobhunt

help:  ## Show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

install:  ## Create the virtualenv and install dependencies + Chromium
	uv venv --python 3.12 .venv
	uv pip install -e ".[dev]"
	$(PY) -m playwright install chromium

run:  ## Start the app at http://127.0.0.1:8765
	$(RUN) app

search:  ## Find and score jobs from the command line
	$(RUN) scrape

list:  ## Show current matches
	$(RUN) list

apply:  ## Fill applications for the top 5 matches
	$(RUN) apply -n 5

track:  ## Show the application tracker
	$(RUN) track

lint:  ## Lint and check formatting
	$(PY) -m ruff check jobhunt
	$(PY) -m ruff format --check jobhunt

format:  ## Auto-format and fix lint issues
	$(PY) -m ruff format jobhunt
	$(PY) -m ruff check --fix jobhunt

clean:  ## Remove caches (keeps your data/ folder)
	find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	rm -rf .ruff_cache *.egg-info
