# Two-minute demo

Story → one Ask question with the trace open → the methodology's eval table. Open
[la311-closed-vs-fixed.vercel.app](https://la311-closed-vs-fixed.vercel.app) before you start.
Numbers below are the live site's, generated from `findings/findings.json` and the eval summary.

**0:00 — The question (Story page, top).**
"When LA's 311 system marks a request Closed, was the problem fixed? Since the
{launch} relaunch, every case carries a resolution code, so the public data can finally say. Of
requests filed {window_from} to {window_to}, {closure_rate} were marked closed, but only
{fix_rate} have a code saying the work was done: a {gap}-point gap."

**0:20 — The chart (scroll down).**
"The gap has held month after month since the relaunch. The old system recorded no codes, so
there's no line before it, and I say so instead of inventing one."

**0:35 — Where the gap is (the three cards).**
"It's concentrated. One code, 'Item Not Out' on bulky-item pickups, carries
{item_not_out_gap_share} of it, and its rate runs from {nc_low} to {nc_high} depending on the
neighborhood council."

**0:50 — Ask (open Ask, click 'Which council districts have the biggest gap between closed and
fixed?').**
"This is the AI analyst. It can only answer through governed metrics or read-only SQL over
aggregate tables. Here's its trace: the metric it called, the SQL behind it, the rows it got
back. Click a key number and it opens the exact query. Code checks every number in the answer
against the tool results before you see it, so it can't state a number it didn't query."

**1:25 — Methodology (scroll to 'How accurate is Ask 311?').**
"I measure it, too: {eval_questions} test questions, including ones it must decline and
{eval_spanish} in Spanish, with expected answers computed from the data each run. Sonnet got
{sonnet_numeric} of the numbers right at {sonnet_cost} a question; Opus matched it at
{opus_cost_ratio} times the cost, so the site runs Sonnet. Just above: every resolution code,
labeled by Claude and reviewed by me; the AI matched my review on {agree_codes} of codes."

**1:50 — Close.**
"It's all public data, the queries are visible, and nothing claims a cause. What I'd do next is
join closures to work orders and run the closure survey the Controller recommended, so
'verified fixed' means what residents saw, not just what the record says."
