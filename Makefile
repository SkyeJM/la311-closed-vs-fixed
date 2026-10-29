# Closed ≠ Fixed: common tasks. `make help` lists them. Works with GNU Make 3.81 (macOS default).

UV ?= uv
PY := $(UV) run python
PHASE0_SAMPLES := ms7h-a45h b7dx-7gc3 h73f-gn57 73a2-6ar5 2cy6-i7zn

.DEFAULT_GOAL := help
# dbt reads these; absolute paths so it works from dbt/ (where dbt keeps target/ and logs/).
DBT_ENV := LA311_RAW_ROOT=$(CURDIR)/data/raw LA311_WAREHOUSE=$(CURDIR)/data/warehouse.duckdb
DBT := cd dbt && $(DBT_ENV) $(UV) run dbt
SITE_BUILD := $(CURDIR)/build/docs-site

.PHONY: help setup lint fmt test check discover schema-check pin ingest-sample ingest refresh \
	profile build docs serving docs-site label label-finalize findings eval serve ask \
	suggested deploy

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install Python and dbt deps, and git hooks
	$(UV) sync
	cd dbt && $(UV) run dbt deps
	$(UV) run pre-commit install

lint: ## Ruff lint and format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Auto-fix lint and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Offline tests, incl. a dbt build on synthetic fixtures (never calls the live API)
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

build: ## dbt build on the full data: seeds, models, tests -> data/warehouse.duckdb
	$(DBT) build

docs: ## dbt docs for the full build -> dbt/target/static_index.html (local; has local paths)
	$(DBT) docs generate --static

serving: ## Export marts + slim fact to data/serving.duckdb (no addresses or coordinates)
	$(PY) -m api.serving

docs-site: ## Public dbt docs built from synthetic fixtures (what CI publishes) -> site/
	rm -rf $(SITE_BUILD) site
	$(PY) -m tests.fixtures.synthetic_raw $(SITE_BUILD)/raw
	# The fixtures plant an unmapped resolution code on purpose, so it may only warn here.
	cd dbt && LA311_RAW_ROOT=$(SITE_BUILD)/raw LA311_WAREHOUSE=$(SITE_BUILD)/warehouse.duckdb \
		$(UV) run dbt build --quiet --vars '{code_map_final: false}' \
		--target-path $(SITE_BUILD)/target --log-path $(SITE_BUILD)/logs
	cd dbt && LA311_RAW_ROOT=$(SITE_BUILD)/raw LA311_WAREHOUSE=$(SITE_BUILD)/warehouse.duckdb \
		$(UV) run dbt docs generate --static --target-path $(SITE_BUILD)/target \
		--log-path $(SITE_BUILD)/logs
	mkdir -p site && cp $(SITE_BUILD)/target/static_index.html site/index.html

label: ## Label new resolution codes with Claude, then write ai/labels/review.csv (needs .env key)
	$(PY) -m ai.label_codes context
	$(PY) -m ai.label_codes run
	$(PY) -m ai.label_codes review

label-finalize: ## Reviewed ai/labels/review.csv -> dbt/seeds/resolution_code_map.csv + agreement
	$(PY) -m ai.label_codes finalize

findings: serving ## Q1-Q5 numbers + E2 evidence -> findings/findings.json and findings/MEMO.md
	$(PY) -m findings

eval: ## Golden-set eval for one model: make eval MODEL=claude-haiku-5-5 (spends credit)
	$(PY) -m evals.run --model $(or $(MODEL),claude-sonnet-5-5) $(if $(MAX_USD),--max-usd $(MAX_USD))
	$(PY) -m evals.report

serve: ## Run the API locally with reload: http://127.0.0.1:8000/api/docs
	$(UV) run uvicorn api.app:app --reload

ask: ## Ask the agent one question in the terminal: make ask Q="..." [MODEL=...] (spends credit)
	$(PY) -m ai.agent "$(Q)" $(if $(MODEL),--model $(MODEL)) --trace

suggested: ## Rebuild cached answers to the suggested questions (spends credit; default model)
	$(PY) -m api.suggested build $(if $(MODEL),--model $(MODEL))

deploy:
	@echo "'make $@' arrives in Phase 5 (brief section 8)." && exit 1
