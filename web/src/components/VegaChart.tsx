"use client";

// Every chart on the site, the Ask agent's included, renders through here: Vega-Lite with one
// theme (recessive axes, 2px lines, the outcome palette), an accessible name, and a "Show the
// data" table, so no reading depends on color or on seeing the chart.
import dynamic from "next/dynamic";
import type { VisualizationSpec } from "vega-embed";

const VegaEmbed = dynamic(() => import("react-vega").then((m) => m.VegaEmbed), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded bg-rule/40" />,
});

const INK_2 = "#52514e";
export const THEME = {
  background: "transparent",
  font: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  view: { stroke: null },
  axis: {
    labelColor: INK_2,
    titleColor: INK_2,
    labelFontSize: 12,
    titleFontSize: 12,
    titleFontWeight: 400,
    gridColor: "#e1e0d9",
    domainColor: "#c3c2b7",
    tickColor: "#c3c2b7",
  },
  legend: {
    labelColor: INK_2,
    titleColor: INK_2,
    labelFontSize: 12,
    titleFontSize: 12,
    titleFontWeight: 400,
    orient: "top",
    symbolStrokeWidth: 2,
    labelLimit: 260,
  },
  title: { color: "#0b0b0b", fontSize: 14, fontWeight: 600, anchor: "start" },
  line: { strokeWidth: 2 },
  point: { size: 64, filled: true },
  bar: { stroke: "#fcfcfb", strokeWidth: 1 },
  range: {
    category: ["#2a78d6", "#eb6834", "#6250d6", "#1baf7a", "#eda100", "#e87ba4"],
  },
};

export type DataTable = { columns: string[]; rows: (string | number)[][] };

// Vega reads a bare date ("2025-03-01") as UTC midnight, which in Los Angeles is still the day
// before: March would label as February. Months are calendar months, so read them as local.
const BARE_DATE = /^\d{4}-\d{2}-\d{2}$/;

function localDates<T>(node: T): T {
  if (Array.isArray(node)) return node.map(localDates) as T;
  if (node && typeof node === "object") {
    return Object.fromEntries(
      Object.entries(node).map(([k, v]) => [
        k,
        typeof v === "string" && BARE_DATE.test(v) ? `${v}T00:00:00` : localDates(v),
      ]),
    ) as T;
  }
  return node;
}

export function VegaChart({
  spec,
  label,
  table,
  height = 280,
}: {
  spec: VisualizationSpec;
  label: string;
  table?: DataTable;
  height?: number;
}) {
  const sized = {
    width: "container",
    height,
    autosize: { type: "fit", contains: "padding" },
    ...localDates(spec),
  } as VisualizationSpec;
  return (
    <figure className="w-full">
      <div className="w-full" style={{ height: height + 40 }} role="img" aria-label={label}>
        <VegaEmbed
          spec={sized}
          options={{ actions: false, renderer: "svg", config: THEME as never }}
          className="w-full"
        />
      </div>
      {table && (
        <details className="mt-2 text-sm text-ink-2">
          <summary className="cursor-pointer select-none">Show the data</summary>
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="tabular w-full border-collapse text-left">
              <thead>
                <tr>
                  {table.columns.map((c) => (
                    <th key={c} scope="col" className="border-b border-rule px-2 py-1 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j} className="border-b border-rule px-2 py-1">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}
