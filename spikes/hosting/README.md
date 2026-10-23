# Hosting spike (Phase 0)

**Question:** what is the cheapest reliable way to serve a small FastAPI app that reads a
read-only DuckDB file and streams `/ask` answers over SSE? The constraint is $0/month with no card
(Skye, 2026-10-23). The decision and its reasoning are in `docs/DECISIONS.md`.

## 1. Size and speed of the serving file (measured locally)

`uv run python spikes/hosting/bench_duckdb.py --rows 18000000` builds a synthetic slim fact table
at roughly full scale (~14M legacy + ~4M current rows; no real data). It then times queries in
fresh read-only processes with 1 thread and a 1 GB memory limit (DuckDB 2.0.0, Apple Silicon).

| Variant | File | Dashboard queries (first run) | Full-scan yearly median | Peak RSS |
|---|---|---|---|---|
| compact (date + hours to close) | 182 MB | 8–46 ms | 0.47 s | 240 MB |
| full timestamps | 320 MB | 10–47 ms | 0.51 s | 278 MB |

Opening the file takes about 15 ms. Synthetic data compresses differently from real data and a
cloud vCPU is slower than this laptop, so treat these numbers as a size *estimate* and a latency
*lower bound*. Both variants fit under a ~400 MB data budget.

## 2. Platforms (desk research 2026-10-23; D = documented, C = community, ? = unverified)

| Platform | $0 / card? | RAM · stream limit | Cold start | Verdict |
|---|---|---|---|---|
| **Vercel Hobby** (Python runtime, Services beta) | $0; no card; over limit = paused, never billed (D) | 2 GB / 1 vCPU · 300 s; Python streaming (D) | median Python ~1.3–2.8 s (vendor); large bundle unmeasured | **Recommended** |
| Google Cloud Run | $0 inside free tier, but billing account + card; no hard cap | up to 32 GiB · 3,600 s; SSE (D) | image size doesn't affect start (D) | Fallback if a card is OK |
| Render free | $0, no card | 512 MB / 0.1 CPU | sleeps after 15 min, ~1 min wake (D) | Fails the cold-start bar |
| Railway | $1/mo credit; sleeps | 0.5 GB | first request delayed or 502 (D) | Too small |
| Fly.io | no free tier for new orgs (D) | | | Not $0 |
| MotherDuck Lite | $0 data (10 GB); still needs compute | | | Fallback for data only |
| HF Spaces (Docker) | Docker Spaces need PRO, $9/mo (D, C) | | | Not $0 |
| Koyeb / Modal | card hold (Koyeb); 150 s HTTP limit (Modal) | | | Skip |

**Vercel details that matter:**
- Hobby limits: 4 active-CPU hours, 360 GB-hours of memory and 1M invocations per month.
- Read-only filesystem, with `/tmp` at 500 MB, so set DuckDB `temp_directory` to `/tmp`.
- Python bundle limit is 500 MB. Hobby eligibility for the 5 GB "Large Functions" beta is unconfirmed.
- Ship data by downloading a GitHub Release asset in the build step: no LFS bandwidth limits, and no Vercel Blob caps.
- Guardrails: a WAF rate-limit rule, Upstash Redis free tier for counters, and an Anthropic Console spend limit as the backstop.

## 3. Free test deploy (needs Skye)
1. Create a Vercel Hobby account (no card) and log in. Updating the CLI first is recommended (installed 54.0.0; current 65.x): `npm i -g vercel@latest`, then `vercel login`.
2. Then I deploy a throwaway project: FastAPI with `/health`, a DuckDB query over a ~300 MB synthetic file, and a 110-second SSE stream.
3. I measure bundle acceptance, cold start and streaming, then delete the project.

## Sources (checked 2026-10-23)
- **Vercel:**
  - https://vercel.com/docs/functions/limitations
  - https://vercel.com/docs/limits
  - https://vercel.com/docs/plans/hobby
  - https://vercel.com/docs/functions/runtimes/python
  - https://vercel.com/docs/services
  - https://vercel.com/docs/fluid-compute
  - https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
  - https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size
  - https://community.vercel.com/t/large-functions-beta-not-applied-python-bundle-limited-to-500-mb-on-hobby/50605
- **Google:**
  - https://docs.cloud.google.com/free/docs/free-cloud-features
  - https://docs.cloud.google.com/run/docs/configuring/request-timeout
- **Other platforms:**
  - https://render.com/docs/free
  - https://docs.fly.io/about/pricing
  - https://docs.railway.com/reference/pricing/plans
  - https://motherduck.com/product/pricing/
  - https://huggingface.co/docs/hub/spaces-overview
  - https://modal.com/docs/guide/webhook-timeouts
- **Anthropic spend limits:** https://platform.claude.com/docs/en/api/rate-limits
