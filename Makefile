# Closed ≠ Fixed: common tasks. `make help` lists them. Works with GNU Make 3.81 (macOS default).

UV ?= uv
PY := $(UV) run python
PHASE0_SAMPLES := ms7h-a45h b7dx-7gc3 h73f-gn57 73a2-6ar5 2cy6-i7zn

.DEFAULT_GOAL := help
.PHONY: help setup lint fmt test check discover schema-check pin ingest-sample ingest refresh \
	profile build findings eval serve deploy

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install Python deps and git hooks
	$(UV) sync
	$(UV) run pre-commit install

lint: ## Ruff lint and format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Auto-fix lint and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Offline test suite (never calls the live API)
	$(UV) run pytest

check: lint test ## Lint + tests (run before every commit)

discover: ## Flag 311 datasets on the portal that sources.yml doesn't know about
	$(PY) -m ingest discover

schema-check: ## Fail if any dataset's columns or saved filter drifted from its pin
	$(PY) -m ingest schema-check --all

pin: ## Re-pin every schema from live metadata (only after reviewing a drift)
	$(PY) -m ingest pin --all

ingest-sample: ## Pull ~10K-row random-cluster samples for the Phase 0 datasets
	$(PY) -m ingest sample $(addprefix --source ,$(PHASE0_SAMPLES)) --n 10000

ingest: ## Full pull of every dataset via the bulk export (slow: ~17M rows)
	$(PY) -m ingest pull --all

refresh: ## Incremental refresh of the current-year dataset (rows modified since the watermark)
	$(PY) -m ingest refresh

profile: ## Regenerate docs/PROFILE.md from the raw pulls
	$(PY) -m ingest profile

build findings eval serve deploy:
	@echo "'make $@' arrives in a later phase (brief section 8)." && exit 1
