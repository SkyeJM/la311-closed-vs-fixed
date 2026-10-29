"use client";

// Ask 311: a question, the agent's tool trace as it happens, and an answer whose every key
// number links to the query behind it. Each question stands alone (no chat history is sent).
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { VisualizationSpec } from "vega-embed";
import { VegaChart } from "@/components/VegaChart";
import { type AgentEvent, ApiError, ask, getSuggested, sendFeedback } from "@/lib/api";
import { count } from "@/lib/format";

type KeyNumber = { label: string; value: number; unit: string; metric: string | null; query_id: string };
type Answer = {
  answer_type: "answered" | "partial" | "declined";
  answer_markdown: string;
  key_numbers: KeyNumber[];
  evidence_level: string;
  caveats: string[];
  query_ids: string[];
  chart: string | null;
  follow_ups: string[];
};
type Step = {
  id: string;
  name: string;
  input: Record<string, unknown>;
  ok?: boolean;
  error?: string;
  query_id?: string;
  sql?: string;
  params?: unknown[];
  columns?: string[];
  rows?: Record<string, unknown>[];
  row_count?: number;
  duplicate_of?: string | null;
};
type Turn = {
  question: string;
  steps: Step[];
  answer?: Answer;
  chart?: { query_id: string; spec: VisualizationSpec } | null;
  problems?: string[];
  error?: string;
  status: "running" | "done";
  traceId?: string;
  cached?: boolean;
  seconds?: number;
  feedback?: "up" | "down";
};

const EVIDENCE: Record<string, string> = {
  E1: "E1: the resolution code says what happened",
  E2: "E2: behavior or status (timing, cancellations, re-reports)",
  E3: "E3: a modeled estimate",
  none: "No metric: counts, definitions or a decline",
};

function formatKey(k: KeyNumber): string {
  switch (k.unit) {
    case "percent":
      return `${k.value.toFixed(1)}%`;
    case "percentage_points":
      return `${k.value.toFixed(1)} pts`;
    case "hours":
      return `${k.value.toFixed(1)} hours`;
    case "days":
      return `${k.value.toFixed(1)} days`;
    default:
      return count(k.value);
  }
}

function describe(step: Step): string {
  const input = step.input;
  if (step.name === "query_metric") {
    const filters = (input.filters as { dimension: string; values: string[] }[]) ?? [];
    const parts = filters.map((f) => `${f.dimension} = ${f.values.join(", ")}`);
    const groups = (input.group_by as string[]) ?? [];
    const range = (input.date_range as string[]) ?? [];
    return [
      String(input.metric),
      parts.length ? `where ${parts.join("; ")}` : "",
      groups.length ? `by ${groups.join(", ")}` : "",
      range.length ? `${range[0].slice(0, 7)} to ${range[1].slice(0, 7)}` : "",
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (step.name === "run_sql") return "SQL over the aggregate tables";
  if (step.name === "describe_table") return `columns of ${String(input.table)}`;
  if (step.name === "explain_resolution_code") return `the mapping of "${String(input.code)}"`;
  if (step.name === "make_chart") return `a chart of ${String(input.query_id)}`;
  return "the metric catalog";
}

function TraceStep({ step, turnIndex }: { step: Step; turnIndex: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <li id={step.query_id ? `t${turnIndex}-${step.query_id}` : undefined} className="scroll-mt-20">
      <details className="rounded border border-rule bg-surface px-3 py-2">
        <summary className="cursor-pointer text-sm">
          {step.query_id && (
            <span className="font-mono text-xs text-ink-2">{step.query_id} </span>
          )}
          <span className="font-medium">{step.name}</span>: {describe(step)}
          {step.ok === undefined
            ? " …"
            : !step.ok
              ? " → error"
              : step.duplicate_of !== undefined
                ? ` → repeat${step.duplicate_of ? ` of ${step.duplicate_of}` : ""}, not run again`
                : step.row_count !== undefined
                  ? ` → ${count(step.row_count)} ${step.row_count === 1 ? "row" : "rows"}`
                  : ""}
        </summary>
        <div className="mt-2 space-y-2 text-sm">
          {step.error && <p className="text-[#b3261e]">{step.error}</p>}
          {step.sql && (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-ink-2">SQL</span>
                <button
                  type="button"
                  className="text-xs underline"
                  onClick={async () => {
                    await navigator.clipboard.writeText(step.sql ?? "");
                    setCopied(true);
                  }}
                >
                  {copied ? "Copied" : "Copy SQL"}
                </button>
              </div>
              <pre className="overflow-x-auto rounded bg-page p-2 text-xs">
                {step.sql}
                {step.params?.length ? `\n-- parameters: ${JSON.stringify(step.params)}` : ""}
              </pre>
            </div>
          )}
          {step.rows && step.rows.length > 0 && (
            <div className="max-h-64 overflow-auto">
              <table className="tabular w-full border-collapse text-left text-xs">
                <thead>
                  <tr>
                    {Object.keys(step.rows[0]).map((c) => (
                      <th key={c} scope="col" className="border-b border-rule px-2 py-1 font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {step.rows.slice(0, 20).map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="border-b border-rule px-2 py-1">
                          {v === null ? "null" : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </details>
    </li>
  );
}

function AnswerView({
  turn,
  index,
  onAsk,
  onFeedback,
}: {
  turn: Turn;
  index: number;
  onAsk: (q: string) => void;
  onFeedback: (rating: "up" | "down") => void;
}) {
  const a = turn.answer!;
  const open = (queryId: string) => {
    const item = document.getElementById(`t${index}-${queryId}`);
    item?.querySelector("details")?.setAttribute("open", "");
    item?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return (
    <div className="space-y-4">
      {a.answer_type !== "answered" && (
        <p className="text-sm font-medium text-ink-2">
          {a.answer_type === "partial" ? "Partly answerable from this data" : "Outside what this data can answer"}
        </p>
      )}
      <div className="prose-answer max-w-none">
        <ReactMarkdown>{a.answer_markdown}</ReactMarkdown>
      </div>
      {a.key_numbers.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Key numbers, each linked to its query">
          {a.key_numbers.map((k, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => open(k.query_id)}
                className="rounded border border-rule bg-surface px-2 py-1 text-left text-sm hover:border-[#1c5cab]"
              >
                <span className="tabular font-semibold">{formatKey(k)}</span>{" "}
                <span className="text-ink-2">{k.label}</span>{" "}
                <span className="font-mono text-xs text-ink-2">{k.query_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {turn.chart && (
        <VegaChart
          spec={turn.chart.spec}
          label={`Chart drawn from query ${turn.chart.query_id}`}
          height={260}
        />
      )}
      {a.caveats.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold">Caveats</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
            {a.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-sm text-ink-2">
        Evidence: {EVIDENCE[a.evidence_level] ?? a.evidence_level}
        {turn.cached
          ? " · a saved answer to a suggested question, shown instantly"
          : turn.seconds !== undefined
            ? ` · answered in ${turn.seconds.toFixed(1)} s`
            : ""}
      </p>
      {turn.problems && turn.problems.length > 0 && (
        <p className="rounded border border-[#b3261e] p-2 text-sm text-[#b3261e]">
          This answer failed the automatic number check: {turn.problems.join("; ")}
        </p>
      )}
      {a.follow_ups.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {a.follow_ups.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onAsk(q)}
              className="rounded-full border border-rule bg-surface px-3 py-1 text-left text-sm hover:border-[#1c5cab]"
            >
              {q}
            </button>
          ))}
        </div>
      )}
      {turn.traceId && (
        <div className="flex items-center gap-2 text-sm text-ink-2">
          Was this useful?
          {(["up", "down"] as const).map((rating) => (
            <button
              key={rating}
              type="button"
              aria-pressed={turn.feedback === rating}
              onClick={() => onFeedback(rating)}
              className={`rounded border px-2 py-0.5 ${turn.feedback === rating ? "border-[#1c5cab] bg-[#1c5cab] text-white" : "border-rule"}`}
            >
              {rating === "up" ? "Yes" : "No"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AskClient() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [suggested, setSuggested] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const top = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getSuggested()
      .then((s) => setSuggested(s.questions.map((q) => q.question)))
      .catch(() => setSuggested([]));
  }, []);

  const patch = (index: number, change: (t: Turn) => Turn) =>
    setTurns((all) => all.map((t, i) => (i === index ? change(t) : t)));

  async function run(text: string) {
    const q = text.trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    setQuestion("");
    const index = turns.length;
    setTurns((all) => [...all, { question: q, steps: [], status: "running" }]);
    setTimeout(() => top.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    try {
      for await (const event of ask(q)) handle(index, event);
    } catch (e) {
      const message =
        e instanceof ApiError ? e.message : "The connection dropped before the answer finished.";
      patch(index, (t) => ({ ...t, error: message }));
    } finally {
      patch(index, (t) => ({ ...t, status: "done" }));
      setBusy(false);
    }
  }

  function handle(index: number, e: AgentEvent) {
    patch(index, (t) => {
      const base = { ...t, traceId: e.trace_id ?? t.traceId, cached: e.cached ?? t.cached };
      switch (e.type) {
        case "tool_call":
          return {
            ...base,
            steps: [
              ...t.steps,
              { id: String(e.id), name: String(e.name), input: e.input as Record<string, unknown> },
            ],
          };
        case "tool_result":
          return {
            ...base,
            steps: t.steps.map((s) =>
              s.id === e.id
                ? {
                    ...s,
                    ok: Boolean(e.ok),
                    error: e.error as string | undefined,
                    query_id: e.query_id as string | undefined,
                    sql: e.sql as string | undefined,
                    params: e.params as unknown[] | undefined,
                    columns: e.columns as string[] | undefined,
                    rows: e.rows as Record<string, unknown>[] | undefined,
                    row_count: e.row_count as number | undefined,
                    duplicate_of:
                      "duplicate_of" in e ? ((e.duplicate_of as string | null) ?? null) : undefined,
                  }
                : s,
            ),
          };
        case "answer":
          return {
            ...base,
            answer: e.answer as Answer,
            chart: e.chart as Turn["chart"],
            problems: e.problems as string[],
          };
        case "error":
          return { ...base, error: String(e.message) };
        case "done":
          return { ...base, seconds: Number(e.latency_s) };
        default:
          return base;
      }
    });
  }

  return (
    <div className="space-y-8">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(question);
        }}
        className="space-y-2"
      >
        <label htmlFor="question" className="text-sm font-medium">
          Ask about MyLA311 service requests (English or Spanish)
        </label>
        <div className="flex gap-2">
          <input
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={600}
            placeholder="Which categories have the biggest gap between closed and fixed?"
            className="min-w-0 flex-1 rounded border border-rule bg-surface px-3 py-2"
          />
          <button
            type="submit"
            disabled={busy || question.trim().length < 3}
            className="rounded-md bg-[#1c5cab] px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Working…" : "Ask"}
          </button>
        </div>
        <p className="text-xs text-ink-2">
          Answers come only from the City&apos;s open data through governed metrics; every number
          links to its query. No addresses or individuals. Limited to a few questions an hour.
        </p>
      </form>
      {turns.length === 0 && suggested.length > 0 && (
        <section aria-labelledby="suggested-heading" className="space-y-2">
          <h2 id="suggested-heading" className="text-sm font-semibold text-ink-2">
            Try one of these (answered instantly from a cache)
          </h2>
          <div className="flex flex-wrap gap-2">
            {suggested.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => run(q)}
                className="rounded-full border border-rule bg-surface px-3 py-1 text-left text-sm hover:border-[#1c5cab]"
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      <div ref={top} />
      <ol className="space-y-10">
        {turns.map((turn, i) => ({ turn, i })).reverse().map(({ turn, i }) => {
          const queries = turn.steps.filter((s) => s.query_id).length;
          return (
            <li key={i} className="space-y-4 border-t border-rule pt-6">
              <h2 className="text-xl font-semibold">{turn.question}</h2>
              <section aria-label="How the answer was built" className="space-y-2">
                <h3 className="text-sm font-semibold text-ink-2">
                  {turn.status === "running"
                    ? `Working… ${turn.steps.length ? `${turn.steps.length} tool calls so far` : ""}`
                    : `Trace: ${turn.steps.length} tool ${turn.steps.length === 1 ? "call" : "calls"}, ${queries} ${queries === 1 ? "query" : "queries"}`}
                </h3>
                <ol className="space-y-1">
                  {turn.steps.map((s) => (
                    <TraceStep key={s.id} step={s} turnIndex={i} />
                  ))}
                </ol>
              </section>
              {turn.answer && (
                <AnswerView
                  turn={turn}
                  index={i}
                  onAsk={run}
                  onFeedback={(rating) => {
                    if (turn.traceId) sendFeedback(turn.traceId, rating).catch(() => {});
                    patch(i, (t) => ({ ...t, feedback: rating }));
                  }}
                />
              )}
              {turn.error && (
                <p role="alert" className="rounded border border-rule bg-surface p-3 text-sm">
                  {turn.error}
                </p>
              )}
            </li>
          );
        })}
      </ol>

    </div>
  );
}
