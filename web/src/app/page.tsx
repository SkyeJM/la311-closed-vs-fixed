import Link from "next/link";
import { TrendChart } from "@/components/TrendChart";
import findings from "@/data/findings.json";
import { count, day, month, pct, points } from "@/lib/format";

// Every number on this page is read from findings.json (make findings), which stores each one
// with the query that produced it.
const h = findings.headline;
const q2 = findings.q2_where_the_gap_is;
const q3 = findings.q3_bulky_items;
const q4 = findings.q4_cutover;
const allPickups = q3.by_request_type.find((r) => r.request_type === "All pickups")!;
const itemNotOut = q2.top_codes.find((c) => c.resolution_code === "QC-Item Not Out")!;
const graffiti = q4.categories.find((c) => c.unified_category === "Graffiti")!;
const months = findings.trend.months.filter((m) => m.full_followup);
const ncs = q3.neighborhood_councils;

function HowCalculated({ metric, anchor }: { metric?: string; anchor?: string }) {
  return (
    <Link href={`/methodology#${anchor ?? `metric-${metric}`}`} className="text-sm">
      How this is calculated
    </Link>
  );
}

export default function StoryPage() {
  const window = `${month(h.window.from_month)} to ${month(h.window.to_month)}`;
  return (
    <article className="space-y-12">
      <header className="space-y-4">
        <p className="text-sm font-medium uppercase tracking-wide text-ink-2">
          Los Angeles MyLA311 · new system, {window}
        </p>
        <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">
          {pct(h.closure_rate)} of requests were marked closed. {pct(h.verified_fix_rate)} have a
          code saying the work was done.
        </h1>
        <p className="max-w-3xl text-lg text-ink-2">
          When a MyLA311 request is marked Closed, the record also says how it ended. In the
          relaunched system, the gap between the two is{" "}
          <strong className="text-ink">{points(h.gap_pp)}</strong>: requests closed without a
          code that says the problem was fixed.
        </p>
        <dl className="grid max-w-3xl grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-rule bg-surface p-4">
            <dt className="text-sm text-ink-2">Marked closed</dt>
            <dd className="tabular text-3xl font-semibold">{pct(h.closure_rate)}</dd>
          </div>
          <div className="rounded-lg border border-rule bg-surface p-4">
            <dt className="text-sm text-ink-2">Verified fixed</dt>
            <dd className="tabular text-3xl font-semibold text-[#1c5cab]">
              {pct(h.verified_fix_rate)}
            </dd>
          </div>
          <div className="rounded-lg border border-rule bg-surface p-4">
            <dt className="text-sm text-ink-2">Closed, not verified fixed</dt>
            <dd className="tabular text-3xl font-semibold">{points(h.gap_pp)}</dd>
          </div>
        </dl>
        <p className="max-w-3xl text-sm text-ink-2">
          Out of {count(h.fix_rate_base)} service requests filed {window}. The base leaves out{" "}
          {count(h.excluded_from_base.neutral)} duplicates and information-only closes and{" "}
          {count(h.excluded_from_base.handed_off)} intake handoffs, whose own record can&apos;t
          show a fix. Counting every request, the City&apos;s closure rate is{" "}
          {pct(h.official_closure_rate)}. <HowCalculated metric="closed_fixed_gap_pp" />
        </p>
      </header>

      <section aria-labelledby="trend-heading" className="space-y-3">
        <h2 id="trend-heading" className="text-xl font-semibold">
          The gap has held since the relaunch
        </h2>
        <p className="max-w-3xl text-ink-2">
          Resolution codes start with the new system on {day(findings.parameters.cutover_date)};
          the old system recorded none, so there is no earlier line. Months filed after{" "}
          {month(h.window.to_month)} are left out until their requests have had{" "}
          {findings.parameters.headline_followup_days} days to close.
        </p>
        <TrendChart months={months} launch={day(findings.parameters.cutover_date)} />
        <HowCalculated metric="closed_fixed_gap_pp" />
      </section>

      <section aria-labelledby="findings-heading" className="space-y-4">
        <h2 id="findings-heading" className="text-xl font-semibold">
          Three things the records show
        </h2>
        <ol className="grid gap-4 md:grid-cols-3">
          <li className="space-y-2 rounded-lg border border-rule bg-surface p-4">
            <h3 className="font-semibold">A few codes carry the gap</h3>
            <p className="text-ink-2">
              Five resolution codes account for {pct(q2.top_5_codes_share, 0)} of the{" "}
              {count(q2.closed_unverified_total)} requests closed without evidence of a fix.
              &ldquo;QC-Item Not Out&rdquo; alone carries {pct(itemNotOut.share_of_gap, 0)}.
            </p>
            <HowCalculated metric="closed_unverified" />
          </li>
          <li className="space-y-2 rounded-lg border border-rule bg-surface p-4">
            <h3 className="font-semibold">&ldquo;Item not out&rdquo; depends on where</h3>
            <p className="text-ink-2">
              Crews closed {pct(allPickups.item_not_out_share, 0)} of bulky and dumped item
              pickups because nothing was out to collect. Across {ncs.compared} neighborhood
              councils that ranged from {pct(ncs.lowest[0].item_not_out_share, 0)} to{" "}
              {pct(ncs.highest[0].item_not_out_share, 0)}.
            </p>
            <HowCalculated anchor="codes" />
          </li>
          <li className="space-y-2 rounded-lg border border-rule bg-surface p-4">
            <h3 className="font-semibold">Graffiti closes more slowly than before</h3>
            <p className="text-ink-2">
              Resident-reported graffiti closed within 30 days fell from{" "}
              {pct(graffiti.closed_within_30d_rate.before, 0)} in the year before the relaunch
              to {pct(graffiti.closed_within_30d_rate.after, 0)} in the year after it, while
              cancellations fell from {pct(graffiti.cancellation_rate.before, 0)} to{" "}
              {pct(graffiti.cancellation_rate.after, 0)}.
            </p>
            <HowCalculated metric="closed_within_30d_rate" />
          </li>
        </ol>
      </section>

      <section className="space-y-3 rounded-lg border border-rule bg-surface p-6">
        <h2 className="text-xl font-semibold">Ask your own question</h2>
        <p className="max-w-3xl text-ink-2">
          Ask 311 answers questions from the same governed metrics, shows every query it runs,
          and links each number to the query behind it.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/ask"
            className="rounded-md bg-[#1c5cab] px-4 py-2 font-medium text-white no-underline hover:bg-[#184f95]"
          >
            Ask 311
          </Link>
          <Link href="/explore" className="rounded-md border border-rule px-4 py-2 no-underline">
            Explore the data
          </Link>
        </div>
      </section>
    </article>
  );
}
