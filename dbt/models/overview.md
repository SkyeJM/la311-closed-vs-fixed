{% docs __overview__ %}
# Closed ≠ Fixed: the warehouse

How often was a MyLA311 service request marked "Closed" actually fixed, and did the March 28, 2025
relaunch change what "closed" means? Source: the 13 MyLA311 datasets on
[data.lacity.org](https://data.lacity.org) (CC0). Code and decisions:
[github.com/SkyeJM/la311-closed-vs-fixed](https://github.com/SkyeJM/la311-closed-vs-fixed).

**Layers**

- **staging**: one model per era, typed from the raw strings. Address fields are never selected.
- **intermediate**: both eras in one shape, with closure outcomes, the re-report signal, and the
  Apr–Aug 2025 overlap check.
- **marts**: the fact table, dimensions, and count marts. Only the marts and dims, plus a slim
  current-era fact table with no locating fields, reach the deployed app.

**Evidence levels.** E1 is an explicit resolution code (new system only). E2 is a behavioral proxy
from status, timing or re-reports (both eras).

**Reading this site.** It is built in CI from synthetic fixtures, never from the real rows:
models, columns, tests and lineage are the real project, but no data from it appears here.

**Outcome rules.** A request's outcome comes from its resolution code when the reviewed map knows
it, otherwise from its status; intake handoffs (status Reported) are `handed_off` whatever their
code. Rates are defined once, in `metrics.yml`, and computed from the count marts.

**E2 parameters.** Instant close = marked closed within 1 minute. Re-report = a same-category
request within 50 m in the 30 days after closing, read against the same search in the 30 days
before filing (the placebo). Both are justified in `docs/DECISIONS.md`.
{% enddocs %}
