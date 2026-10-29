# Closed ≠ Fixed: findings memo (v1)

Data through 2026-10-28. Generated from `findings/findings.json` (commit b31ccf9); every number below is in that file with the query that produced it. Descriptive only: no claim here says why a number is what it is.

## Headline

In the new MyLA311 system (requests filed Mar 2025 to Jul 2026, each followed at least 60 days), **87.8% of requests were marked closed, but only 62.1% carry a resolution code saying the work was done: a 25.7-point gap.** The base (2,064,328 requests) leaves out 120,549 duplicates and information-only closes and 156,910 intake handoffs, whose own record can't show a fix. The City's closure rate over every service request in those months is 81.5%.

## What the data shows

1. **Outcome mix (Q1).** Of requests that ended: work done 58%, not found 15%, closed without saying how 7%, handed off at intake 7%, duplicate 5%, cancelled 4%. Bulky and dumped item pickups are 61% of the base, so they set the overall rates (pickup gap: 25.7 points).
2. **Where the gap is (Q2).** The gap is concentrated in a few codes: five codes carry 94% of the 530,965 closed-but-unverified requests, and "QC-Item Not Out" alone carries 60%. The largest count is Bulky & dumped item pickups in council district 2 (26,560); the highest rate among groups of 500+ is Obstructions (BSS - IED) in district 7, 99.2 points.
3. **Bulky items (Q3).** "Item not out" closed 24% of pickups (300,512). Across 98 neighborhood councils with 1,000+ closed pickups it ranged from 11% to 40%; across weekdays only from 23% to 27%. A new pickup request within 50 m and 30 days followed 68% of item-not-out closes and 66% of completed pickups, against 71% in the 30 days before an item-not-out request was filed: repeat requests follow the place more than the outcome.
4. **The cutover (Q4).** Comparing the year before the relaunch with the year after the overlap (crosswalked categories, crew self-reports out): graffiti closed within 30 days went from 74% to 65% and cancellations from 23% to 15%; streetlights closed within 30 days went from 16% to 12%; pickups closed within 7 days from 90% to 86%; dead animals closed within 7 days from 99% to 98%. Instant closes were at most 0.3% of closes in any category and period.
5. **Proxy validation (Q5).** Among resident-reported closes in the new system, those closed within a minute were verifiably fixed 67% of the time, against 71% for the rest. Re-report rates after not-fixed closes, minus those after fixed ones: bulky & dumped item pickups +2.5 pts, service not complete +1.9 pts, dead animal +11.1 pts. Yet the after-close rate exceeded the before-filing baseline in only 10 of 132 category, era and parameter settings. The proxies carry some signal within a category; they can't stand in for legacy fix rates.

## Method notes

- Instant close = marked closed within 1 minute; re-report = a same-category request within 50 m and 30 days after closing, compared with the same search before filing (placebo).
- Legacy requests still open at the cutover never close in the legacy data, so the "before" year ends 30 days before the relaunch and time to close is compared as "closed within N days", not as a median of closed requests.
- Rates are computed from counts in the served marts through metrics.yml, the same path the dashboard and the Ask agent use.
