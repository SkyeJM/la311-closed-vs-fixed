"use client";

// Explore: the governed metrics behind the story, filtered. Every chart is one query to
// /api/metrics/query, and its SQL is one click away.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { VisualizationSpec } from "vega-embed";
import { VegaChart } from "@/components/VegaChart";
import {
  getReference,
  type MetricRequest,
  type QueryRecord,
  queryMetric,
  type Reference,
  type Row,
} from "@/lib/api";
import { count, month, pct, points } from "@/lib/format";
import { CLASS_LABELS, GROUP_BY_ID, GROUPS, groupOf } from "@/lib/outcomes";

type Filters = {
  category: string;
  department: string;
  cd: string;
  nc: string;
  from: string;
  to: string;
  era: "current" | "cutover";
};

const FIELDS: (keyof Filters)[] = ["category", "department", "cd", "nc", "from", "to", "era"];

function useFilters(): [Filters, (patch: Partial<Filters>) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const filters: Filters = {
    category: params.get("category") ?? "",
    department: params.get("department") ?? "",
    cd: params.get("cd") ?? "",
    nc: params.get("nc") ?? "",
    from: params.get("from") ?? "2025-03",
    to: params.get("to") ?? "2026-07",
    era: params.get("era") === "cutover" ? "cutover" : "current",
  };
  const update = (patch: Partial<Filters>) => {
    const next = new URLSearchParams();
    for (const key of FIELDS) {
      const value = (patch[key] ?? filters[key]) as string;
      if (value) next.set(key, value);
    }
    router.replace(`${path}?${next.toString()}`, { scroll: false });
  };
  return [filters, update];
}

function selection(f: Filters): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  if (f.category) out.unified_category = [f.category];
  if (f.department) out.department = [f.department];
  if (f.cd) out.cd = [f.cd];
  if (f.nc) out.nc_code = [f.nc];
  return out;
}

type Loaded = { gap?: QueryRecord; trend?: QueryRecord; mix?: QueryRecord; codes?: QueryRecord };

function requestsFor(f: Filters): Partial<Record<keyof Loaded, MetricRequest>> {
  const range = [`${f.from}-01`, `${f.to}-01`];
  const where = selection(f);
  if (f.era === "cutover") {
    return {
      trend: {
        metric: "closed_within_30d_rate",
        filters: f.category ? { unified_category: [f.category] } : {},
        group_by: ["era"],
        time_grain: "month",
        date_range: ["2023-01-01", `${f.to}-01`],
      },
    };
  }
  return {
    gap: { metric: "closed_fixed_gap_pp", filters: where, date_range: range },
    trend: { metric: "closed_fixed_gap_pp", filters: where, date_range: range, time_grain: "month" },
    mix: {
      metric: "outcome_mix",
      filters: where,
      date_range: range,
      time_grain: "month",
      group_by: ["closure_outcome"],
    },
    codes: {
      metric: "closed_unverified",
      filters: where,
      date_range: range,
      group_by: ["resolution_code", "closure_outcome"],
      order: "value_desc",
      limit: 10,
    },
  };
}

type Result = { key: string; data: Loaded; error: string | null };

function useQueries(f: Filters): { data: Loaded; error: string | null; loading: boolean } {
  const key = JSON.stringify(f);
  const [result, setResult] = useState<Result>({ key: "", data: {}, error: null });
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(
      Object.entries(requestsFor(JSON.parse(key))).map(async ([name, request]) => [
        name,
        await queryMetric(request, controller.signal),
      ]),
    )
      .then((entries) => setResult({ key, data: Object.fromEntries(entries), error: null }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setResult({ key, data: {}, error: e.message });
      });
    return () => controller.abort();
  }, [key]);
  // Until the new results arrive, the previous ones stay on screen.
  return { data: result.data, error: result.error, loading: result.key !== key };
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-sm text-ink-2">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-rule bg-surface px-2 py-1.5 text-ink"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ShowSql({ record }: { record?: QueryRecord }) {
  if (!record) return null;
  return (
    <details className="text-sm text-ink-2">
      <summary className="cursor-pointer select-none">Show the SQL</summary>
      <pre className="mt-2 overflow-x-auto rounded bg-surface p-3 text-xs text-ink">
        {record.sql}
        {record.params.length ? `\n-- parameters: ${JSON.stringify(record.params)}` : ""}
      </pre>
      {record.coverage && <p className="mt-1">Coverage: {record.coverage}</p>}
    </details>
  );
}

const num = (row: Row, key: string) => Number(row[key] ?? 0);

function Tiles({ record }: { record?: QueryRecord }) {
  const row = record?.rows[0];
  if (!row || !num(row, "a_denominator")) {
    return <p className="text-ink-2">No requests match these filters.</p>;
  }
  const tiles = [
    { label: "Marked closed", value: pct(num(row, "a_rate_pct") / 100) },
    { label: "Verified fixed", value: pct(num(row, "b_rate_pct") / 100) },
    { label: "Closed, not verified fixed", value: points(num(row, "value")) },
    { label: "Requests in the fix-rate base", value: count(num(row, "a_denominator")) },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-rule bg-surface p-3">
          <dt className="text-sm text-ink-2">{t.label}</dt>
          <dd className="tabular text-2xl font-semibold">{t.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function GapTrend({ record }: { record?: QueryRecord }) {
  const rows = (record?.rows ?? []).filter((r) => num(r, "a_denominator") > 0);
  if (rows.length < 2) return null;
  const long = rows.flatMap((r) => [
    { month: r.period_start, series: "Marked closed", rate: num(r, "a_rate_pct") / 100 },
    { month: r.period_start, series: "Verified fixed", rate: num(r, "b_rate_pct") / 100 },
  ]);
  const spec: VisualizationSpec = {
    data: { values: long },
    mark: { type: "line", point: { size: 36 } },
    encoding: {
      x: { field: "month", type: "temporal", title: null, axis: { format: "%b %Y", grid: false } },
      y: { field: "rate", type: "quantitative", title: null, axis: { format: ".0%" } },
      color: {
        field: "series",
        type: "nominal",
        title: null,
        scale: { domain: ["Marked closed", "Verified fixed"], range: ["#52514e", "#2a78d6"] },
      },
      tooltip: [
        { field: "month", type: "temporal", format: "%B %Y", title: "Filed" },
        { field: "series" },
        { field: "rate", format: ".1%", title: "Share" },
      ],
    },
  };
  return (
    <VegaChart
      spec={spec}
      label="Line chart: share marked closed and share verified fixed, by month filed"
      table={{
        columns: ["Month filed", "Marked closed", "Verified fixed", "Gap", "Base"],
        rows: rows.map((r) => [
          month(String(r.period_start)),
          pct(num(r, "a_rate_pct") / 100),
          pct(num(r, "b_rate_pct") / 100),
          points(num(r, "value")),
          count(num(r, "a_denominator")),
        ]),
      }}
    />
  );
}

function MixBars({ record }: { record?: QueryRecord }) {
  const rows = record?.rows ?? [];
  // Classes fold into their group's color; the table keeps every class.
  const byMonth = new Map<string, Map<string, number>>();
  for (const r of rows) {
    const group = groupOf(r.closure_outcome as string | null);
    if (!group) continue;
    const m = String(r.period_start);
    const groups = byMonth.get(m) ?? new Map();
    groups.set(group, (groups.get(group) ?? 0) + num(r, "value"));
    byMonth.set(m, groups);
  }
  const values = [...byMonth.entries()].flatMap(([m, groups]) =>
    GROUPS.map((g, i) => ({
      month: m,
      group: g.label,
      order: i,
      share: groups.get(g.id) ?? 0,
    })),
  );
  if (!values.length) return null;
  const spec: VisualizationSpec = {
    data: { values },
    mark: { type: "bar" },
    encoding: {
      x: { field: "month", type: "ordinal", timeUnit: "yearmonth", title: null },
      y: { field: "share", type: "quantitative", stack: "normalize", title: null, axis: { format: ".0%" } },
      color: {
        field: "group",
        type: "nominal",
        title: null,
        scale: { domain: GROUPS.map((g) => g.label), range: GROUPS.map((g) => g.color) },
        sort: GROUPS.map((g) => g.label),
      },
      order: { field: "order", type: "quantitative" },
      tooltip: [
        { field: "month", type: "temporal", timeUnit: "yearmonth", title: "Filed" },
        { field: "group", title: "Outcome" },
        { field: "share", format: ".1%", title: "Share of requests that ended" },
      ],
    },
  };
  const classes = new Map<string, number>();
  for (const r of rows) {
    const key = String(r.closure_outcome);
    classes.set(key, (classes.get(key) ?? 0) + num(r, "n"));
  }
  const total = [...classes.values()].reduce((a, b) => a + b, 0);
  return (
    <VegaChart
      spec={spec}
      label="Stacked bars: how requests that ended were closed, by month filed, in outcome groups"
      table={{
        columns: ["Outcome class", "Group", "Requests", "Share"],
        rows: [...classes.entries()]
          .sort((a, b) => b[1] - a[1])
          .map(([cls, n]) => [
            CLASS_LABELS[cls] ?? cls,
            GROUP_BY_ID[groupOf(cls) ?? "neutral"].label,
            count(n),
            pct(total ? n / total : null),
          ]),
      }}
    />
  );
}

function CodesTable({ record }: { record?: QueryRecord }) {
  const rows = record?.rows ?? [];
  if (!rows.length) return <p className="text-ink-2">No closed-but-unverified requests here.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full border-collapse text-left text-sm">
        <thead>
          <tr className="text-ink-2">
            <th scope="col" className="border-b border-rule py-2 pr-3 font-medium">
              Resolution code
            </th>
            <th scope="col" className="border-b border-rule py-2 pr-3 font-medium">
              Outcome
            </th>
            <th scope="col" className="border-b border-rule py-2 text-right font-medium">
              Closed without evidence of a fix
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cls = r.closure_outcome as string | null;
            const group = groupOf(cls);
            return (
              <tr key={String(r.resolution_code)}>
                <td className="border-b border-rule py-2 pr-3">
                  {(r.resolution_code as string) ?? "(no code)"}
                </td>
                <td className="border-b border-rule py-2 pr-3">
                  <span className="inline-flex items-center gap-2">
                    <span
                      aria-hidden
                      className="inline-block h-3 w-3 rounded-sm"
                      style={{ background: group ? GROUP_BY_ID[group].color : "#898781" }}
                    />
                    {cls ? (CLASS_LABELS[cls] ?? cls) : "Not mapped"}
                  </span>
                </td>
                <td className="border-b border-rule py-2 text-right">{count(num(r, "value"))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CutoverTrend({ record }: { record?: QueryRecord }) {
  const rows = (record?.rows ?? []).filter((r) => r.value !== null);
  if (!rows.length) return <p className="text-ink-2">No comparable requests for this choice.</p>;
  const spec: VisualizationSpec = {
    data: {
      values: rows.map((r) => ({
        month: r.period_start,
        system: r.era === "legacy" ? "Old system" : "New system",
        rate: num(r, "value"),
      })),
    },
    layer: [
      {
        mark: { type: "line", point: { size: 30 } },
        encoding: {
          x: { field: "month", type: "temporal", title: null, axis: { format: "%b %Y", grid: false } },
          y: { field: "rate", type: "quantitative", title: null, axis: { format: ".0%" } },
          color: {
            field: "system",
            type: "nominal",
            title: null,
            scale: { domain: ["Old system", "New system"], range: ["#52514e", "#2a78d6"] },
          },
          tooltip: [
            { field: "month", type: "temporal", format: "%B %Y", title: "Filed" },
            { field: "system" },
            { field: "rate", format: ".1%", title: "Closed within 30 days" },
          ],
        },
      },
      {
        data: { values: [{ date: "2025-03-28" }] },
        mark: { type: "rule", strokeDash: [4, 4], color: "#898781" },
        encoding: { x: { field: "date", type: "temporal" } },
      },
    ],
  };
  return (
    <VegaChart
      spec={spec}
      label="Line chart: share of requests closed within 30 days, by month filed, old and new system"
      table={{
        columns: ["Month filed", "System", "Closed within 30 days", "Requests followed"],
        rows: rows.map((r) => [
          month(String(r.period_start)),
          r.era === "legacy" ? "Old" : "New",
          pct(num(r, "value")),
          count(num(r, "denominator")),
        ]),
      }}
    />
  );
}

export function ExploreClient() {
  const [filters, update] = useFilters();
  const [reference, setReference] = useState<Reference | null>(null);
  const { data, error, loading } = useQueries(filters);
  useEffect(() => {
    getReference().then(setReference).catch(() => setReference(null));
  }, []);
  const categories = useMemo(
    () =>
      (reference?.categories ?? [])
        .filter((c) => filters.era === "current" || (c.crosswalked && c.comparison !== "volume_only"))
        .map((c) => ({ value: c.name, label: c.name })),
    [reference, filters.era],
  );
  const current = filters.era === "current";
  return (
    <div className="space-y-8">
      <fieldset className="space-y-3">
        <legend className="sr-only">Filters</legend>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="View">
          {(
            [
              ["current", "New system: closed vs fixed"],
              ["cutover", "Before and after the relaunch"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={filters.era === value}
              onClick={() => update({ era: value })}
              className={`rounded-full border px-3 py-1 text-sm ${
                filters.era === value
                  ? "border-[#1c5cab] bg-[#1c5cab] text-white"
                  : "border-rule bg-surface text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label="Category"
            value={filters.category}
            onChange={(v) => update({ category: v })}
            options={categories}
          />
          {current && (
            <>
              <Select
                label="Department"
                value={filters.department}
                onChange={(v) => update({ department: v })}
                options={(reference?.departments ?? []).map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
              />
              <Select
                label="Council district"
                value={filters.cd}
                onChange={(v) => update({ cd: v })}
                options={(reference?.council_districts ?? []).map((d) => ({
                  value: String(d.code),
                  label: d.name,
                }))}
              />
              <Select
                label="Neighborhood council"
                value={filters.nc}
                onChange={(v) => update({ nc: v })}
                options={(reference?.neighborhood_councils ?? []).map((d) => ({
                  value: String(d.code),
                  label: d.name,
                }))}
              />
              <label className="flex flex-col gap-1 text-sm text-ink-2">
                First month filed
                <input
                  type="month"
                  value={filters.from}
                  min="2025-03"
                  max={filters.to}
                  onChange={(e) => e.target.value && update({ from: e.target.value })}
                  className="rounded border border-rule bg-surface px-2 py-1 text-ink"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink-2">
                Last month filed
                <input
                  type="month"
                  value={filters.to}
                  min={filters.from}
                  max={reference?.months.last.slice(0, 7)}
                  onChange={(e) => e.target.value && update({ to: e.target.value })}
                  className="rounded border border-rule bg-surface px-2 py-1 text-ink"
                />
              </label>
            </>
          )}
        </div>
      </fieldset>

      <div aria-live="polite" className="text-sm text-ink-2">
        {loading ? "Loading…" : error ? `Couldn't load this view: ${error}` : null}
      </div>

      {current ? (
        <>
          <section className="space-y-3" aria-labelledby="tiles-heading">
            <h2 id="tiles-heading" className="text-lg font-semibold">
              Closed vs verified fixed
            </h2>
            <Tiles record={data.gap} />
            <ShowSql record={data.gap} />
          </section>
          <section className="space-y-3" aria-labelledby="trend-heading">
            <h2 id="trend-heading" className="text-lg font-semibold">
              By month filed
            </h2>
            <GapTrend record={data.trend} />
            <ShowSql record={data.trend} />
          </section>
          <section className="space-y-3" aria-labelledby="mix-heading">
            <h2 id="mix-heading" className="text-lg font-semibold">
              How requests ended
            </h2>
            <MixBars record={data.mix} />
            <ShowSql record={data.mix} />
          </section>
          <section className="space-y-3" aria-labelledby="codes-heading">
            <h2 id="codes-heading" className="text-lg font-semibold">
              Codes behind the gap
            </h2>
            <CodesTable record={data.codes} />
            <ShowSql record={data.codes} />
          </section>
        </>
      ) : (
        <section className="space-y-3" aria-labelledby="cutover-heading">
          <h2 id="cutover-heading" className="text-lg font-semibold">
            Closed within 30 days, old and new system
          </h2>
          <p className="max-w-3xl text-ink-2">
            Only categories that exist in both systems compare, with crews&apos; own reports left
            out. The old system has no resolution codes, so this view measures closing, not
            fixing. Requests still open when the old system stopped never close in its data.
          </p>
          <CutoverTrend record={data.trend} />
          <ShowSql record={data.trend} />
        </section>
      )}
    </div>
  );
}
