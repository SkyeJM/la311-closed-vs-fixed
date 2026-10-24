# Decisions

One entry per non-obvious choice: date, decision, options considered, why. Grouped by phase.

## Phase 0: setup and spikes

### 2026-10-23 · The repo is public from day one
- **Options:** private until Phase 6 (recommended because it's reversible), public now, local only.
- **Chosen:** public now (Skye's call).
- **Consequences:**
  - Raw data and samples are gitignored.
  - A pre-commit hook blocks files over 500 KB and anything that looks like an API key.
  - CI fixtures (Phase 2) will have address text removed and coordinates coarsened.
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

### 2026-10-23 · Hosting: Vercel Hobby, API as a Python service beside Next.js (test deploy passed; pending Skye's confirmation)
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
- **Consequence for Phase 2 (proposed):** serving holds the marts plus a slim *current-era* fact table (~4M rows); legacy years are served as aggregated marts.

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
