"""Phase 1 profile of the raw pulls: writes docs/PROFILE.md and docs/profile/*.csv.

Every number in the report is computed here from data/raw/*/full.parquet, so it can be
regenerated after any pull with `make profile`. Outputs are aggregates only: no addresses, no
row-level records.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import yaml

from ingest.config import RAW_DIR, ROOT, UNIFIED_FIELDS_FILE, load_registry
from ingest.duck import sql_list

DOCS_DIR = ROOT / "docs"
TIMESTAMP = "coalesce(try_strptime({c}, '%m/%d/%Y %I:%M:%S %p'), try_cast({c} AS TIMESTAMP))"
CASTS = {
    "created_at": TIMESTAMP,
    "updated_at": TIMESTAMP,
    "closed_at": TIMESTAMP,
    "service_date": TIMESTAMP,
    "lat": "try_cast({c} AS DOUBLE)",
    "lon": "try_cast({c} AS DOUBLE)",
    "cd": "try_cast({c} AS INTEGER)",
    "nc_code": "try_cast({c} AS INTEGER)",
}
SKIPPED_FIELDS = {"address"}  # never loaded: the profile publishes aggregates only
CUTOVER = "2025-03-28"
# Codes whose label reads as "information only" (used as evidence, not as the final taxonomy).
INFO_CODE_PATTERN = r"^(GI|IP|KA|PE|RF)-|Information|Info Provided|Report has been received"
# Proposed non-service types (contacts, not service requests), each with the reason shown in
# PROFILE.md. Starts from the brief; revised against the evidence table in section 11a.
PROPOSED_NON_SERVICE = {
    "Information-Only": "an informational contact by definition (brief §3.3)",
    "Feedback": "comments about the service, not a request for work (both eras)",
    "Program Research": "brief's candidate; confirm against the evidence below",
}
# Brief section 4.5 starting guesses, checked here by volume, timing and department.
CROSSWALK_GUESSES = [
    (
        "Bulky / appliance / e-waste pickup",
        ["Bulky Items", "Metal/Household Appliances", "Electronic Waste"],
        ["Item Pickups"],
    ),
    ("Illegal dumping pickup", ["Illegal Dumping Pickup"], ["Illegal Dumping Item Pickup"]),
    (
        "Streetlights",
        ["Single Streetlight Issue", "Multiple Streetlight Issue"],
        ["Streetlight Repair Services"],
    ),
    ("Graffiti", ["Graffiti Removal"], ["Graffiti Removal"]),
    ("Homeless encampment", ["Homeless Encampment"], ["Homeless Encampment"]),
    ("Dead animal", ["Dead Animal Removal"], ["Dead Animal Removal"]),
    ("Water waste", ["Report Water Waste"], ["Report Water Wasting"]),
    ("Other", ["Other"], ["Other"]),
    ("Feedback", ["Feedback"], ["Feedback"]),
]


def fmt(value: object) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.1f}"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value).replace("|", "\\|")


def md_table(headers: list[str], rows: list[tuple]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return lines + [""]


def sql_in(values: list[str]) -> str:
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


class Profiler:
    def __init__(self, raw_root: Path = RAW_DIR, docs_dir: Path = DOCS_DIR) -> None:
        self.raw_root = raw_root
        self.docs_dir = docs_dir
        self.extracts_dir = docs_dir / "profile"
        self.registry = load_registry()
        self.manifest = json.loads((raw_root / "manifest.json").read_text())
        self.con = duckdb.connect()
        self.lines: list[str] = []
        self._load()

    # -- setup -------------------------------------------------------------------------------

    def _label(self, dataset) -> str:
        return f"{dataset.year} cases" if dataset.era == "current" else f"{dataset.year} legacy"

    def _load(self) -> None:
        spec = yaml.safe_load(UNIFIED_FIELDS_FILE.read_text())["fields"]
        datasets = [d for d in self.registry.datasets if d.id in self.manifest]
        self.labels = {d.id: self._label(d) for d in datasets}
        rows = ", ".join(
            f"('{d.id}', '{self.labels[d.id]}', '{d.era}', {d.year}, {i})"
            for i, d in enumerate(datasets)
        )
        self.con.execute(
            f"CREATE TABLE datasets AS SELECT * FROM (VALUES {rows}) t(id, label, era, year, sort)"
        )
        selects = []
        for era in ("legacy", "current"):
            files = [self.raw_root / d.id / "full.parquet" for d in datasets if d.era == era]
            if not files:
                continue
            columns = ["_dataset_id AS dataset_id", f"'{era}' AS era"]
            for unified, mapping in spec.items():
                if unified in SKIPPED_FIELDS:
                    continue
                source = mapping.get(era)
                expr = CASTS.get(unified, "{c}").format(c=f'"{source}"') if source else "NULL"
                columns.append(f"{expr} AS {unified}")
            columns.append(f'"{mapping_of(spec, "created_at", era)}" AS created_raw')
            columns.append(f'"{mapping_of(spec, "closed_at", era)}" AS closed_raw')
            selects.append(
                f"SELECT {', '.join(columns)} "
                f"FROM read_parquet({sql_list(files)}, union_by_name = true)"
            )
        self.con.execute(f"CREATE TABLE r AS {' UNION ALL BY NAME '.join(selects)}")
        self.con.execute(
            "CREATE VIEW r_labeled AS SELECT r.*, d.label, d.sort FROM r JOIN datasets d "
            "ON r.dataset_id = d.id"
        )

    def q(self, sql: str) -> list[tuple]:
        return self.con.execute(sql).fetchall()

    def emit(self, *lines: str) -> None:
        self.lines.extend(lines)

    def table(self, sql: str, headers: list[str] | None = None) -> list[tuple]:
        cursor = self.con.execute(sql)
        rows = cursor.fetchall()
        self.emit(*md_table(headers or [d[0] for d in cursor.description], rows))
        return rows

    def extract(self, name: str, sql: str) -> int:
        """Write a long list to docs/profile/<name>.csv instead of the report."""
        self.extracts_dir.mkdir(parents=True, exist_ok=True)
        cursor = self.con.execute(sql)
        rows = cursor.fetchall()
        with (self.extracts_dir / f"{name}.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([d[0] for d in cursor.description])
            writer.writerows(rows)
        return len(rows)

    # -- sections -----------------------------------------------------------------------------

    def inventory(self) -> None:
        self.emit("## 1. Inventory", "")
        rows = self.q(
            "SELECT label, dataset_id, era, count(*) AS n, count(DISTINCT request_id) AS ids, "
            "min(created_at), max(created_at), count(*) FILTER (created_at IS NULL) "
            "FROM r_labeled GROUP BY ALL ORDER BY any_value(sort)"
        )
        table = []
        for label, dataset_id, _era, n, ids, first, last, unparsed in rows:
            m = self.manifest[dataset_id]
            table.append(
                (label, dataset_id, n, m["live_count_after_pull"], n - ids, first, last, unparsed)
            )
        self.emit(
            "Rows in each full pull, the live `count(*)` taken right after it, duplicate IDs "
            "within the dataset, the created range, and `createddate` values that failed to "
            "parse.",
            "",
            *md_table(
                [
                    "dataset",
                    "id",
                    "rows",
                    "live count",
                    "dup ID rows",
                    "first created",
                    "last created",
                    "unparsed created",
                ],
                table,
            ),
        )
        total = sum(row[2] for row in table)
        self.emit(f"Total: {total:,} rows across {len(table)} datasets.", "")

    def monthly(self) -> None:
        self.emit(
            "## 2. Rows by month",
            "",
            "Created month, by era. The full dataset × month list is in "
            "`docs/profile/rows_by_dataset_month.csv`.",
            "",
        )
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        cols = ", ".join(
            f"count(*) FILTER (month(created_at) = {i + 1}) AS {m}" for i, m in enumerate(months)
        )
        for era in ("legacy", "current"):
            self.emit(f"**{era}**", "")
            self.table(
                f"SELECT year(created_at) AS year, {cols}, count(*) AS total FROM r "
                f"WHERE era = '{era}' GROUP BY 1 ORDER BY 1",
                ["year", *months, "total"],
            )
        self.extract(
            "rows_by_dataset_month",
            "SELECT dataset_id, label, strftime(created_at, '%Y-%m') AS month, count(*) AS rows "
            "FROM r_labeled GROUP BY ALL ORDER BY any_value(sort), month",
        )

    def duplicates(self) -> None:
        self.emit("## 3. Duplicate IDs", "")
        self.table(
            "WITH ids AS (SELECT era, request_id, count(*) AS n, count(DISTINCT dataset_id) AS ds, "
            "min(created_at) AS created FROM r GROUP BY 1, 2 HAVING count(*) > 1) "
            "SELECT era, count(*) AS duplicated_ids, sum(n) AS rows_involved, "
            "count(*) FILTER (ds > 1) AS ids_in_two_datasets, "
            "count(*) FILTER (ds > 1 AND strftime(created, '%m-%d %H:%M:%S') = '01-01 00:00:00') "
            "AS at_jan1_midnight FROM ids GROUP BY 1 ORDER BY 1",
            [
                "era",
                "duplicated IDs",
                "rows involved",
                "IDs in 2 datasets",
                "…created exactly Jan 1 00:00:00",
            ],
        )
        self.con.execute(
            "CREATE TEMP TABLE dup AS SELECT * EXCLUDE (dataset_id) FROM r "
            "QUALIFY count(*) OVER (PARTITION BY era, request_id) > 1"
        )
        dup_rows = dict(self.q("SELECT era, count(*) FROM dup GROUP BY era"))
        distinct_rows = dict(
            self.q("SELECT era, count(*) FROM (SELECT DISTINCT * FROM dup) GROUP BY era")
        )
        self.emit(
            *md_table(
                ["era", "duplicate-ID rows", "rows that exactly copy another (ignoring dataset)"],
                [(era, n, n - distinct_rows.get(era, 0)) for era, n in sorted(dup_rows.items())],
            )
        )

    def timestamps(self) -> None:
        self.emit("## 4. Timestamps", "")
        self.emit(
            "Precision, date-only closes, and durations. `closed_at < created_at` counts "
            "negative durations; 'date-only close' means `closeddate` is exactly midnight.",
            "",
        )
        self.table(
            "SELECT label, round(100 * avg((second(created_at) = 0)::INT), 1), "
            "count(*) FILTER (closed_at IS NOT NULL), "
            "round(100 * avg((closed_at = date_trunc('day', closed_at))::INT), 2), "
            "count(*) FILTER (closed_at < created_at), count(*) FILTER (closed_at = created_at), "
            "count(*) FILTER (closed_raw IS NOT NULL AND closed_at IS NULL) "
            "FROM r_labeled GROUP BY label ORDER BY any_value(sort)",
            [
                "dataset",
                "% created with :00 seconds",
                "rows with closed_at",
                "% date-only closes",
                "negative durations",
                "zero durations",
                "unparsed closed",
            ],
        )
        self.emit(
            "Hour of day of `createddate` (share of each era's rows). A daytime peak means the "
            "floating timestamps are local time; UTC would peak about 8 hours later.",
            "",
        )
        self.table(
            "SELECT hour(created_at) AS hour, "
            "round(100 * count(*) FILTER (era = 'legacy') / "
            "(SELECT count(*) FROM r WHERE era = 'legacy'), 2), "
            "round(100 * count(*) FILTER (era = 'current') / "
            "(SELECT count(*) FROM r WHERE era = 'current'), 2) "
            "FROM r GROUP BY 1 ORDER BY 1",
            ["hour", "legacy %", "current %"],
        )
        self.emit("Negative durations by type and size:", "")
        self.table(
            "SELECT era, request_type, count(*) AS n, "
            "count(*) FILTER (date_diff('minute', closed_at, created_at) < 60) AS under_1h, "
            "count(*) FILTER (date_diff('minute', closed_at, created_at) BETWEEN 60 AND 1439) "
            "AS h1_to_24, count(*) FILTER (date_diff('minute', closed_at, created_at) >= 1440) "
            "AS over_1d FROM r WHERE closed_at < created_at GROUP BY 1, 2 ORDER BY n DESC LIMIT 15",
            ["era", "type", "negative", "< 1 h", "1–24 h", "≥ 1 day"],
        )

    def statuses(self) -> None:
        self.emit("## 5. Statuses", "")
        for era in ("legacy", "current"):
            labels = [lab for d, lab in self.labels.items() if self.registry.get(d).era == era]
            cols = ", ".join(f"count(*) FILTER (label = '{lab}')" for lab in labels)
            self.emit(f"**{era}**", "")
            self.table(
                f"SELECT status, {cols}, count(*) AS total FROM r_labeled WHERE era = '{era}' "
                "GROUP BY 1 ORDER BY total DESC",
                ["status", *labels, "total"],
            )
        self.emit(
            "Status × closed date × resolution code. This is the evidence for the terminal-status "
            "proposal in section 11.",
            "",
        )
        self.table(
            "SELECT era, status, count(*) AS n, "
            "round(100 * avg((closed_at IS NOT NULL)::INT), 1), "
            "round(100 * avg((resolution_code IS NOT NULL)::INT), 1) "
            "FROM r GROUP BY 1, 2 ORDER BY 1, n DESC",
            ["era", "status", "rows", "% with closed date", "% with resolution code"],
        )

    def resolution_codes(self) -> None:
        self.emit("## 6. Resolution codes (current era)", "")
        n_codes, n_rows = self.q(
            "SELECT count(DISTINCT resolution_code), count(resolution_code) FROM r "
            "WHERE era = 'current'"
        )[0]
        self.emit(
            f"{n_codes:,} distinct codes on {n_rows:,} rows. Per-code volume, statuses, "
            "departments and types are in `docs/profile/resolution_codes.csv`, the input to "
            "Phase 3 labeling.",
            "",
        )
        self.table(
            "SELECT coalesce(resolution_code, '(null)'), count(*) AS n, "
            "round(100 * count(*) / sum(count(*)) OVER (), 1), "
            "count(*) FILTER (status = 'Closed'), "
            "count(*) FILTER (request_type = 'Information-Only') "
            "FROM r WHERE era = 'current' GROUP BY 1 ORDER BY n DESC LIMIT 25",
            ["code", "rows", "% of current rows", "status Closed", "Information-Only"],
        )
        top = (
            "(SELECT code, string_agg({col} || ' (' || CAST(n AS VARCHAR) || ')', '; ' "
            "ORDER BY n DESC) AS top "
            "FROM (SELECT resolution_code AS code, coalesce({col}, '(none)') AS {col}, "
            "count(*) AS n, row_number() OVER (PARTITION BY resolution_code ORDER BY count(*) "
            "DESC) AS rk FROM r WHERE era = 'current' AND resolution_code IS NOT NULL "
            "GROUP BY 1, 2) WHERE rk <= 3 GROUP BY 1)"
        )
        self.extract(
            "resolution_codes",
            "SELECT b.code, b.n, b.n_2025, b.n_2026, b.pct_closed_within_60s, "
            "s.top AS top_statuses, d.top AS top_departments, t.top AS top_types FROM "
            "(SELECT resolution_code AS code, count(*) AS n, "
            "count(*) FILTER (dataset_id = '73a2-6ar5') AS n_2025, "
            "count(*) FILTER (dataset_id = '2cy6-i7zn') AS n_2026, "
            "round(100 * avg((date_diff('second', created_at, closed_at) BETWEEN 0 AND 60)::INT)"
            ", 1) AS pct_closed_within_60s FROM r WHERE era = 'current' "
            "AND resolution_code IS NOT NULL GROUP BY 1) b "
            f"LEFT JOIN {top.format(col='status')} s USING (code) "
            f"LEFT JOIN {top.format(col='department')} d USING (code) "
            f"LEFT JOIN {top.format(col='request_type')} t USING (code) ORDER BY b.n DESC",
        )
        self.emit(
            "Codes that share a prefix but not a label (map on the full string, never the prefix):",
            "",
        )
        self.table(
            "SELECT split_part(resolution_code, '-', 1) AS prefix, "
            "count(DISTINCT resolution_code), "
            "string_agg(DISTINCT resolution_code, ' · ') FROM r WHERE era = 'current' "
            "AND resolution_code LIKE '%-%' GROUP BY 1 HAVING count(DISTINCT resolution_code) > 1 "
            "ORDER BY 2 DESC, 1",
            ["prefix", "codes", "labels"],
        )
        self.emit('Check on the brief\'s "C-Closed is mostly Information-Only" (2026 cases):', "")
        self.table(
            "SELECT count(*), count(*) FILTER (request_type = 'Information-Only'), "
            "round(100 * avg((request_type = 'Information-Only')::INT), 1) FROM r "
            "WHERE dataset_id = '2cy6-i7zn' AND resolution_code = 'C-Closed'",
            ["C-Closed rows", "…on Information-Only", "%"],
        )

    def null_rates(self) -> None:
        self.emit("## 7. Null rates (% of rows) by unified field", "")
        fields = [
            c
            for c in self.q("DESCRIBE r")
            if c[0] not in ("dataset_id", "era", "created_raw", "closed_raw")
        ]
        names = [c[0] for c in fields]
        cols = ", ".join(f"round(100 * avg(({n} IS NULL)::INT), 1)" for n in names)
        per_dataset = self.q(
            f"SELECT label, {cols} FROM r_labeled GROUP BY label ORDER BY any_value(sort)"
        )
        labels = [row[0] for row in per_dataset]
        transposed = [(name, *[row[i + 1] for row in per_dataset]) for i, name in enumerate(names)]
        self.emit(*md_table(["field", *labels], transposed))

    def types(self) -> None:
        self.emit("## 8. Request types", "")
        legacy_labels = [
            lab for d, lab in self.labels.items() if self.registry.get(d).era == "legacy"
        ]
        cols = ", ".join(f"count(*) FILTER (label = '{lab}')" for lab in legacy_labels)
        self.emit("**Legacy types by dataset**", "")
        self.table(
            f"SELECT request_type, {cols}, count(*) AS total FROM r_labeled WHERE era = 'legacy' "
            "GROUP BY 1 ORDER BY total DESC",
            ["type", *legacy_labels, "total"],
        )
        self.emit(
            "**Current types.** 'Closed ≤60 s' is the share of rows with a closed date where "
            "`closeddate − createddate` is between 0 and 60 seconds. 'Info-like codes' is the "
            "share of coded rows whose code reads as information-only "
            f"(`{INFO_CODE_PATTERN}`).",
            "",
        )
        self.table(
            "SELECT request_type, count(*) FILTER (dataset_id = '73a2-6ar5') AS n_2025, "
            "count(*) FILTER (dataset_id = '2cy6-i7zn') AS n_2026, mode(department), "
            "round(100 * avg((status = 'Closed')::INT), 1), "
            "round(100 * avg((date_diff('second', created_at, closed_at) BETWEEN 0 AND 60)::INT)"
            ", 1), "
            f"round(100 * avg(regexp_matches(resolution_code, '{INFO_CODE_PATTERN}')::INT), 1), "
            "mode(resolution_code) FROM r WHERE era = 'current' GROUP BY 1 "
            "ORDER BY n_2025 + n_2026 DESC",
            [
                "type",
                "2025",
                "2026",
                "main dept",
                "% Closed",
                "% closed ≤60 s",
                "% info-like codes",
                "most common code",
            ],
        )

    def channels(self) -> None:
        self.emit("## 9. Channels", "")
        self.table(
            "SELECT era, coalesce(channel, '(null)'), count(*) AS n, "
            "round(100 * count(*) / sum(count(*)) OVER (PARTITION BY era), 1) "
            "FROM r GROUP BY 1, 2 ORDER BY 1, n DESC",
            ["era", "channel", "rows", "% of era"],
        )

    def overlap(self) -> None:
        self.emit(
            "## 10. The Apr–Aug 2025 overlap",
            "",
            f"The new system started {CUTOVER}. Which legacy rows continue after it, and is the "
            "same work recorded twice?",
            "",
        )
        self.table(
            f"SELECT strftime(created_at, '%Y-%m') AS month, request_type, channel, count(*) AS n "
            f"FROM r WHERE era = 'legacy' AND created_at >= '{CUTOVER}' GROUP BY ALL "
            "ORDER BY month, n DESC",
            ["month", "legacy type", "channel", "rows"],
        )
        self.emit("Graffiti Removal by month and channel in both systems (2025):", "")
        self.table(
            "SELECT strftime(created_at, '%Y-%m') AS month, "
            "count(*) FILTER (era = 'legacy' AND channel = 'Driver Self Report'), "
            "count(*) FILTER (era = 'legacy' AND channel <> 'Driver Self Report'), "
            "count(*) FILTER (era = 'current' AND channel = 'Driver Self Reported'), "
            "count(*) FILTER (era = 'current' AND channel <> 'Driver Self Reported') "
            "FROM r WHERE request_type = 'Graffiti Removal' AND year(created_at) = 2025 "
            "GROUP BY 1 ORDER BY 1",
            [
                "month",
                "legacy: crew self-report",
                "legacy: other",
                "current: crew self-report",
                "current: other",
            ],
        )
        self.emit(
            "Double-recording check: for each post-cutover legacy graffiti row with coordinates, "
            "is there a current-system graffiti case within 50 m created within ±1 day? The "
            "placebo repeats the search 7–9 days away, which estimates how often an unrelated "
            "case is simply nearby.",
            "",
        )
        self.table(
            "WITH l AS (SELECT request_id, created_at, lat, lon FROM r WHERE era = 'legacy' "
            f"AND request_type = 'Graffiti Removal' AND created_at >= '{CUTOVER}' "
            "AND lat BETWEEN 33 AND 35 AND lon BETWEEN -119 AND -117), "
            "c AS (SELECT created_at, lat, lon, floor(lat / 0.0005)::BIGINT AS gy, "
            "floor(lon / 0.0005)::BIGINT AS gx FROM r WHERE era = 'current' "
            "AND request_type = 'Graffiti Removal' AND created_at < '2025-10-01' "
            "AND lat BETWEEN 33 AND 35 AND lon BETWEEN -119 AND -117), "
            "lx AS (SELECT l.*, floor(lat / 0.0005)::BIGINT + dy AS gy, "
            "floor(lon / 0.0005)::BIGINT + dx AS gx "
            "FROM l, range(-1, 2) t1(dy), range(-1, 2) t2(dx)), "
            "pairs AS (SELECT lx.request_id, abs(date_diff('hour', lx.created_at, c.created_at)) "
            "AS hours FROM lx JOIN c USING (gy, gx) WHERE 2 * 6371000 * asin(sqrt("
            "pow(sin(radians(c.lat - lx.lat) / 2), 2) + cos(radians(lx.lat)) * "
            "cos(radians(c.lat)) * pow(sin(radians(c.lon - lx.lon) / 2), 2))) <= 50) "
            "SELECT (SELECT count(*) FROM l), "
            "count(DISTINCT request_id) FILTER (hours <= 24), "
            "count(DISTINCT request_id) FILTER (hours BETWEEN 168 AND 216) FROM pairs",
            [
                "legacy graffiti rows (post-cutover)",
                "with a current case ≤50 m, ±1 day",
                "placebo: ≤50 m, 7–9 days away",
            ],
        )

    def instant_close(self) -> None:
        self.emit(
            "## 12. Time to close (for choosing the instant-close threshold in Phase 3)",
            "",
            "Rows with both timestamps and a non-negative duration, excluding the "
            "non-service types proposed in section 11.",
            "",
        )
        self.table(
            "SELECT label, count(*) AS n, "
            "round(100 * avg((d <= 60)::INT), 1), round(100 * avg((d <= 300)::INT), 1), "
            "round(100 * avg((d <= 900)::INT), 1), round(100 * avg((d <= 3600)::INT), 1), "
            "round(100 * avg((d <= 86400)::INT), 1), round(quantile_cont(d, 0.5) / 3600, 1), "
            "round(quantile_cont(d, 0.9) / 3600, 1) FROM (SELECT label, sort, "
            "date_diff('second', created_at, closed_at) AS d FROM r_labeled "
            f"WHERE request_type NOT IN {sql_in(self.non_service)} AND closed_at >= created_at) "
            "GROUP BY label ORDER BY any_value(sort)",
            [
                "dataset",
                "rows",
                "% ≤1 min",
                "% ≤5 min",
                "% ≤15 min",
                "% ≤1 h",
                "% ≤1 day",
                "median h",
                "p90 h",
            ],
        )

    def special_types(self) -> None:
        self.emit("## 13. Service Not Complete and Information-Only", "")
        self.emit("**Service Not Complete**: department, reason code and resolution code.", "")
        self.table(
            "SELECT department, coalesce(reason_code, '(null)'), count(*) AS n FROM r "
            "WHERE request_type = 'Service Not Complete' GROUP BY 1, 2 ORDER BY n DESC LIMIT 12",
            ["department", "reason code", "rows"],
        )
        self.table(
            "SELECT coalesce(resolution_code, '(null)'), count(*) AS n FROM r "
            "WHERE request_type = 'Service Not Complete' GROUP BY 1 ORDER BY n DESC LIMIT 8",
            ["resolution code", "rows"],
        )
        self.emit("**Information-Only** by dataset, status and code:", "")
        self.table(
            "SELECT label, status, coalesce(resolution_code, '(null)'), count(*) AS n "
            "FROM r_labeled WHERE request_type = 'Information-Only' GROUP BY ALL "
            "ORDER BY any_value(sort), n DESC LIMIT 12",
            ["dataset", "status", "code", "rows"],
        )

    # -- proposals ----------------------------------------------------------------------------

    def proposals(self) -> None:
        self.emit(
            "## 11. Proposals for sign-off",
            "",
            "These become dbt seeds in Phase 2 after review. Evidence is in the sections above.",
            "",
            "### 11a. Non-service types",
            "",
            "Candidates: any current type where at least 80% of closed rows close within 60 "
            "seconds or at least 50% of coded rows carry information-only codes, plus the brief's "
            "list. The proposed list is a judgment on this evidence (each with a reason), not a "
            'mechanical rule: Information-Only is coded with the generic "C-Closed", so code '
            "labels alone would miss it.",
            "",
        )
        candidates = self.q(
            "SELECT request_type, count(*) AS n, "
            "round(100 * avg((date_diff('second', created_at, closed_at) BETWEEN 0 AND 60)::INT)"
            ", 1) AS instant, "
            f"round(100 * avg(regexp_matches(resolution_code, '{INFO_CODE_PATTERN}')::INT), 1) "
            "AS info, mode(resolution_code) FROM r WHERE era = 'current' GROUP BY 1 "
            "HAVING instant >= 80 OR info >= 50 "
            f"OR request_type IN {sql_in(list(PROPOSED_NON_SERVICE))} ORDER BY n DESC"
        )
        self.non_service = sorted(PROPOSED_NON_SERVICE)
        self.emit(
            *md_table(
                [
                    "current type",
                    "rows",
                    "% closed ≤60 s",
                    "% info-like codes",
                    "most common code",
                    "proposed",
                    "why",
                ],
                [
                    (*row, row[0] in PROPOSED_NON_SERVICE, PROPOSED_NON_SERVICE.get(row[0]))
                    for row in candidates
                ],
            )
        )
        self.emit(
            f"Proposed non-service list: {', '.join(self.non_service)}.",
            "",
            "### 11b. Terminal statuses",
            "",
            "Proposed rule: a status is terminal if at least 99% of its rows carry a closed date.",
            "",
        )
        statuses = self.q(
            "SELECT era, status, count(*) AS n, round(100 * avg((closed_at IS NOT NULL)::INT), 1) "
            "AS pct FROM r GROUP BY 1, 2 ORDER BY 1, n DESC"
        )
        self.terminal = {(era, s) for era, s, n, pct in statuses if pct >= 99}
        self.emit(
            *md_table(
                ["era", "status", "rows", "% with closed date", "proposed terminal"],
                [(*row, (row[0], row[1]) in self.terminal) for row in statuses],
            )
        )
        self.emit(
            "### 11c. Type crosswalk",
            "",
            "The brief's guesses, checked by volume either side of the cutover. 'Legacy/mo' "
            "averages Jan–Feb 2025 (whole months before the cutover); 'current/mo' averages "
            "May–Jun 2025. The same legacy months in 2024 show the seasonal baseline.",
            "",
        )
        rows = []
        for category, legacy_types, current_types in CROSSWALK_GUESSES:
            row = self.q(
                "SELECT "
                f"count(*) FILTER (era = 'legacy' AND request_type IN {sql_in(legacy_types)} "
                "AND created_at >= '2025-01-01' AND created_at < '2025-03-01') / 2, "
                f"count(*) FILTER (era = 'current' AND request_type IN {sql_in(current_types)} "
                "AND created_at >= '2025-05-01' AND created_at < '2025-07-01') / 2, "
                f"count(*) FILTER (era = 'legacy' AND request_type IN {sql_in(legacy_types)} "
                "AND created_at >= '2024-05-01' AND created_at < '2024-07-01') / 2, "
                "mode(department) FILTER (era = 'legacy' "
                f"AND request_type IN {sql_in(legacy_types)}), "
                "mode(department) FILTER (era = 'current' "
                f"AND request_type IN {sql_in(current_types)}) "
                "FROM r"
            )[0]
            rows.append((category, " + ".join(legacy_types), " + ".join(current_types), *row))
        self.emit(
            *md_table(
                [
                    "category",
                    "legacy types",
                    "current types",
                    "legacy/mo (Jan–Feb 2025)",
                    "current/mo (May–Jun 2025)",
                    "legacy/mo (May–Jun 2024)",
                    "legacy dept",
                    "current dept",
                ],
                rows,
            )
        )
        self.emit("Other current types with streetlight, dumping or pickup in the name:", "")
        self.table(
            "SELECT request_type, count(*) AS n, mode(department) FROM r WHERE era = 'current' "
            "AND regexp_matches(request_type, 'Streetlight|Dumping|Pickup|Bulky') "
            "GROUP BY 1 ORDER BY n DESC",
            ["current type", "rows", "main dept"],
        )

    # -- report -------------------------------------------------------------------------------

    def run(self) -> Path:
        pulled = sorted(m["pulled_at"] for m in self.manifest.values())
        self.emit(
            "# Data profile (Phase 1)",
            "",
            "Generated by `ingest/profile.py` (`make profile`) from the raw pulls in "
            f"`data/raw/`, pulled {pulled[0]} to {pulled[-1]} (UTC). Every number below is "
            "computed by that script; regenerate rather than edit. Quirks and their "
            "interpretation are in `docs/DATA_NOTES.md`.",
            "",
        )
        self.inventory()
        self.monthly()
        self.duplicates()
        self.timestamps()
        self.statuses()
        self.resolution_codes()
        self.null_rates()
        self.types()
        self.channels()
        self.overlap()
        self.proposals()
        self.instant_close()
        self.special_types()
        self.emit(f"_Generated {datetime.now(UTC).isoformat(timespec='seconds')}._", "")
        path = self.docs_dir / "PROFILE.md"
        path.write_text("\n".join(self.lines))
        return path


def mapping_of(spec: dict, unified: str, era: str) -> str:
    return spec[unified][era]
