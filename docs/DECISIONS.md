# Decisions

One entry per non-obvious choice: date, decision, options considered, why. Grouped by phase.

## Phase 0: setup and spikes

### 2026-10-23 · The repo is public from day one
- **Options:** private until Phase 6 (recommended because it's reversible), public now, local only.
- **Chosen:** public now (Skye's call).
- **Consequences:**
  - Raw data and samples are gitignored.
  - A pre-commit hook blocks files over 500 KB and anything that looks like an API key.
  - CI fixtures (Phase 2) will have address text removed and coordinates coarsened. Phase 2 went further: the fixtures are fully synthetic (see "CI builds dbt on synthetic fixtures").
  - Commits use a repo-local identity with Skye's GitHub noreply address, so no personal email lands in public history.

### 2026-10-23 · uv-managed virtual project, no packaging
- **Options:** an installable package with console scripts; a virtual project run with `python -m`.
- **Chosen:** the virtual project, run as `uv run python -m ingest ...` behind Makefile targets.
- **Why:** nothing here is a library, so a build backend would be a moving part with no payoff. The Makefile is the interface.

### 2026-10-23 · Raw layer is all-VARCHAR Parquet with Socrata API field names
- **Options:**
  - let DuckDB infer types at ingest;
  - cast at ingest from a schema;
  - keep strings as delivered and cast once, in dbt staging.
- **Chosen:** keep strings, cast in staging.
- **Why:**
  - The raw layer stays a faithful copy: leading zeros in case numbers survive, and type inference can't guess differently from file to file.
  - All parsing logic lives in one reviewable place.
  - We use API field names because the bulk-export headers are display names, and the current datasets reuse legacy display names for different fields (`docs/DATA_NOTES.md`).

### 2026-10-23 · Schema pins include each dataset's saved filter, and drift fails loudly
- **Options:** hash the columns only; hash the columns plus the saved filter.
- **Chosen:** pin the columns (field, type, display name) and the whitespace-normalized saved-filter SoQL in `ingest/schemas/`.
  - `make schema-check` and every pull fail on any difference.
  - `make pin` accepts a change after review.
- **Why:** every dataset is a saved filter, so the filter *is* the population. A City edit, such as adding a request type or fixing the Dec 31 cutoff, would silently shift every rate.

### 2026-10-23 · Phase 0 samples use proportional random clusters, not ID patterns
- **Options:**
  - the first N rows of each month by row id (v1);
  - ID-suffix systematic sampling;
  - minute-of-hour sampling;
  - random-offset clusters.
- **Chosen:** random-offset clusters.
  - Rows are allocated to months in proportion to volume.
  - Each month is split into equal strata, with one run of 100 consecutive rows at a seeded random offset per stratum.
  - Rows repeated by overlapping runs are dropped.
- **Why the alternatives failed:**
  - Row ids follow creation order, so v1 returned only day 1 of each month for the 2026 dataset.
  - Suffix sampling is uniform for current case numbers but not for legacy SR numbers: "ends in 37" returned 0 rows for Sep 2015 and 0.08% of Mar 2024.
  - Minute-of-hour sampling fails on 2015, whose timestamps have only minute precision.
- **Limitation:** clusters make fine-grained distributions (hour of day) lumpy. Samples are for field checks and quick looks only; Phase 1 profiles the full data.

### 2026-10-23 · Exclude `d7h2-83jy` (legacy streetlight view with resolution codes)
- **Options:** use it as legacy E1 evidence for streetlights; exclude it; ask the City first.
- **Chosen:** excluded (Skye, 2026-10-23). It's listed under `ignored` in `sources.yml`, and no rows were pulled. Legacy outcomes therefore stay E2 (behavioral) only.
- **Why:**
  - The view is public, marked official and listed in the catalog, but its own description says "This copy is private and for internal City use only."
  - Building findings on data the publisher calls internal would be hard to defend in an interview, even though anyone can reach it.
  - If the City confirms it's meant to be public, streetlights would get explicit outcomes in both eras.

### 2026-10-23 · Pre-commit runs ruff through `uv run`
- **Why:** one ruff version (from `uv.lock`) for the editor, CI and hooks, with no second pin to drift. Large-file, private-key and API-key guards are added because the repo is public.

### 2026-10-23 · Phase branches, one PR per phase
- **Why:** each PR carries that phase's checkpoint and merges on Skye's "go", so git history mirrors the phase gates.

### 2026-10-23 · MIT license for code; the City's data stays CC0
- **Why:** MIT is the conventional choice for portfolio code. Easy to change.

### 2026-10-23 · Hosting: Vercel Hobby, API as a Python service beside Next.js (confirmed by Skye at the Phase 1 gate)
- **Constraint:** $0/month, no card, no paid tiers (Skye).
- **Options researched 2026-10-23** (details and sources in `spikes/hosting/README.md`):
  - Vercel Hobby
  - Google Cloud Run
  - Render free
  - Fly.io
  - Railway
  - MotherDuck Lite (compute elsewhere)
  - Hugging Face Spaces
  - Koyeb
  - Modal
- **Recommendation:**
  - Vercel Hobby, running FastAPI in the same project as the Next.js app (same origin, so no CORS).
  - `serving.duckdb` is bundled at build time from a GitHub Release asset.
- **Why:**
  - It's the only option that is $0 with no card on file and *can't* bill: over-limit Hobby projects pause instead of charging.
  - Cloud Run is the sturdier runtime but needs a billing account and has no hard spending cap.
  - Render and Railway free tiers sleep (about a minute to wake, or 502s) and have 512 MB of RAM.
  - Hugging Face Docker Spaces now require PRO.
  - Fly.io has no free tier.
- **Size check** (synthetic 18M-row slim fact table, DuckDB 2.0, 1 thread, 1 GB memory limit):
  - 182 MB in the compact layout (date plus hours to close), 320 MB with full timestamps.
  - Dashboard-style queries take 8–47 ms on first run; a full-scan yearly median takes about 0.5 s.
  - Peak memory stays at or below 278 MB.
  - Script: `spikes/hosting/bench_duckdb.py`.
- **Cost estimate:** $0/month within Hobby's monthly limits: 4 active-CPU hours, 360 GB-hours of memory, 1M invocations.
  - Conservative capacity is about 6,400 100-second `/ask` streams a month at 2 GB, because memory GB-hours run out first.
  - That's far above portfolio traffic, and the guardrails cap `/ask` well below it.
- **Risks the test deploy must settle:**
  - Hobby's Python bundle limit: 500 MB documented; whether the 5 GB "Large Functions" beta applies to Hobby is unconfirmed.
  - Cold start with a 200–300 MB data file.
  - SSE through Vercel Services, which is in beta.
  - Hitting a Hobby limit pauses the project for up to 30 days.
- **Guardrails:**
  - A Vercel WAF rate-limit rule per IP.
  - Upstash Redis free tier (via the Marketplace) for hourly and daily counters.
  - An Anthropic Console workspace spend limit as the hard backstop.
- **Fallbacks:** MotherDuck Lite for the data if the bundle won't fit; Cloud Run if Skye adds a card.
- **Test deploy, 2026-10-23** (throwaway project on Skye's Hobby account; details in `spikes/hosting/README.md`):
  - The real bundle limit is **225 MB including dependencies**, not the documented 500 MB: an 18M-row synthetic file was rejected at 357 MB.
  - A 112 MB file deployed in 34 s. Queries ran in about 18 ms warm (160 ms on first touch).
  - A 110-second SSE stream arrived unbuffered with no cutoff.
  - Files generated in the build step are bundled.
  - A true scale-from-zero cold start wasn't captured (instances stayed warm); re-measure in Phase 5. The throwaway project was deleted.
- **Consequence for Phase 2:** serving holds the marts plus a slim *current-era* fact table; legacy years are served as aggregated marts. Built in Phase 2 at 75 MB (see "Serving export" below).

## Phase 1: ingest and profile

### 2026-10-23 · Full pulls use the bulk export; values are stored exactly as delivered
- **Options:** the bulk export (`rows.csv?accessType=DOWNLOAD`, one streamed file per dataset); paging the SODA row API (`$limit`/`$offset`).
- **Chosen:** the bulk export, as the brief recommends.
- **How:**
  - The export's headers are display names, so they're mapped to API field names through the pin. Any unknown or missing column fails the pull.
  - Values stay as delivered, including timestamps like `12/31/2015 09:59:00 PM`. A `_pull_method` column tells staging which format a row uses.
  - Any line DuckDB can't parse fails the pull instead of being skipped.
  - Every pull is reconciled against a live `count(*)`.
- **Why:**
  - One streamed request per dataset; 2015's 237,305 rows took 28 s.
  - Reformatting at ingest would make raw differ from the source. Keeping parsing in staging puts it in one reviewable place.
  - Failing on bad lines is the difference between a loud error and a silently smaller denominator.

### 2026-10-23 · Incremental refresh: `systemmodstamp` watermark with a 3-day overlap
- **Options:** Socrata's `:updated_at` (portal ingest time); `systemmodstamp` (the source system's modification time); full re-pulls only.
- **Chosen:**
  - `systemmodstamp`, as the brief specifies, re-reading 3 days before the watermark.
  - Each refresh writes an append-only `delta_<UTC>.parquet`. Staging keeps the latest version of each case.
  - A full pull supersedes all deltas.
- **Why:**
  - Modifications can reach the portal out of order, and the overlap makes late arrivals harmless because duplicates are resolved downstream.
  - Deltas can't see deleted or re-filtered cases, so a periodic full pull is still the source of truth. Weekly is the plan for the stretch-goal refresh job.

### 2026-10-23 · Profile proposals: a mechanical rule where the data decides, a reviewed list where judgment does
- **Terminal statuses** use a rule: a status is terminal if at least 99% of its rows have a closed date.
- **Non-service types** are an explicit list in `ingest/profile.py`, with a reason per type, shown next to the evidence.
  - **Why:** Information-Only cases carry the generic code "C-Closed", so any rule based on code labels would miss the most obvious contact type.
- **Crosswalk:** the brief's guesses, checked by volume either side of the cutover and by department.

### 2026-10-23 · DuckDB lockdown order for read-only serving (spike finding, used in Phase 4)
- **Finding:** with DuckDB 2.0, putting `enable_external_access=false` in the connect config makes `temp_directory` impossible to set.
- **Working sequence:** connect read-only with `temp_directory`, then `SET enable_external_access = false`, then `SET lock_configuration = true`.
- **Tested locally:** this blocks re-enabling external access, reading local files, raising the memory limit, and writing tables. It's the layer under the `run_sql` SQL parser.

### 2026-10-23 · Phase 1 sign-off
- **What was asked:** the Phase 1 checkpoint asked for answers to five decisions along with "go", and recommended yes on each.
- **Skye's reply:** "go", with no changes, taken as accepting the recommendations:
  1. **Non-service types:** Information-Only, Program Research and current-era Other, plus Feedback in both eras. Legacy "Other" stays a service type that isn't crosswalked: without codes it can't be characterized.
  2. **Terminal statuses:** legacy Closed, Cancelled, Referred Out; current Closed, Reported, Cancelled, Closed Ext-Referred.
  3. **Crosswalk:** six categories, with crew self-reports excluded from every cross-era comparison.
  5. **Hosting:** Vercel Hobby.
- **Deferred:** decision 4 (whether intake-only "Reported" cases count against the fix rate) moves to Phase 3 with the taxonomy.
- **Where they live:** dbt seeds (`non_service_types`, `status_map`, `request_type_crosswalk`, `unified_categories`), so each is a reviewable data file rather than SQL.

## Phase 2: dbt models

### 2026-10-23 · dbt-core 1.12 with dbt-duckdb 1.11, on DuckDB 2.0
- **Options:** dbt v2 (the new Rust engine, now the default `pip install dbt`); dbt-core 1.x with dbt-duckdb; downgrading DuckDB to 1.5 for safety.
- **Chosen:** dbt-core 1.12.6, dbt-duckdb 1.11.0 and DuckDB 2.0.0, with dbt_utils 1.4.1.
- **Why:**
  - The brief names dbt-core + dbt-duckdb.
  - dbt's docs list DuckDB as "CLI only" in v2, the default v2 build isn't open source (the Apache build is `dbt-oss`), and dbt-duckdb has an open issue about hanging under the new engine.
  - dbt says v1.x "remains fully supported".
  - DuckDB 2.0 shipped on 2026-10-21. A smoke test passed seeds, tables, views, generic and singular tests, unit tests and static docs, and dbt-duckdb's nightly CI already covers 2.0.
- **Upgrade path:** the project avoids deprecated syntax (`data_tests:`, `arguments:` for test inputs), so a later move to v2 should be mechanical.

### 2026-10-23 · One dbt source per Socrata dataset, kept in sync with `sources.yml`
- **Options:** one glob over every raw file, with era read from the manifests; one source per era; one source per dataset.
- **Chosen:** one source table per dataset (`legacy_2015` … `current_2026`), each linked to its portal page in the docs. Staging unions them from two dbt vars (`legacy_datasets`, `current_datasets`).
- **Why:**
  - It's the conventional dbt layout, and lineage shows every published dataset.
  - `tests/test_dbt_project.py` fails if the sources or the vars disagree with `sources.yml`.
  - The manifest reconciliation fails if a pulled dataset isn't staged, so "Cases 2027" can't be half-added.
- **DuckDB-specific reads stay at the source edge:** `read_parquet` locations live under `config` (not `meta`, so local paths stay out of the docs), and `UNION ALL BY NAME` absorbs the five legacy views that lack a column.

### 2026-10-23 · Staging keeps no addresses and cleans locations conservatively
- **Address fields:** never selected, because nothing needs them. Coordinates cover every spatial join (brief section 10: data minimization).
- **Coordinates:** points outside a box around the city (lat 33.6–34.4, lon -118.8 to -118.0) are nulled and flagged, so they can't create false spatial matches. About 2,200 current-era cases geocode to other continents.
- **Codes:** council district 0 and NC code 0 mean "none" and become null. Only 5-digit ZIPs are kept (9-digit ZIP+4 is truncated).
- **Dropped downstream:** `assigned_to` (about 150 crew and yard codes; the brief rules out claims about crews), `cd_member` (a person's name) and police area (names in one era, numbers in the other).
- **Deduplication:** within a dataset, staging keeps the latest version of each case across the full pull and its deltas. It does *not* dedupe across datasets: Phase 1 found no shared IDs, so a unique test fails loudly if that changes, instead of silently dropping rows.

### 2026-10-23 · Reconciliation is against the live count after the latest pull or refresh
- **Options:** compare staging with the rows on disk; with the manifest's file counts; with the portal's own count.
- **Chosen:** both checks.
  - `assert_staging_reconciles_to_manifest` compares each dataset's staged rows with the live count taken right after its latest full pull or refresh. Ingest now records that count after every refresh.
  - `assert_raw_files_match_manifest` checks every file's row count against what ingest recorded.
- **Why:** the first is the end-to-end claim ("what dbt built is what the portal had"), and the second localizes a failure to one file.
- **First result:** all 13 datasets match exactly (16,009,032 rows on 2026-10-23).

### 2026-10-23 · Outcome precedence: the code, then the status, never a guess
- **Rule (`int_request_outcomes`):**
  - A mapped resolution code decides (E1). The most specific map row wins: code + department + type, then code + department, then code + type, then the code alone. A dbt unit test pins this order.
  - A terminal case with no code takes its status's outcome from `status_map`, which is the only option for legacy rows.
  - A code the map doesn't know leaves the outcome null (`unmapped_code`), not a default.
- **Why:** a default would hide new codes. Null keeps them visible, and `assert_all_resolution_codes_mapped` lists them.
- **Phase 2 map is provisional:** `resolution_code_map.csv` holds only the brief's first-guess examples (53 codes, `label_source = brief_first_guess`).
  - The mapping test *warns* (118 unmapped codes today, 118,291 terminal cases).
  - Phase 3 replaces the map with the AI-labeled, reviewed one and sets `code_map_final: true`, which turns the warning into a build failure. That's the brief's alerting.
- **Seeds beyond the brief's three:**
  - `status_map`: terminal flag plus the outcome a status implies.
  - `closure_outcomes`: the taxonomy, with counts_as_fixed and an outcome group.
  - `unified_categories`: comparability per category.
  - Each turns a signed-off decision into reviewable data.

### 2026-10-23 · Re-reports: a square spatial hash plus exact distance, not H3 (parameters provisional)
- **Options:**
  - H3 cells with `h3_grid_disk` (a DuckDB community extension; native in Snowflake);
  - DuckDB spatial's R-tree join;
  - square grid cells with a 3×3 equi-join and an exact great-circle filter.
- **Chosen:** the square grid.
  - Cells are 55 m (the 50 m radius plus 10%, which absorbs the east-west scale change across the city). A point's neighbors within 50 m always lie in its own cell or the 8 around it.
  - Time is split into 30-day buckets, so a window spans at most two of them.
- **Why:**
  - It's exact.
  - It needs no extension download (CI and the build stay offline-safe).
  - It's plain SQL in both DuckDB and Snowflake. H3's neighbor search needs DuckDB-only `unnest` syntax, while its single-cell function is the same in both, so H3 stays available for the stretch-goal map.
- **Verified:** a brute-force search (bounding box plus distance, no grid) on 3,000 random closed requests matched the model on every one.
- **Definition details:**
  - Requests from either era count, so a legacy request closed before the cutover can be re-reported in the new system for crosswalked categories.
  - Crew self-reports and duplicates never count as re-reports.
  - A window counts only if it can be observed in full: it must end before the data does, and, for legacy-only types, before the cutover.
- **Provisional:** 50 m and 30 days come from the brief. Phase 3 checks them against a placebo baseline, because pickups recur at the same buildings so often that re-reports there measure recurrence more than failure.

### 2026-10-23 · Durations exist only for terminal requests; marts store counts, not rates
- **Durations:** about 1% of legacy Open rows (and some Forward rows) carry a closed date although the request is open. `hours_to_close` and `is_instant_close` are therefore defined only when the status is terminal.
- **Marts:**
  - They hold additive counts and sums, so any rate can be computed at any roll-up: rates of rates would be wrong.
  - Percentiles can't be re-aggregated, so they are precomputed only at the grain where they're used (month × category × era in `mart_cutover_comparison`). The slim serving fact handles other current-era grains.
- **Rates are defined once, in `metrics.yml` (Phase 3)**, for the marts and the AI layer.

### 2026-10-23 · Serving export: an allowlist module, checked for locating fields on every build
- **Chosen:** `api/serving.py` copies an explicit list of tables from the warehouse into `data/serving.duckdb`, along with dbt's docs as table and column comments.
  - The tables: dims, marts, and `fct_current_requests` (current-era service requests without IDs, coordinates, ZIPs or crew fields).
  - The build fails if any forbidden column (address, lat, lon, zip, request IDs, assigned_to, cd_member) would reach serving.
- **Why:**
  - One module is the allowlist for both the deploy and Phase 4's `run_sql` tool (marked per table). The row-level slim fact is reachable only through governed metric queries, never raw SQL.
  - Carrying comments over lets the agent's `describe_table` read definitions straight from the database.
- **Size:** 75.0 MB (2,778,200 slim-fact rows plus marts), half of the 150 MB budget set under Vercel's 225 MB bundle limit.

### 2026-10-23 · CI builds dbt on synthetic fixtures, never on real rows
- **Chosen:** `tests/fixtures/synthetic_raw.py` invents a few rows per dataset, shaped by the real pins and written through the real ingest code (bulk-export CSV → `export_to_parquet`, refresh pages → `soda_csvs_to_parquet`, plus manifests).
  - Every row is placed to exercise one edge case: a delta update, a re-report pair, a duplicate that must not count, the cutover overlap, a date-only close, out-of-area coordinates, an unmapped code.
  - `tests/test_dbt_fixtures.py` runs `dbt build` on them inside pytest (about 8 s) and asserts each case.
- **Why:**
  - The brief requires CI to build dbt without the live API.
  - Invented rows can't leak an address, while scrubbed real rows still could.
  - Checking specific outcomes catches logic errors that green tests alone would miss.
- **Docs site:** `make docs-site` builds the dbt docs from the same fixtures. The static page embeds the absolute paths of whichever machine built it, so only the CI build is meant for publishing.
