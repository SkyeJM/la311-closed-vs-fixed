"use client";

// The two methodology tables that read the served data: the reviewed code map (searchable)
// and the crosswalk of request types between the old and new systems.
import { useEffect, useMemo, useState } from "react";
import { type CodeRow, getCodes, getReference, type Reference } from "@/lib/api";
import { count } from "@/lib/format";
import { CLASS_LABELS, GROUP_BY_ID, groupOf } from "@/lib/outcomes";

const SOURCE: Record<string, string> = {
  ai_accepted: "AI, accepted",
  ai_overridden: "AI, changed in review",
  human: "Reviewer",
};

export function CodeTable() {
  const [codes, setCodes] = useState<CodeRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    getCodes()
      .then((r) => setCodes(r.codes))
      .catch(() => setFailed(true));
  }, []);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (codes ?? []).filter(
      (c) =>
        !q ||
        [c.resolution_code, c.closure_outcome, c.main_department, c.main_request_type]
          .join(" ")
          .toLowerCase()
          .includes(q),
    );
  }, [codes, query]);
  if (failed) return <p className="text-ink-2">The code map couldn&apos;t load.</p>;
  if (!codes) return <p className="text-ink-2">Loading the code map…</p>;
  return (
    <div className="space-y-3">
      <label className="flex max-w-md flex-col gap-1 text-sm text-ink-2">
        Search codes, outcomes, departments or request types
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="rounded border border-rule bg-surface px-2 py-1.5 text-ink"
        />
      </label>
      <p className="text-sm text-ink-2" aria-live="polite">
        {shown.length} of {codes.length} codes
      </p>
      <div className="max-h-[32rem] overflow-auto rounded border border-rule">
        <table className="tabular w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr>
              {["Code", "Outcome", "Labeled by", "Service requests", "Main department"].map(
                (h) => (
                  <th key={h} scope="col" className="border-b border-rule px-2 py-2 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => {
              const group = groupOf(c.closure_outcome);
              return (
                <tr key={c.resolution_code} className="align-top">
                  <td className="border-b border-rule px-2 py-2">
                    <details>
                      <summary className="cursor-pointer">{c.resolution_code}</summary>
                      <p className="mt-1 max-w-prose text-ink-2">{c.rationale}</p>
                    </details>
                  </td>
                  <td className="border-b border-rule px-2 py-2">
                    <span className="inline-flex items-center gap-2">
                      <span
                        aria-hidden
                        className="inline-block h-3 w-3 shrink-0 rounded-sm"
                        style={{ background: group ? GROUP_BY_ID[group].color : "#898781" }}
                      />
                      {CLASS_LABELS[c.closure_outcome] ?? c.closure_outcome}
                    </span>
                  </td>
                  <td className="border-b border-rule px-2 py-2">
                    {SOURCE[c.label_source] ?? c.label_source}
                  </td>
                  <td className="border-b border-rule px-2 py-2 text-right">
                    {count(c.n_service_cases)}
                  </td>
                  <td className="border-b border-rule px-2 py-2">{c.main_department ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const COMPARISON: Record<string, string> = {
  full: "All measures",
  resident_reported_only: "Resident-reported only",
  volume_only: "Volume only",
  none: "Not compared",
};

export function CrosswalkTable() {
  const [rows, setRows] = useState<Reference["crosswalk"] | null>(null);
  useEffect(() => {
    getReference()
      .then((r) => setRows(r.crosswalk.filter((c) => c.is_crosswalked)))
      .catch(() => setRows([]));
  }, []);
  if (!rows) return <p className="text-ink-2">Loading the crosswalk…</p>;
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full border-collapse text-left text-sm">
        <thead>
          <tr>
            {["Category", "System", "Request type", "Compared on", "Requests", "Note"].map((h) => (
              <th key={h} scope="col" className="border-b border-rule px-2 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.era}-${r.request_type}`} className="align-top">
              <td className="border-b border-rule px-2 py-2">{r.unified_category}</td>
              <td className="border-b border-rule px-2 py-2">{r.era === "legacy" ? "Old" : "New"}</td>
              <td className="border-b border-rule px-2 py-2">{r.request_type}</td>
              <td className="border-b border-rule px-2 py-2">
                {COMPARISON[r.cross_era_comparison] ?? r.cross_era_comparison}
              </td>
              <td className="border-b border-rule px-2 py-2 text-right">{count(r.n_requests)}</td>
              <td className="border-b border-rule px-2 py-2 text-ink-2">{r.comparability_note ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
