# Resume bullets

Two versions, every number generated from `findings/findings.json` and the eval summary. Pick
three or four per resume; each stands alone.

**Project line:** Closed ≠ Fixed — how often a "Closed" LA 311 request was actually fixed ·
la311-closed-vs-fixed.vercel.app · Python, dbt, DuckDB, FastAPI, Next.js, Claude API

## Analyst / product ops

- Designed a closed-vs-verified-fixed metric for LA's MyLA311, showing {closure_rate} of requests
  marked closed but {fix_rate} verified fixed ({gap}-point gap, {base} requests)
- Built a dbt + DuckDB warehouse unifying {requests_legacy} legacy and {requests_current} new-system
  311 requests, with tests, pinned source schemas and row counts reconciled to the source
- Created an outcome taxonomy ({classes} classes) for {codes} resolution codes with AI-proposed,
  human-reviewed labels ({agree_codes} AI–human agreement); an unmapped code fails the build
- Defined {metrics} governed metrics once in YAML, compiled to SQL and shared by the dashboard,
  the findings memo and an AI analyst, so definitions can't drift
- Compared the 2025 relaunch like for like (matched {compare_months}-month windows, "closed
  within N days"): graffiti closed within 30 days {graffiti_30d_before} → {graffiti_30d_after}
- Traced the gap to a few codes: five carry {top5_share} of {unverified_total} closed-unverified
  requests; "item not out" ran {nc_low}–{nc_high} across neighborhood councils
- Wrote stakeholder-ready definitions and limitations for every metric on a public methodology
  page, with each chart linked to its definition and every number to its query

## AI-forward / solutions / APM

- Built Ask 311, a Claude tool-use agent (FastAPI, SSE) that answers only via {metrics} governed
  metrics and sandboxed SQL, shows its query trace and verifies every number in code
- Ran multi-model evals on a {eval_questions}-question golden set with data-computed answers:
  Sonnet {sonnet_numeric} numeric accuracy at {sonnet_cost}/question; Opus matched at
  {opus_cost_ratio}× the cost
- Diagnosed repeated tool calls from production traces and cut the agent's cost per answer
  {sonnet_cost_drop} (median latency {sonnet_round2_p50} s → {sonnet_p50} s), verified by a full
  eval re-run
- Designed human-in-the-loop AI labeling of {codes} resolution codes (Haiku twice, Sonnet on
  disagreement) for {label_cost}, {agree_codes} agreement with human review
- Shipped guardrails for a public AI demo: per-IP rate limits, a {daily_cap}/day spend cap and
  kill switch, a sqlglot SQL sandbox on read-only DuckDB, hashed-IP traces
- Deployed Next.js + FastAPI as one Vercel project on the free tier, with an accessible,
  mobile-first UI and a pinned, checksummed data release
