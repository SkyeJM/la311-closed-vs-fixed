// Browser calls to the FastAPI service, which shares this site's origin (/api/...).

export type MetricRequest = {
  metric: string;
  filters?: Record<string, string[]>;
  group_by?: string[];
  time_grain?: "none" | "month" | "quarter" | "year";
  date_range?: string[];
  order?: "dimensions" | "value_desc" | "value_asc";
  limit?: number;
  min_count?: number;
};

export type Row = Record<string, string | number | boolean | null>;

export type QueryRecord = {
  query_id: string;
  tool: string;
  sql: string;
  params: (string | number | boolean | null)[];
  columns: string[];
  rows: Row[];
  row_count: number;
  truncated: boolean;
  metric: string | null;
  unit: string | null;
  evidence: string | null;
  source: string | null;
  coverage: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export async function queryMetric(request: MetricRequest, signal?: AbortSignal) {
  const response = await fetch("/api/metrics/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  return json<QueryRecord>(response);
}

export type Reference = {
  categories: {
    name: string;
    department: string;
    crosswalked: boolean;
    comparison: string;
    requests: number;
  }[];
  departments: { name: string; requests: number }[];
  council_districts: { code: number; name: string }[];
  neighborhood_councils: { code: number; name: string }[];
  crosswalk: {
    era: string;
    request_type: string;
    unified_category: string;
    is_crosswalked: boolean;
    cross_era_comparison: string;
    comparability_note: string | null;
    is_service_request: boolean;
    non_service_reason: string | null;
    n_requests: number;
  }[];
  months: { first: string; last: string };
};

export async function getReference() {
  return json<Reference>(await fetch("/api/reference"));
}

export type CodeRow = {
  resolution_code: string;
  closure_outcome: string;
  outcome_group: string;
  counts_as_fixed: string;
  label_source: string;
  rationale: string;
  n_service_cases: number | null;
  main_department: string | null;
  main_request_type: string | null;
  n_context_overrides: number;
};

export async function getCodes() {
  return json<{ codes: CodeRow[] }>(await fetch("/api/codes"));
}

export async function getSuggested() {
  return json<{ questions: { question: string; cached: boolean }[] }>(
    await fetch("/api/suggested"),
  );
}

export async function sendFeedback(traceId: string, rating: "up" | "down") {
  await fetch("/api/feedback", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ trace_id: traceId, rating }),
  });
}

export type AgentEvent = { type: string; trace_id?: string; cached?: boolean } & Record<
  string,
  unknown
>;

/** POST a question and yield the agent's server-sent events as they arrive. */
export async function* ask(question: string, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    await json(response);
    return;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) yield JSON.parse(data) as AgentEvent;
      boundary = buffer.indexOf("\n\n");
    }
  }
}
