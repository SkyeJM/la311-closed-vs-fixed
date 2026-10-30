# Interview prep

The twelve questions most likely to come up, with draft answers grounded in
[`DECISIONS.md`](DECISIONS.md). Numbers are generated from `findings/findings.json` and the eval
summary. Make the answers yours: say them out loud and cut what you wouldn't say.

A note on how this was built: Claude Code was the main development tool. Be ready to say what
you decided and what you delegated. The decision log records each call, including the ones you
made at each phase gate (the fix-rate base, the code review, the default model, publishing the
data, the eval budget).

---

**1. Give me the two-minute version.**

LA relaunched its 311 system on Mar 28, 2025, and the new system publishes a resolution code on every
case, so public data can now say how a request ended, not just that it closed. I built a pipeline
over the City's MyLA311 open data since 2015, mapped every resolution code to an outcome, and
compared "closed" with "verified fixed" on the same requests. Of requests filed Mar 2025 to
Jul 2026, 87.8% were marked closed but 62.1% have a code saying the work was
done: a 25.7-point gap, concentrated in a few codes. It's a live site with a dashboard and an AI
analyst that shows its queries and is evaluated on a 43-question test set.

**2. Why isn't the closure rate enough?**

Closed is a status. A request closes when a crew fixes it, when there was nothing to fix, when
it's handed to another agency, or with a generic "Closed" code that says nothing. The closure
rate counts all of those the same way. "Verified fixed" means the resolution code says the work
was done or had already been done. It's still the City's own record, not an inspection, so I
call it verified by the record, and I say that on the methodology page.

**3. How did you define the base, and why?**

The closure rate and the fix rate have to share a denominator, or the gap between them means
nothing. I left out duplicates and information-only closes (120,549), which have no
outcome of their own, and intake handoffs (156,910), which end in this system and
are worked in another one. Open requests stay in, because an unresolved request is part of the
picture. With one base, the gap is simply the share of requests marked closed without a code
saying the problem was fixed. I proposed the base at a checkpoint and confirmed it before
building the metrics.

**4. How did you compare the old and new systems fairly?**

Four rules. Compare only categories that exist in both systems, through a reviewed crosswalk.
Leave out crews logging their own work, which closes by construction. Use equal
12-month periods and skip the five months when both systems ran. And measure speed
as "closed within N days among requests followed that long," because requests still open when
the old system stopped never close in its data: a median of closed requests would flatter it. On
that basis, graffiti closed within 30 days went from 74% to
65%. I describe that change; I don't attribute it.

**5. How did you build the taxonomy? Why let an AI label codes?**

There are 171 codes, and labeling them by hand is slow and inconsistent. Claude Haiku labeled
each code twice from its context, and Sonnet decided the 19 codes where the runs
disagreed or were unsure. That cost $0.19. Then a person reviewed every label. The AI
matched the reviewed map on 94.7% of codes, 99.7% of requests. The review wasn't
a rubber stamp: it changed 9 codes, and it set rules, for example that
enforcement steps like "notice issued" don't count as fixed. One honest caveat: the overrides were
proposed with Claude Code's help and approved by me, so the agreement figure measures the
labeling models against a reviewed map, not against an independent coder.

**6. What surprised you in the data?**

Three things. Requests open in the old system when it stopped never close in its data, which
would have made the relaunch look worse with a naive median. Re-reports measure place more than
failure: a new request near the same spot followed 68% of "item not out"
closes, against 71% in the month before the request was even filed. And some
bureaus close almost everything with a generic code, so their fix rate reads near zero because
nothing is recorded, not necessarily because nothing was done.

**7. How does the AI analyst work, and why build the loop yourself?**

It's a manual tool loop over the Claude API. Tools: governed metrics first, then read-only SQL
over aggregate tables, a schema browser, a code explainer and a chart tool that can only draw
rows a query returned. I wrote the loop myself instead of using the SDK's tool runner because
every step needs a guard: stream the trace to the browser, check the spend cap before each call,
stop at 8 steps, and check the answer before showing it. The answer is a structured
output because Sonnet and Opus 5.5 don't allow a forced final tool call, and structured output
always parses.

**8. How do you know its numbers are right?**

Three layers. It can only get numbers from tools, and the metric tool compiles governed
definitions into parameterized SQL. Before an answer is shown, code checks that every number in
it appears in a tool result at the precision it's written. If one doesn't, the answer goes back
once with the problem. And a 43-question golden set, with expected answers computed
from the data at run time, measures it per model: Sonnet got 100% of the numeric
questions right and passed every check on 100% of questions.

**9. Which model would you ship, and why?**

Sonnet. It matched Opus on accuracy at $0.0123 a question against $0.0337, and it was
faster: a median 5.7 s against 10.2 s. Haiku is about 10 times
cheaper but scored lower (93% of all checks), and it once answered a Spanish question in
English. The live site runs Sonnet, and the model is one environment variable, so the call is
easy to revisit.

**10. What makes it safe to put on the public internet?**

The API key stays on the server. Each IP gets 10 live questions an hour, with a
firewall rule in front. Spend is checked against a $1.00 daily cap before every model call,
and there's a kill switch. The SQL tool parses queries with sqlglot, allows one SELECT over
allowlisted aggregate tables, and runs on a read-only DuckDB connection with file access off and
a time limit. On privacy: the deployed data has no addresses, coordinates or IDs (the build
fails if one sneaks in), the AI can't read row-level tables directly, and traces store a hashed
IP and nothing else that identifies a person.

**11. What went wrong, and what did you learn?**

A few things, each caught by a check. The metric compiler applied a monthly date range to a
quarterly table and silently shifted the window; I found it while adding rankings, fixed the rule
and added a test. Every chart labeled months one early because Vega reads a bare date as UTC
midnight, which is still the previous day in Los Angeles; screenshots caught it before deploy.
And in production the agent re-ran queries it already had: one answer used all
8 steps. Showing it a step counter cut cost per answer 25%, and I re-ran
the full evals so the published numbers match what's deployed.

**12. What would you do next, or with internal data?**

Join closures to work orders and closure photos to check how often each code is right, and add
the closure survey the Controller recommended in 2021, so "verified fixed" means what residents
saw. With more time: mix-adjusted comparisons across districts, long-run trends back to 2015 on
the shared categories, and a weekly refresh with a short note on what changed.
