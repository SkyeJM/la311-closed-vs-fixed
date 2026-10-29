// Outcome groups and classes, with the one color each group wears everywhere.
//
// The brief asks for one colorblind-safe color per outcome class; eleven classes are more hues
// than stay distinguishable, so the hue encodes the class's group (six) and charts that show
// classes label them in text. The order is the stacking order, validated for adjacent pairs.
import outcomes from "@/data/outcomes.json";

export type Group = "fixed" | "not_fixed" | "unknown" | "handed_off" | "cancelled" | "neutral";

export const GROUPS: { id: Group; label: string; color: string; note: string }[] = [
  { id: "fixed", label: "Verified fixed", color: "#2a78d6", note: "The code says the work was done" },
  { id: "not_fixed", label: "Closed, not fixed", color: "#eb6834", note: "Not found, referred out, deferred or unable" },
  { id: "unknown", label: "Closed without saying how", color: "#6250d6", note: "A generic code, or none" },
  { id: "handed_off", label: "Handed off at intake", color: "#1baf7a", note: "Worked in another system; outcome not in this data" },
  { id: "cancelled", label: "Cancelled", color: "#eda100", note: "By the customer, a contractor or the department" },
  { id: "neutral", label: "Duplicate or information only", color: "#e87ba4", note: "Outside the fix-rate base" },
];

export const GROUP_BY_ID = Object.fromEntries(GROUPS.map((g) => [g.id, g])) as Record<
  Group,
  (typeof GROUPS)[number]
>;

export type OutcomeClass = {
  closure_outcome: string;
  counts_as_fixed: string;
  outcome_group: Group;
  sort_order: string;
  description: string;
};

export const CLASSES = outcomes as OutcomeClass[];

export const CLASS_LABELS: Record<string, string> = {
  fixed_work_done: "Work done",
  already_resolved: "Already resolved",
  duplicate: "Duplicate",
  not_found: "Not found",
  referred_out_of_scope: "Referred out",
  deferred: "Deferred",
  unable: "Unable",
  cancelled: "Cancelled",
  info_only: "Information only",
  closed_unspecified: "Closed without saying how",
  handed_off: "Handed off at intake",
};

export function groupOf(closureOutcome: string | null): Group | null {
  if (!closureOutcome) return null;
  return CLASSES.find((c) => c.closure_outcome === closureOutcome)?.outcome_group ?? null;
}

export function colorOf(closureOutcome: string | null): string {
  const group = groupOf(closureOutcome);
  return group ? GROUP_BY_ID[group].color : "#898781";
}
