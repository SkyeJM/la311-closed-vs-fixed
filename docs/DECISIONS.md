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

## Phase 3: taxonomy and metrics

### 2026-10-28 · Phase 2 sign-off
- **Skye's reply:** "go, Pages enabled, there isn't a .env file in the project yet".
- **Done on that basis:**
  - PR #3 merged; Phase 3 runs on `phase-3-taxonomy`.
  - `.env` created from `.env.example` (gitignored, mode 600) for Skye to paste the API key into. Code only ever checks that the key is set; it never prints it.
  - The docs workflow was run on main, but its deploy step got a 404: the repo still reports `has_pages: false`. My attempt to switch Pages on through the API was blocked again as a public-surface change, so Skye needs to pick **GitHub Actions** under Settings → Pages → Source. The workflow stays manual until then, so a merge can't fail on it.
- **Decision 4 (intake handoffs):** Skye didn't object to the standing recommendation, so it's taken as accepted, as at the Phase 1 gate (next entry). Skye can still override it.

### 2026-10-28 · Intake handoffs are their own outcome, outside the fix-rate base (decision 4)
- **Options:**
  - count status Reported as closed-unspecified (the Phase 2 placeholder);
  - count it as referred out (not fixed);
  - give it its own outcome and leave it out of the fix-rate denominator.
- **Chosen:** the third option. `closure_outcome = handed_off` (outcome group `handed_off`, counts_as_fixed `not_observable`). It's set from the status even when the case has a code (`status_map.status_decides`).
- **Why:**
  - These cases end at intake and are worked in another department's system (LSD, LADBS, DPW, LADWP). 311 can't show whether they were fixed.
  - Counting them as unfixed would charge the 311 record for work it never tracks. Counting them as fixed would credit work nobody can see.
  - The codes they carry acknowledge intake rather than describe an outcome. "C-Report has been received" is on 175,529 of the 190,670 Reported cases, "C-Closed" on 13,007, and "C-Report has been referred out." on 1,905. So the status has to win over the code.
- **Visible, not hidden:** handoffs are a slice of the outcome mix and are counted in `findings.json` (`headline.excluded_from_base`).

### 2026-10-28 · One base for the fix rate and the closure rate, so the gap is a share of requests
- **The brief's formulas:**
  - closure_rate = closed ÷ created;
  - verified_fix_rate = fixed ÷ terminal;
  - gap = closure_rate − verified_fix_rate.
- **Problem:** the two rates have different denominators, so their difference isn't a share of anything. It can even go negative when many requests are still open.
- **Chosen:**
  - **The fix-rate base** is every service request except those whose own record can't show a fix: duplicates and information-only closes (outcome group `neutral`) and intake handoffs. Open requests stay in.
  - `verified_fix_rate` and the closure rate are both computed on that base. The gap (`closed_fixed_gap_pp`) then equals the share of requests that were marked closed without a code saying the problem was fixed.
  - `closure_rate` itself stays the official view (all service requests) as context. findings.json reports both.
- **Why open requests stay in:** dropping them would make the gap depend on how fast cases close. The headline uses requests filed at least 60 days before the data ends (`headline.window`), so few are still open.
- **Stated as the brief asks:** `closed_not_fixed_share` doesn't count cancellations in its numerator. Cancellations carry status Cancelled, which isn't "closed", and the 0.03% of closed cases with a cancellation code count only in the denominator.
- **"Closed" is the status:** Closed and Closed Ext-Referred, plus legacy Closed and Referred Out (`status_map.is_closed`). Legacy Referred Out is 7,819 rows.

### 2026-10-28 · Instant close = marked closed within 1 minute
- **Evidence** (`findings.json → e2_parameters.instant_close`):
  - In the new system, 225,923 terminal service requests end within 10 seconds of filing. Nearly all are intake handoffs, duplicates and cancellations, not closes.
  - Requests actually marked *Closed* within a minute are rare: about 1,100 resident-reported ones in 19 months (`current_seconds_to_close`). Among comparable closes it's a fraction of a percent in both eras.
  - The threshold barely matters: the share of comparable closes within 1, 2, 5 or 10 minutes is recorded per era.
- **Chosen:** 1 minute, applied to requests whose status says closed.
  - A minute is the coarsest precision in the data (2015–2019 timestamps are whole minutes).
  - It catches anything closed before a crew could have been sent.
  - Cancellations and handoffs end differently and have their own measures.
- **Changed from Phase 2:** 5 minutes, and any terminal status.

### 2026-10-28 · Re-reports get a placebo: the same search before the request was filed
- **Problem:** Phase 2 found that half or more of closed pickup, graffiti and encampment requests get a new nearby request within 30 days. A re-report signal is only meaningful against what that place sees anyway.
- **Options:**
  - a spatial placebo (the same search around a point shifted a few hundred meters);
  - the same place a year later;
  - the same place in the 30 days before the request was filed.
- **Chosen:** the before-filing window. It's the same place and season, has no secular drift, and is cheap: the same equi-join, with time mirrored.
  - Eligibility now requires *both* windows to be fully observable, so the after-close rate and its placebo describe the same requests.
  - Only requests whose status says closed are eligible (a re-report follows a close).
- **Result:**
  - At 50 m and 30 days, after-close rates sit below before-filing rates in every crosswalked category with real volume, in both eras. The exceptions are tiny: 17 closed new-system encampment cases, and legacy water waste at about zero.
  - Across a 3×4 grid of radii (25/50/100 m) and windows (7–60 days), the after-close rate exceeded the baseline in 10 of 132 settings, 9 of them for legacy water waste (`findings.json → e2_parameters.rereport`).
  - So 50 m and 30 days stay. The conclusion doesn't hinge on them, and re-reports are read as recurrence unless they beat the placebo.
- **Caveat:** before a streetlight request, the window often holds other reports of the same outage, so "before" isn't pure background there. Comparisons are descriptive.

### 2026-10-28 · The cutover is compared on equal, fully followed periods
- **Data trap found:** legacy requests still open when the old system was retired never close in the legacy data (see DATA_NOTES). In the year before the cutover, 31% of legacy streetlight requests are still Open.
  - A median over closed requests silently drops exactly the slow cases.
  - Closed shares near the cutover are cut short.
- **Chosen** (`mart_cutover_periods`):
  - "Before" is the 12 months ending 30 days before the cutover (legacy), so every request had 30 days to close in its own system. "After" is the 12 months after the Apr–Aug 2025 overlap (new system). Whole years balance the seasons, and the overlap's legacy tail and the new system's first months stay out.
  - Time to close is compared as **closed within 7 / 30 days**. Medians and p90s are kept, over closed requests only, with the caveat.
  - Monthly series carry `has_full_followup` and null those shares where follow-up is incomplete.

### 2026-10-28 · metrics.yml plus a small compiler, not the dbt Semantic Layer
- **Options:**
  - dbt's semantic layer (MetricFlow);
  - SQL views per metric;
  - a YAML catalog compiled to SQL by a small module (`api/metrics.py`).
- **Chosen:** the YAML catalog and compiler.
- **Why:**
  - The deployed API runs on Vercel's 225 MB bundle. Shipping dbt-core plus MetricFlow to compile queries at request time would crowd out the data.
  - The metrics are all ratios of additive counts, which a 300-line compiler covers.
  - The same definitions drive findings.json, the dashboard and the agent's `query_metric`, so there's one place to change a definition.
- **How it stays honest:**
  - Each metric lists its sources, most general first. The compiler picks the first that can answer.
  - A source that holds only part of the population (new system only, pickups only) is refused unless the request asks for that part, so it can't answer silently for a subset.
  - Filter values are bound parameters.
  - Tests check every metric against the fact table and that every eligible source agrees.

### 2026-10-28 · Findings run on the served marts through the metrics
- **Chosen:** `make findings` computes Q1–Q5 on `data/serving.duckdb` through metrics.yml, the same path the UI and the agent will use. Only the E2 parameter evidence, which needs coordinates, runs on the warehouse.
  - Every number is stored with its query (SQL, parameters and source) under an id.
  - `findings/MEMO.md` is rendered from the JSON. Its interpretive sentences appear only when the numbers support them.
- **Status:** `provisional` until the reviewed code map lands and `code_map_final` is true.

### 2026-10-28 · AI code labeling: Haiku twice, Sonnet on doubt, a person reviews everything
- **Shape (brief section 6B):**
  - `ai/label_codes.py` sends each code's context (aggregates only) to `claude-haiku-5-5` twice with structured output.
  - It escalates to `claude-sonnet-5-5` once when the runs disagree, either is low-confidence, a label contradicts its own counts_as_fixed, or a run fails.
  - Nothing reaches the dbt seed until `finalize` reads the reviewed sheet.
- **Choices within it:**
  - **Context overrides come back in the same call** (`context_overrides`, naming departments or types from the input). That avoids a second round per code; an override naming anything not in the context counts as a failed run.
  - **counts_as_fixed uses the seed's vocabulary** (yes/no/neutral/not_a_service/unknown) instead of the brief's yes/no/unknown, so a contradiction with the class can be detected.
  - **The prompt defines the classes in general terms and never lists the brief's example codes.** Those examples still shaped the class definitions, so AI agreement with the brief's first guesses isn't an independent test. The number that matters is agreement with Skye's review.
  - **The proposal lives in `ai/labels/`, not `dbt/seeds/`,** because dbt loads every CSV in seeds/.
  - **The review sheet puts first** the rows that differ from the brief, low-confidence and failed rows, then escalations and overrides, then volume. `finalize` records `ai_accepted`, `ai_overridden` or `human`, and writes the agreement report (`ai/labels/agreement.json`), which findings.json picks up.
- **API details** (checked against platform.claude.com docs on 2026-10-28):
  - Structured outputs via `output_config.format` (GA, no beta header), with the schema from `anthropic.transform_schema`.
  - Adaptive thinking. The SDK (2.3) has no temperature parameter for these models, so the two runs differ by ordinary sampling.
  - The system prompt (about 4K tokens, above Haiku 5.5's 512-token minimum) is cached with a breakpoint. The first request goes alone so the rest can read the cache.
- **Cost:**
  - A `--max-usd` spend cap of $3 stops new requests.
  - The dry run estimates about $1.60 for 171 codes.
  - `ai/pricing.py` holds the price table (Haiku 5.5 $0.10/$0.50 per MTok, Sonnet 5.5 $2/$10) and is reused for the Phase 4 daily cap.

### 2026-10-28 · Seeds are always rebuilt
- **Problem:** adding columns to `status_map` failed the build. dbt reloads a seed into its existing table, so the new columns didn't match.
- **Chosen:** `+full_refresh: true` for seeds. They're tiny, and a stale table can't hide a reviewed change.

### 2026-10-28 · Skye's answers at the first Phase 3 checkpoint
- **Fix-rate base:** confirmed as built (duplicates, information-only closes and handoffs out; open requests in).
- **GitHub Pages:** on, with GitHub Actions as the source. The dbt docs are published at https://skyejm.github.io/la311-closed-vs-fixed/, and the workflow now runs on every push to main that touches the dbt project, the fixtures, the Makefile or the workflow itself.
- **Anthropic key:** added to `.env`, but the first labeling call came back "Your credit balance is too low to access the Anthropic API". The account has no prepaid API credits yet. Nothing was spent.
  - The labeler now stops at the first account-level refusal (authentication, permission or credit) instead of logging every call as a failure and writing an empty proposal.
  - Buying credits is Skye's decision. API usage is prepaid, and credits are non-refundable and expire a year after purchase.

### 2026-10-28 · The reviewed resolution-code map; new codes now fail the build
- **Labeling run:**
  - 171 codes and 361 calls, with no failures, for $0.19 (the dry run estimated $1.60). The cached system prompt (7,338 tokens) made the second Haiku call per code cheap.
  - Haiku's two runs agreed on 156 codes. 19 went to Sonnet: 15 where the runs disagreed, 3 low-confidence, 1 where the context overrides differed. On 8 of those, Sonnet chose a class neither Haiku run had.
  - Numbers: `ai/labels/run_summary.json`, also in `findings.json → ai_labeling.labeling_run`.
- **Review** (Skye, "go with your recommendations"). I (Claude Code) flagged the rows needing judgment and proposed changes, and Skye approved them all:
  - **The one disagreement with the brief:** NAT-No Action Taken stays *cancelled* (the AI's label; the brief guessed *unable*). The code gives no reason, and every case has status Cancelled.
  - **Consistency between related codes:**
    - INO-Item Not Out → *not_found* (as QC-Item Not Out).
    - A-Request Completed → *fixed_work_done*.
    - CNACV → *unable* (as its twin CNABD).
    - NAR-No Action Recommended (LADOT reviews that decline a request) → *unable*, while NAR-No Action Required stays *not_found*.
  - **A rule for enforcement steps:** "complaint accepted", "notice issued" and "criminal filing" codes are *closed_unspecified*. The department acted, but nothing shows the problem stopped. Codes that name the outcome ("complied", driver disciplined) stay *fixed_work_done*.
  - **One split by request type:** NCPP-Not at Curb / On Private Property is *not_found* for pickups and missed collections (like "item not out"). A reviewer-written row makes it *referred_out_of_scope* for Dead Animal Removal, where private property is the owner's job.
- **Result:** `dbt/seeds/resolution_code_map.csv` has 176 rows (171 codes plus 5 context overrides).
  - By label_source: 166 ai_accepted, 9 ai_overridden, 1 human.
  - AI–human agreement: 94.7% of codes and 99.7% of service cases (`ai/labels/agreement.json`).
  - The AI matched 52 of the brief's 53 first guesses. That isn't independent, because the brief's examples shaped the class definitions.
- **Caveat for the interview story:** the overrides were proposed by the coding assistant and approved by Skye. The agreement figure measures the labeling models (Haiku/Sonnet) against that reviewed map.
- **`code_map_final: true`:** an unmapped code now fails `make build`.
  - The synthetic fixtures still plant one, build with the flag off, and a test checks that turning it on fails the build on that code.
  - New codes go through `make label` (spend-capped) → review → `make label-finalize`.
- **Effect on findings:** findings v1 is now `final`. The headline gap is 25.7 points on the reviewed map, against 30.0 on the provisional one, mostly because "RC-Request Completed" (streetlights) and the scooter codes are now credited as fixed.

## Phase 4: API, agent and evals

### 2026-10-29 · Phase 3 sign-off
- Skye said "go" and added $10 of API credit for the Phase 4 evals (about $14.80 in the account at the start of the phase). PR #4 merged; this phase is on `phase-4-api-agent`.

### 2026-10-29 · A manual tool loop, not the SDK's tool runner
- **Options:** the SDK's beta tool runner, which runs tools and loops for you, or a manual loop over `messages.create` (brief section 6A asks for the choice to be logged).
- **Chosen: manual** (`ai/agent/loop.py`), because every step has to do things the runner hides:
  - stream each tool call and result to the UI as it happens (`/api/ask` is SSE);
  - check the daily spend cap before each model call and the step cap after it;
  - switch tools off on the last allowed step, so the loop always ends in an answer;
  - check the answer before accepting it, and send it back once with the problems.
- **Cost of the choice:** about 150 lines of loop code, tested offline with a scripted client.

### 2026-10-29 · The answer contract is a structured output, not a submit_answer tool
- **Options:** a final `submit_answer` tool, or JSON output with `output_config.format`. Both are allowed by the brief.
- **Why structured output:**
  - Claude Opus 5.5 and Sonnet 5.5 reject forced tool use (`tool_choice` any or tool returns a 400; docs checked 2026-10-29). A submit tool couldn't be forced, and a model that ended with plain text would need a retry.
  - With `output_config.format`, the model's final message always parses. Tool calls stay free during the loop, and strict tool schemas keep their inputs valid.
- **One field added to the brief's shape:** `answer_type` (answered, partial, declined). Declines and partial answers are then explicit, and the evals can check them without parsing prose. `evidence_level` also takes "none" for volumes, definitions and declines.

### 2026-10-29 · "Never state a number that didn't come from a tool" is checked in code
- **Runtime:** before an answer is accepted, `ai/agent/answer.py` checks:
  - every cited query_id exists;
  - every key number is in the rows of the query it cites (a percent must be on the 0-100 scale);
  - every number in the prose matches some tool value at the precision it was written with (`ai/agent/numbers.py`), allowing for a percentage, hours shown as days, or a thousands or millions multiplier.
- Years, small bare counts and numbers in the question or the prompt's definitions (50 m, 30 days) are exempt.
- An answer that fails goes back to the model once with the list of problems. If it still fails, it is delivered with the problems attached for the UI to flag, and the evals count it as a failure.
- **Why both the runtime check and the evals:** the brief asks the evals to check this programmatically. Checking at runtime as well means a public answer can't quietly carry an invented number.

### 2026-10-29 · Tools: governed first, SQL as a guarded escape hatch
- **`query_metric`** compiles metrics.yml through `api/metrics.py`.
  - Filters arrive as a list of {dimension, values}. Strict tool schemas require `additionalProperties: false`, which rules out a free-form dict.
  - Values are typed per column and checked against the column's real values. An unknown value returns the closest valid ones ("graffiti" → Graffiti).
  - Results add `value_pct` for shares and both component rates for differences (the gap query gives closed %, fixed % and the gap at once), so the model never has to compute them.
- **`run_sql`** takes one SELECT checked on sqlglot's parse tree (`ai/agent/sqlguard.py`). It may read only the aggregate tables `api/serving.py` marks `sql_tool`.
  - Table functions (`read_csv`, `query()`, which could otherwise get around the allowlist, `glob` ...) and the row-level fact table are rejected. The fact table is reachable only through governed metrics, which always aggregate (brief section 10: no row-level output).
  - What runs is sqlglot's rendering of the tree it checked.
  - Underneath, the connection is read-only with file access off and the configuration locked (`api/db.py`, in the order the Phase 0 spike found). Each query has a 10-second interrupt and a 100-row cap for the model.
- **`make_chart`** takes a Vega-Lite spec without data. The API attaches the cited query's rows, rejects specs that bring their own data, URLs or links, and validates the result against the Vega-Lite 6.5 JSON schema (vendored, gzipped; react-vega 8 renders Vega-Lite 6). A chart can show only numbers a tool returned.
- **`list_metrics`, `describe_table`, `explain_resolution_code`** read the catalog, the dbt docs carried into serving, and the reviewed code map with its rationale and label source.

### 2026-10-29 · The system prompt is generated, and holds no data numbers
- `ai/agent/prompt.py` fills `ai/agent/prompts/system.md` from metrics.yml, the outcome seed and the served data: dates, crosswalk, cutover periods and category list. It follows a refresh without hand edits.
- It holds definitions and rules but no counts or rates, so the model can quote a number only from a tool. A test enforces this.
- About 4,300 tokens, plus about 1,500 for the tools, cached together. Every question after the first reads them at a tenth of the input price or less.
- **Default dates:** when the user gives none, current-era rates use the findings window (requests filed Mar 2025 through the last month with 60 days of follow-up), and before-and-after questions use the cutover periods. Answers then agree with the published findings.

### 2026-10-29 · One question at a time; follow-ups are standalone questions
- **Options:** a chat with history, or independent questions.
- **Chosen: independent questions.** The brief's `follow_ups` become clickable standalone questions ("in plain words, understandable without this conversation").
- **Why:**
  - Every answer can be evaluated, cached and traced on its own.
  - A public endpoint takes no client-supplied history, which would be both a cost lever and a prompt-injection surface.
- **Trade-off:** "what about district 7?" doesn't resolve against an earlier answer. The UI can offer the agent's own follow-ups instead.

### 2026-10-29 · Effort medium for every model, set through ASK_EFFORT
- Default effort differs by model: medium for Opus 5.5 and Haiku 5.5, high for Sonnet 5.5. The docs recommend medium for agentic and latency-sensitive work. The evals compare all three models at medium, so only the model changes.
- **Not CLAUDE_EFFORT:** Claude Code sets that variable in its own shell (to max). The first smoke test inherited it, and Haiku thought for about 30 s per step until it hit the token limit. The project variable is `ASK_EFFORT`.
- **Other caps:** 8 steps per question (tools off on the 8th), 8,000 output tokens per step, $0.75 per question, and 600 characters per question.

### 2026-10-29 · Guardrails for the public /api/ask
- **What refuses a question, in order, before the stream opens** (plain HTTP errors):
  1. Cached answers to the suggested questions are served first, at no cost.
  2. The kill switch (`ASK_ENABLED=false`) returns 503.
  3. A spent daily cap (`DAILY_SPEND_CAP_USD`, also checked before every model call) returns 503.
  4. The per-IP limit (10 live questions an hour) returns 429 with Retry-After.
- **Privacy:**
  - IPs are hashed with HMAC and a secret salt, and never stored.
  - Traces are JSONL, one line per question: tool calls with SQL, the answer check, tokens, cost and latency.
  - Emails, phone numbers and street addresses typed into a question are masked before logging.
- **Counters** live behind a small store interface. The in-memory store is right for one local process. On Vercel, Ask stays off until a shared store (Upstash Redis via the Marketplace, Phase 5) and `IP_HASH_SALT` are configured, so a deploy can't silently run with per-instance limits.
- **Backstops:** a Vercel WAF rate-limit rule and the Anthropic Console workspace spend limit (Phase 5, Skye's settings).
- **The key stays server-side:** only the Python API reads it, and no endpoint returns configuration.

### 2026-10-29 · Evals: expected numbers computed at run time, a cheap judge for the rest
- **Golden set:** `evals/golden.yaml` has 43 questions: 31 numeric, 6 must-qualify, 6 must-decline, 5 in Spanish.
  - Each numeric entry says how to compute its answer: a governed metric request, or SQL for one share no metric defines. `evals/expected.py` computes it from serving.duckdb when the eval runs, so the set stays right after a refresh.
  - The brief's example ("pothole fix rates in 2018 vs 2026") is in: the legacy data has no pothole category and no resolution codes.
- **Checks** (`evals/score.py`):
  - numbers within a tolerance: 0.15 points absolute for percents and points, 0.5% relative for counts, 3% for durations, or the precision the answer wrote, whichever is looser;
  - the governed metric used;
  - evidence level and answer type;
  - no unsupported numbers;
  - required caveats and no causal claims, graded by a judge;
  - the question's language.
- **The judge:** `claude-haiku-5-5` with structured output. It quotes its evidence so Skye can spot-check.
  - In development it marked one English answer as "not English", so language is now a deterministic stopword count.
  - It also failed one caveat on a parenthetical detail, so its prompt now grades substance, not wording.
  - `evals/rescore.py` re-grades a saved run, so judge fixes don't cost new agent runs.
- **Runs:** `make eval MODEL=...` writes `evals/results/{date}_{model}.json` and `.md`. `evals/report.py` builds `SUMMARY.md` and `summary.json` (for the methodology page) from the latest full run per model.

### 2026-10-29 · Metric date ranges are whole months, and never shift on quarterly marts
- **Bug found while adding ranking:** `date_range` was applied to whichever source the compiler picked. On the quarterly district mart, Mar 2025 to Jul 2026 silently became Apr 2025 to Sep 2026.
- **Effect:** findings v1 was unaffected, because Q2 already forced the monthly fact table. The agent would have been affected, since it can't choose a source.
- **Fix:** a date range is now (first month, last month) as month starts. A source answers it only when the range starts and ends on its own grain; otherwise the compiler falls through to a finer source. Tests cover both paths.
- **Also added:** ranking options (`order`, `limit`, `min_count`), so "which district has the largest gap" needs no hand-written SQL.

### 2026-10-29 · Eval results: two rounds, and what round 1 changed
- **Round 1** (agent at d986648; files `evals/results/*_round1.*`):
  - **Numeric:** all three models answered 31 of 31 numeric questions correctly.
  - **All checks:** Haiku 42/43 (answered a Spanish question in English); Sonnet 42/43; Opus 40/43.
  - **Sonnet's miss:** it re-ran one identical query six times until the step cap, then wrote a number it computed itself. The runtime check caught it, but no step was left for a revision.
  - **Opus's misses:**
    - A judge false positive: "counting these would raise the rate" describes the metric, not a cause.
    - One real speculation about why graffiti closures slowed.
    - An evidence label (E1, from `outcome_mix`) that the golden entry hadn't allowed.
- **Changes after round 1:**
  - A repeated identical tool call now points back to its first result instead of running again.
  - The judge separates explaining an observed change, which is causal, from describing how a metric is computed, which isn't.
  - The encampment entry accepts E1.
  - The pilots had already led to two prompt rules: compute uncatalogued shares in run_sql, and never speculate about causes.
- **Round 2 (final; agent and harness at e5471ca)**, 43 questions per model, effort medium (`evals/results/SUMMARY.md`):

  | model | numeric | all checks | Spanish | cost per question | latency p50 / p90 |
  |---|---|---|---|---|---|
  | claude-haiku-5-5 | 30/31 (97%) | 41/43 (95%) | 4/5 | $0.0011 | 6.8 s / 13.4 s |
  | claude-sonnet-5-5 | 31/31 (100%) | 43/43 (100%) | 5/5 | $0.0165 | 8.8 s / 15.8 s |
  | claude-opus-5-5 | 31/31 (100%) | 43/43 (100%) | 5/5 | $0.0365 | 12.3 s / 19.3 s |

  - Haiku's two misses are real:
    - It again answered the same Spanish question in English.
    - It quietly narrowed "graffiti requests" to resident reports, though it said so in the answer.
  - The judge itself cost $0.003 per 43-question run.
- **Caveats on these numbers:**
  - 43 questions is a small set, so a single miss moves a rate by 2 to 3 points.
  - The golden set was written by the same assistant that wrote the agent's prompt. Both follow the brief, but the questions aren't independent of the prompt's vocabulary. Skye's spot-checks of the judge and a few hand-written questions in Phase 5 would strengthen this.
- **Spend:** Phase 4 used about $5.40 of API credit by token count: smoke tests, pilots, a Haiku development run, two full rounds on three models, the judge and the suggested-answer cache.

### 2026-10-29 · Default model: keep claude-sonnet-5-5
- **Options:**
  - Haiku: 15 times cheaper and the fastest, but 41/43, missing the brief's explicit Spanish requirement.
  - Sonnet: 43/43.
  - Opus: 43/43 at 2.2 times Sonnet's cost and about 40% slower.
- **Chosen:** Sonnet, the brief's default, now backed by the evals. Opus adds no measured accuracy here.
- **What it costs:** about $0.017 per live question, so the $1.00 daily cap allows roughly 60 live questions a day. The six suggested questions are served from the cache at no cost.
- **Reversible:** `CLAUDE_MODEL` switches the model without a code change. Haiku is the fallback if traffic outgrows the cap.
