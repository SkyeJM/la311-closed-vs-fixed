"""Hosting spike app: read-only DuckDB queries plus a long SSE stream, on synthetic data only.

Deployed as a throwaway Vercel project from this directory. The build step (pyproject.toml)
generates serving_synthetic.duckdb, so no large file is uploaded.

    /health   bundle check: file size, open time, process uptime (cold vs warm)
    /query    a dashboard-style aggregate, timed
    /stream   SSE: one event every `every` seconds for `seconds` seconds
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

PROCESS_STARTED = time.perf_counter()
DB_PATH = Path(__file__).resolve().parent / "serving_synthetic.duckdb"
STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    con = duckdb.connect(
        str(DB_PATH),
        read_only=True,
        config={"threads": 1, "memory_limit": "1GB", "temp_directory": "/tmp/duckdb"},
    )
    # Order matters in DuckDB 2.x: once external access is off, temp_directory can't be set,
    # and lock_configuration stops any later SQL from loosening these settings.
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    STATE["con"] = con
    STATE["open_ms"] = round((time.perf_counter() - started) * 1000, 1)
    yield
    STATE["con"].close()


app = FastAPI(lifespan=lifespan)


def uptime() -> float:
    return round(time.perf_counter() - PROCESS_STARTED, 2)


@app.get("/health")
def health() -> dict:
    return {
        "db_mb": round(DB_PATH.stat().st_size / 1e6, 1),
        "open_ms": STATE.get("open_ms"),
        "uptime_s": uptime(),
        "duckdb": duckdb.__version__,
    }


@app.get("/query")
def query() -> dict:
    started = time.perf_counter()
    rows = (
        STATE["con"]
        .cursor()
        .execute(
            "SELECT date_trunc('month', created_at) AS m, outcome_id, count(*) FROM fct "
            "WHERE era = 'current' AND category_id = 3 GROUP BY ALL ORDER BY ALL"
        )
        .fetchall()
    )
    return {
        "rows": len(rows),
        "query_ms": round((time.perf_counter() - started) * 1000, 1),
        "uptime_s": uptime(),
    }


@app.get("/stream")
async def stream(seconds: float = 110, every: float = 5) -> StreamingResponse:
    async def events():
        started = time.perf_counter()
        i = 0
        while (elapsed := time.perf_counter() - started) < seconds:
            yield f"data: {json.dumps({'i': i, 't': round(elapsed, 1)})}\n\n"
            i += 1
            await asyncio.sleep(every)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
