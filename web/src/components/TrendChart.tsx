"use client";

// The Story page's chart: marked closed vs verified fixed by month filed, the gap shaded
// between them, the relaunch marked where the codes begin. Months come from findings.json.
import type { VisualizationSpec } from "vega-embed";
import { VegaChart } from "@/components/VegaChart";
import { month, pct, points } from "@/lib/format";

export type TrendMonth = {
  month: string;
  closure_rate: number;
  verified_fix_rate: number;
  gap_pp: number;
};

export function TrendChart({ months, launch }: { months: TrendMonth[]; launch: string }) {
  const long = months.flatMap((m) => [
    { month: m.month, series: "Marked closed", rate: m.closure_rate },
    { month: m.month, series: "Verified fixed", rate: m.verified_fix_rate },
  ]);
  const spec: VisualizationSpec = {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    layer: [
      {
        data: { values: months },
        mark: { type: "area", color: "#eb6834", opacity: 0.14 },
        encoding: {
          x: { field: "month", type: "temporal" },
          y: { field: "closure_rate", type: "quantitative" },
          y2: { field: "verified_fix_rate" },
        },
      },
      {
        data: { values: long },
        mark: { type: "line", point: { size: 36 } },
        encoding: {
          x: {
            field: "month",
            type: "temporal",
            title: "Month the request was filed",
            axis: { format: "%b %Y", labelAngle: 0, tickCount: 6, grid: false },
          },
          y: {
            field: "rate",
            type: "quantitative",
            title: null,
            axis: { format: ".0%", tickCount: 4 },
          },
          color: {
            field: "series",
            type: "nominal",
            title: null,
            scale: { domain: ["Marked closed", "Verified fixed"], range: ["#52514e", "#2a78d6"] },
          },
          tooltip: [
            { field: "month", type: "temporal", format: "%B %Y", title: "Filed" },
            { field: "series", title: "Series" },
            { field: "rate", format: ".1%", title: "Share of the fix-rate base" },
          ],
        },
      },
      {
        data: { values: [{ month: months[0]?.month, label: `MyLA311 relaunched ${launch}` }] },
        mark: { type: "text", align: "left", dx: 4, dy: -8, color: "#52514e", fontSize: 12 },
        encoding: {
          x: { field: "month", type: "temporal" },
          y: { datum: 0.98 },
          text: { field: "label" },
        },
      },
    ],
  };
  return (
    <VegaChart
      spec={spec}
      label={`Line chart: share of requests marked closed and verified fixed by month filed, ${month(
        months[0].month,
      )} to ${month(months[months.length - 1].month)}. The gap between them is shaded.`}
      table={{
        columns: ["Month filed", "Marked closed", "Verified fixed", "Gap"],
        rows: months.map((m) => [
          month(m.month),
          pct(m.closure_rate),
          pct(m.verified_fix_rate),
          points(m.gap_pp),
        ]),
      }}
    />
  );
}
