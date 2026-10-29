# Resume bullets

Two versions, every number generated from `findings/findings.json` and the eval summary. Pick
three or four per resume; each stands alone.

**Project line:** Closed ≠ Fixed — how often a "Closed" LA 311 request was actually fixed ·
la311-closed-vs-fixed.vercel.app · Python, dbt, DuckDB, FastAPI, Next.js, Claude API

## Analyst / product ops

- Designed a closed-vs-verified-fixed metric for LA's MyLA311, showing 87.8% of requests
  marked closed but 62.1% verified fixed (25.7-point gap, 2,064,328 requests)
- Built a dbt + DuckDB warehouse unifying 12,314,408 legacy and 2,796,957 new-system
  311 requests, with tests, pinned source schemas and row counts reconciled to the source
- Created an outcome taxonomy (11 classes) for 171 resolution codes with AI-proposed,
  human-reviewed labels (94.7% AI–human agreement); an unmapped code fails the build
- Defined 18 governed metrics once in YAML, compiled to SQL and shared by the dashboard,
  the findings memo and an AI analyst, so definitions can't drift
- Compared the 2025 relaunch like for like (matched 12-month windows, "closed
  within N days"): graffiti closed within 30 days 74% → 65%
- Traced the gap to a few codes: five carry 94% of 530,965 closed-unverified
  requests; "item not out" ran 11%–40% across neighborhood councils
- Wrote stakeholder-ready definitions and limitations for every metric on a public methodology
  page, with each chart linked to its definition and every number to its query

## AI-forward / solutions / APM

- Built Ask 311, a Claude tool-use agent (FastAPI, SSE) that answers only via 18 governed
  metrics and sandboxed SQL, shows its query trace and verifies every number in code
- Ran multi-model evals on a 43-question golden set with data-computed answers:
  Sonnet 100% numeric accuracy at $0.0123/question; Opus matched at
  2.7× the cost
- Diagnosed repeated tool calls from production traces and cut the agent's cost per answer
  25% (median latency 8.8 s → 5.7 s), verified by a full
  eval re-run
- Designed human-in-the-loop AI labeling of 171 resolution codes (Haiku twice, Sonnet on
  disagreement) for $0.19, 94.7% agreement with human review
- Shipped guardrails for a public AI demo: per-IP rate limits, a $1.00/day spend cap and
  kill switch, a sqlglot SQL sandbox on read-only DuckDB, hashed-IP traces
- Deployed Next.js + FastAPI as one Vercel project on the free tier, with an accessible,
  mobile-first UI and a pinned, checksummed data release
