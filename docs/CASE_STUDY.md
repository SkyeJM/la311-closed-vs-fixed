# Case study: Closed ≠ Fixed

*About a five-minute read. Every number here is generated from `findings/findings.json` and the
eval summary; the decisions behind each step are in [`DECISIONS.md`](DECISIONS.md).*

## The problem

Los Angeles runs MyLA311, the service-request system residents use to report graffiti, missed
bulky-item pickups, broken streetlights and dozens of other problems. The City reports how many
requests it closes, and the City Council has asked for quarterly reports on exactly that. But
"closed" is a status, not an outcome: a request can close because a crew fixed the problem,
because nothing was there, because it was handed to another agency, or for no stated reason.

On Mar 28, 2025 the City relaunched MyLA311, and the new system publishes a resolution code on every
case. For the first time, public data says *how* a request ended. That made two questions
answerable:

1. When a request is marked closed, how often does the record say the problem was fixed?
2. Did the relaunch change what "closed" means?

## Approach

**Two systems, one warehouse.** The data comes as 13 public datasets: one per year for
the old system (12,314,408 service requests) and two for the new one
(2,796,957, through Oct 28, 2026). Each is a saved filter on a private City table, so the
pipeline pins every dataset's schema and filter and fails loudly if either drifts. A dbt project
on DuckDB stages, deduplicates and unifies them. Which system a row came from is a fact of the
data, never inferred from its date, because both systems ran side by side from April to August
2025.

**Defining "fixed."** The new system uses 171 resolution codes, from "AR-Request Completed"
to "QC-Item Not Out." Each maps to one of 11 outcome classes (work done, already resolved,
not found, referred out, deferred, unable, cancelled, closed without saying how, and others).
Claude proposed every label from each code's context (departments, request types, volumes,
statuses): Haiku labeled each code twice, and Sonnet decided the 19 codes where the
runs disagreed or were unsure. The whole run cost $0.19. A person then reviewed every
label; the AI matched the reviewed map on 94.7% of codes, covering 99.7% of
requests. The reviewed map lives in a dbt seed, and a code that isn't mapped fails the build.

**One base for both rates.** The headline compares two rates on the same requests. The *fix-rate
base* leaves out duplicates and information-only closes (120,549 requests) and
requests handed off at intake (156,910), whose outcome is recorded in another
system. Open requests stay in. The *closure rate* is the share of the base marked closed; the
*verified fix rate* is the share whose code says the work was done. Their difference, in
percentage points, is the share of requests marked closed without a code saying the problem was
fixed. Every rate is defined once in `metrics.yml` and computed from summed counts, so the site,
the findings and the AI analyst can't disagree about a definition.

**Comparing across the relaunch.** The old system has no resolution codes, so fix rates exist
only after the relaunch. For the categories that exist in both systems, the comparison uses
behavior instead: closed within 7 or 30 days, and cancellations. Requests still open in the old
system when it stopped never close in its data, so a median time to close would flatter the old
system; "closed within N days, among requests that could be followed that long" doesn't. The
comparison sets 12 months before the relaunch against 12 months after
the overlap, and leaves out crews logging their own work, which closes by construction.

**Testing the proxies.** Two cheap signals could stand in for fix rates in the old system: an
*instant close* (within 1 minute of filing) and a *re-report* (a new request
within 50 m and 30 days of a close). The new system's codes can test
them.

**An analyst you can audit.** Ask 311 is a Claude agent that answers questions only through
tools: governed metrics first, and read-only SQL over aggregated tables when no metric fits. It
shows every query, links each key number to the query behind it, and its answer is checked in
code: a number that didn't come from a tool result sends the answer back. A golden set of
43 questions, with expected answers computed from the data when the test runs,
compares three models.

## Findings

- **The gap.** Of requests filed Mar 2025 to Jul 2026, 87.8% were marked closed
  and 62.1% have a code saying the work was done: a 25.7-point gap. Counting every request,
  the City's closure rate is 81.5%.
- **How requests ended.** Work done 58%, not found 15%, closed without
  saying how 7%, handed off at intake 7%.
- **Where the gap is.** It is concentrated: five codes carry 94% of the
  530,965 requests closed without evidence of a fix, and "QC-Item Not Out" alone
  carries 60%. Street-services categories close almost everything with a
  generic code, so their fix rates read near zero because nothing is recorded, not necessarily
  because nothing was done.
- **Bulky items.** "Item not out" closed 24% of pickups
  (300,512 requests), from 11% to 40% across neighborhood
  councils but only 23% to 27% across weekdays. A new pickup request near the
  same spot within 30 days followed 68% of item-not-out closes
  and 66% of completed pickups, against 71% in the
  30 days *before* the request was filed: repeat requests follow the place more than
  the outcome.
- **The relaunch.** Resident-reported graffiti closed within 30 days fell from
  74% to 65%, and cancellations from 23%
  to 15%. Streetlights closed within 30 days went from 16% to
  12%; pickups closed within 7 days from 90% to 86%.
- **The proxies don't hold up.** Instant closes were verifiably fixed 67% of the time,
  against 71% for other closes. After-close re-reports exceeded the before-filing
  baseline in only 10 of 132 category, system and parameter
  settings. Neither signal can stand in for a fix rate before 2025.
- **The AI analyst.** On the golden set, claude-sonnet-5-5 got 100% of numeric
  questions right and passed every check on 100% of questions, at $0.0123 a
  question and a median 5.7 s. claude-opus-5-5 matched it on numbers at
  2.7 times the cost; claude-haiku-5-5 cost 10 times less but
  scored lower (94% of numbers, 93% of all checks). Sonnet runs the live
  site.

## Limitations

- "Verified fixed" means the City's own record says so. No one checked the street, and a code
  can be wrong in either direction.
- The old system recorded no outcome, so there is no fix rate before the relaunch, and the
  proxies that might have filled in don't track fixes.
- Some bureaus close nearly everything with a generic code. Their "gap" measures recording, not
  work.
- Requests handed off at intake, including every homeless-encampment report, leave this data at
  the moment they're filed.
- All of it is descriptive. The data can show what changed and where, not why, and it says
  nothing about any person, crew or contractor.

## Next steps

- **Mix-adjusted geography:** compare districts and neighborhoods after standardizing for the mix
  of request types, so a district isn't ranked low for receiving harder requests.
- **Long-run trends:** the behavioral measures for 2015–2026 on the categories both systems share.
- **Inside the City:** join closures to work orders and closure photos, and run the closure survey
  the Controller recommended in 2021, to measure how often each code is right.
- **A weekly refresh:** the data updates daily; a scheduled build would keep the site and the
  agent current, with a short note on what changed.
