# Closed ≠ Fixed

How often was a MyLA311 service request marked "Closed" actually fixed, and did the Mar 28, 2025
relaunch change what "closed" means? Public CC0 data from data.lacity.org, DuckDB + dbt, a FastAPI
API with a governed Claude agent, and Next.js on Vercel. Portfolio project by Skye Jackel-Marken.

Full brief (local only, gitignored): `docs/BRIEF.md`. Decisions: `docs/DECISIONS.md`. Data quirks:
`docs/DATA_NOTES.md`.

## How we work
- **Phase gates (brief §8).** Finish one phase, stop with a checkpoint (what was built, key numbers, surprises, decisions needed), and wait for "go". Current phase: **3, taxonomy and metrics**.
- **Log as you go.** Every non-obvious choice goes in `docs/DECISIONS.md` (date, options, why). Every data quirk goes in `docs/DATA_NOTES.md`, with its source query.
- **No invented numbers.** Prose numbers come from `findings/findings.json` (`make findings`), which stores each number with its query; `findings/MEMO.md` is rendered from it.
- **Check current docs** for fast-moving tools: Anthropic SDK, dbt-duckdb, DuckDB (now **2.x**), Socrata, hosts.
- **Commits:** small conventional commits on a phase branch, with `make check` passing first. One PR per phase, merged on "go".
- **Secrets** live in `.env` (gitignored; template in `.env.example`).
- **Money:** ask before anything costing more than a few dollars. Hosting must be $0.
- **The repo is public.** Never commit raw data, addresses or keys; fixtures must be scrubbed.

## Commands
- `make setup` (uv sync + git hooks) · `make check` (lint + tests) · `make fmt`
- `make discover` · `make schema-check` · `make pin` · `make ingest-sample`
- `make ingest` (full pulls → `data/raw/{id}/full.parquet` + manifests) · `make refresh` (deltas for both current datasets) · `make profile` (→ `docs/PROFILE.md`)
- `make build` (dbt build on the full data → `data/warehouse.duckdb`, ~25 s) · `make serving` (→ `data/serving.duckdb`) · `make docs` · `make docs-site` (public docs from fixtures → `site/`)
- `make findings` (rebuilds serving, then → `findings/findings.json` + `MEMO.md`) · `make label` (Claude labels new resolution codes → `ai/labels/review.csv`; needs the key in `.env`, spend-capped) · `make label-finalize` (reviewed sheet → `dbt/seeds/resolution_code_map.csv`)
- CLI: `uv run python -m ingest --help`. dbt directly: `cd dbt && uv run dbt ...` (defaults point at `../data`)

## Conventions
- **Python:** 3.12 via uv, as a virtual project with no packaging. CLIs are Typer apps run as `python -m <pkg>`.
- **Raw layer:** Parquet, all VARCHAR, Socrata *API field names* (never display names). Types are cast in dbt staging.
- **Era** is the system of record (which dataset a row came from), never inferred from dates.
- **Tests are offline;** mark live-API tests `@pytest.mark.live`. `make test` includes a real `dbt build` on synthetic fixtures (`tests/fixtures/synthetic_raw.py`, ~8 s): add a fixture row for each new edge case.
- **dbt** (1.12 + dbt-duckdb, not dbt v2): schemas `staging` → `intermediate` → `marts` (+ `seeds`).
  - Reviewed decisions live in seeds, not SQL.
  - E2 parameters and `code_map_final` are vars in `dbt/dbt_project.yml`.
  - DuckDB-only SQL goes in `macros/portability.sql` or at the raw-source edge; marts stay Snowflake-portable.
  - Marts store additive counts; rates come from `metrics.yml` (Phase 3).
- **Metrics:** every rate is defined once in `metrics.yml` and compiled by `api/metrics.py` (structured filters, bound parameters). Findings, the UI and the agent all go through it; never hand-write a rate's SQL elsewhere.
- **Code labels:** the AI proposes, a person reviews. `resolution_code_map.csv` changes only through `make label-finalize`, which records `label_source`.
- **Serving:** `api/serving.py` is the allowlist. Never add address, coordinate, ZIP, ID or crew columns (the build fails if you try).
- **Makefile** must work with GNU Make 3.81.
- **DuckDB 2.x:** implicit aliases that are keywords fail (`... AS month` works, `... month` doesn't),
  and relations have no `fetchone()` (use `con.execute(...).fetchone()` or `rel.fetchall()`).

## Data traps (details in docs/DATA_NOTES.md)
- Every dataset is a saved filter on a private parent table. The filter SoQL is pinned in `ingest/schemas/`; filter drift = population drift.
- Bulk CSV export headers are display names, and current datasets reuse legacy display names ("UpdatedDate" = `systemmodstamp`, "Owner" = `department_name__c`).
- The 2025 Cases filter ends 2025-12-31 12:59:59, so Dec 31 afternoon cases are in neither dataset.
- Legacy year filters use inclusive BETWEEN, so rows at exactly Jan 1 00:00:00 can sit in two years. Dedupe `srnumber`.
- The 2025 Cases dataset still changes (cases created in 2025 keep closing), so both current datasets refresh incrementally. Reconcile against the live count after each pull or refresh, never the dataset page.
- About 2,200 current-era cases geocode outside LA; staging nulls them. CD 0 and NC 0 mean "none". `assigned_to` is crew codes: staging only.
- Timestamps are floating local Pacific time. 2015–2019 have minute precision (2020 mixed); legacy
  streetlight closes in 2017–2021 are often date-only (midnight), hence ~14K negative durations.
- Current status "Reported" = the 311 record ends at intake (a handoff). Homeless Encampment, Report a
  Sidewalk Problem, Private Property Violation and Report Water Wasting are 100% Reported. Their codes
  ("C-Report has been received") acknowledge intake, so the status decides: outcome `handed_off`.
- Legacy requests still open at the cutover never close in the legacy data (31% of streetlights in the
  last year). Compare closure speed as "closed within N days" with full follow-up, never as a median
  of closed requests.
- Re-reports mostly measure place-level recurrence: always read them against the before-filing placebo.
- Information-Only cases are contacts, not service requests (instantly "Closed", code "C-Closed").
- "Driver Self Report(ed)" = crews logging their own work: 15% of legacy rows, 57% of legacy graffiti,
  and back in current graffiti from 2026. Closed by construction; excluded from cross-era comparisons.
- The bulky / illegal-dumping boundary moved at the cutover: crosswalk them as one category.
- `action_taken__c` is a call-center action, not a resolution. `service_date__c` is a schedule, not proof of service.
- Map resolution codes on the full string; prefixes collide ("RC-Contractor Serviced" vs "RC-Unable to Locate Address").
- `locator_sr_council_district` holds the member's *name*. "neigborhood" is misspelled in source fields.
- Dataset-page row counts are stale caches; count rows yourself.
