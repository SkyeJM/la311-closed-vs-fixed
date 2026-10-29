import type { Metadata } from "next";
import agreement from "@/data/agreement.json";
import evals from "@/data/eval-summary.json";
import findings from "@/data/findings.json";
import metrics from "@/data/metrics.json";
import sources from "@/data/sources.json";
import { day, month, pct } from "@/lib/format";
import { CLASS_LABELS, CLASSES, GROUP_BY_ID, GROUPS } from "@/lib/outcomes";
import { CodeTable, CrosswalkTable } from "./Tables";

export const metadata: Metadata = { title: "Methodology" };

type Metric = {
  label: string;
  unit: string;
  evidence: string;
  eras: string[];
  description: string;
};

const EVIDENCE: Record<string, string> = {
  E1: "E1 · the code says what happened",
  E2: "E2 · behavior",
  status: "Status",
  none: "Count",
};

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-6 space-y-3">
      <h2 id={`${id}-heading`} className="text-2xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function MethodologyPage() {
  const h = findings.headline;
  const params = findings.parameters;
  const runs = agreement.ai_human_agreement;
  const sourcesByEra = (era: string) => sources.filter((s) => s.era === era);
  return (
    <article className="space-y-12">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Methodology</h1>
        <p className="max-w-3xl text-ink-2">
          How &ldquo;closed&rdquo; and &ldquo;fixed&rdquo; are measured, where the data comes
          from, what it can&apos;t show, and how the AI parts were checked.
        </p>
        <nav aria-label="On this page" className="text-sm">
          <ul className="flex flex-wrap gap-x-4 gap-y-2">
            {[
              ["outcomes", "Outcomes"],
              ["metrics", "Metrics"],
              ["sources", "Sources"],
              ["crosswalk", "Crosswalk"],
              ["codes", "Code map"],
              ["labeling", "AI labeling"],
              ["evals", "Ask 311 evals"],
              ["limitations", "Limitations"],
            ].map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="inline-block py-1">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <Section id="outcomes" title="How requests end">
        <p className="max-w-3xl text-ink-2">
          In the new MyLA311 (from {day(params.cutover_date)}), each request that ends carries a
          resolution code. A reviewed map turns every code into one outcome class. A request is{" "}
          <strong className="text-ink">closed</strong> when its status says Closed (or Closed
          Ext-Referred), and <strong className="text-ink">verified fixed</strong> when its class
          says the work was done. Requests marked Reported end at intake and are worked in
          another system, so their outcome isn&apos;t in this data.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr>
                {["Outcome class", "Group", "Counts as fixed", "Meaning"].map((c) => (
                  <th key={c} scope="col" className="border-b border-rule px-2 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CLASSES.map((c) => {
                const group = GROUP_BY_ID[c.outcome_group];
                return (
                  <tr key={c.closure_outcome} className="align-top">
                    <td className="border-b border-rule px-2 py-2">
                      {CLASS_LABELS[c.closure_outcome] ?? c.closure_outcome}
                    </td>
                    <td className="border-b border-rule px-2 py-2">
                      <span className="inline-flex items-center gap-2">
                        <span
                          aria-hidden
                          className="inline-block h-3 w-3 shrink-0 rounded-sm"
                          style={{ background: group.color }}
                        />
                        {group.label}
                      </span>
                    </td>
                    <td className="border-b border-rule px-2 py-2">{c.counts_as_fixed}</td>
                    <td className="border-b border-rule px-2 py-2 text-ink-2">{c.description}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="max-w-3xl text-sm text-ink-2">
          Colors follow the six outcome groups ({GROUPS.map((g) => g.label).join(", ")}),
          everywhere on the site. The {CLASSES.length} classes are more than colors can keep
          apart for every reader, so classes share their group&apos;s color and are named in
          text.
        </p>
      </Section>

      <Section id="metrics" title="Metric definitions">
        <p className="max-w-3xl text-ink-2">
          Every rate is defined once in <code>metrics.yml</code> and computed from summed counts
          at query time. The story, the explore page and Ask 311 all use these definitions.
          Default window for the new system: requests filed {month(h.window.from_month)} to{" "}
          {month(h.window.to_month)}, the months with at least{" "}
          {params.headline_followup_days} days of follow-up.
        </p>
        <dl className="space-y-4">
          {Object.entries(metrics as Record<string, Metric>).map(([name, m]) => (
            <div
              key={name}
              id={`metric-${name}`}
              className="scroll-mt-6 rounded-lg border border-rule bg-surface p-4"
            >
              <dt className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-semibold">{m.label}</span>
                <code className="text-xs text-ink-2">{name}</code>
                <span className="text-xs text-ink-2">
                  {EVIDENCE[m.evidence] ?? m.evidence} · {m.eras.join(" and ")} system ·{" "}
                  {m.unit.replace("_", " ")}
                </span>
              </dt>
              <dd className="mt-1 text-ink-2">
                {m.description.split("`").map((part, i) =>
                  i % 2 ? <code key={i}>{part}</code> : part,
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section id="sources" title="Sources">
        <p className="max-w-3xl text-ink-2">
          Public open data from the City of Los Angeles (CC0), pulled in bulk from{" "}
          <a href="https://data.lacity.org">data.lacity.org</a> and refreshed incrementally. Data
          through {day(findings.data.data_end)}. No scraping, no logged-in sources, and no
          addresses or coordinates leave the build: the site and the AI read only aggregated
          tables and a slim table without locations.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            ["current", "New MyLA311 (Cases, with resolution codes)"],
            ["legacy", "Old MyLA311 (status only)"],
          ].map(([era, title]) => (
            <div key={era}>
              <h3 className="font-semibold">{title}</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                {sourcesByEra(era).map((s) => (
                  <li key={s.id}>
                    <a href={`https://data.lacity.org/d/${s.id}`} className="inline-block py-0.5">
                      {s.name}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <Section id="crosswalk" title="Comparing the old and new systems">
        <p className="max-w-3xl text-ink-2">
          Only these categories exist in both systems. Comparisons use the{" "}
          {params.cutover_compare_months} months before the relaunch against the{" "}
          {params.cutover_compare_months} months after both systems stopped running side by side
          ({day(params.overlap_end_date)}), leave out crews logging their own work, and measure
          closing speed as &ldquo;closed within N days&rdquo;, because requests still open in the
          old system when it stopped never close in its data.
        </p>
        <CrosswalkTable />
      </Section>

      <Section id="codes" title="The resolution-code map">
        <p className="max-w-3xl text-ink-2">
          Claude labeled every code from its context (departments, request types, volumes,
          statuses); a person reviewed every label. Open a code to read the reasoning.
        </p>
        <CodeTable />
      </Section>

      <Section id="labeling" title="AI labeling, checked by a person">
        <p className="max-w-3xl text-ink-2">
          Each of the {agreement.codes} codes was labeled twice by Claude Haiku, with Claude
          Sonnet called when the two runs disagreed or were unsure. The reviewer accepted the
          AI&apos;s label for {pct(runs.share_of_codes)} of codes, covering{" "}
          {pct(runs.share_of_service_cases)} of service requests, and changed{" "}
          {runs.overrides.length}.
        </p>
      </Section>

      <Section id="evals" title="How accurate is Ask 311?">
        <p className="max-w-3xl text-ink-2">
          A {evals.models[0].questions}-question test set (numeric questions, questions it must
          qualify or decline, and questions in Spanish) runs against each model. Expected
          numbers are computed from the data when the test runs; a number must match within
          rounding, and an answer passes only if every check passes: the right metric, evidence
          level and answer type, required caveats, no causal claims, the question&apos;s
          language, and no number that didn&apos;t come from a query.
        </p>
        <div className="overflow-x-auto">
          <table className="tabular w-full border-collapse text-left text-sm">
            <thead>
              <tr>
                {[
                  "Model",
                  "Numbers correct",
                  "All checks",
                  "Spanish",
                  "Cost per question",
                  "Typical time",
                ].map((c) => (
                  <th key={c} scope="col" className="border-b border-rule px-2 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {evals.models.map((m) => (
                <tr key={m.model}>
                  <td className="border-b border-rule px-2 py-2">{m.model}</td>
                  <td className="border-b border-rule px-2 py-2">{pct(m.numeric_accuracy, 0)}</td>
                  <td className="border-b border-rule px-2 py-2">{pct(m.pass_rate, 0)}</td>
                  <td className="border-b border-rule px-2 py-2">{pct(m.spanish, 0)}</td>
                  <td className="border-b border-rule px-2 py-2">
                    ${m.cost_per_question_usd.toFixed(3)}
                  </td>
                  <td className="border-b border-rule px-2 py-2">{m.latency_s.p50.toFixed(1)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="limitations" title="What this can't tell you">
        <ul className="max-w-3xl list-disc space-y-2 pl-5 text-ink-2">
          <li>
            &ldquo;Verified fixed&rdquo; means the City&apos;s own record says the work was done.
            Nobody checked the street; a code can be wrong in either direction.
          </li>
          <li>
            The old system recorded no resolution codes, so fix rates exist only from the
            relaunch on. Older comparisons use closing speed and cancellations instead.
          </li>
          <li>
            Some departments close nearly everything with a generic code. Their low fix rates
            mean the outcome wasn&apos;t recorded, not that nothing was done.
          </li>
          <li>
            Requests handed off at intake (status Reported) are worked in other systems; this
            data can&apos;t follow them.
          </li>
          <li>
            New requests near a closed one mostly reflect places that keep generating reports,
            so re-reports are always compared with the same search before the request was filed.
          </li>
          <li>
            Everything here is descriptive. None of it says why a number is what it is, and
            none of it judges a person, crew or contractor.
          </li>
        </ul>
      </Section>
    </article>
  );
}
