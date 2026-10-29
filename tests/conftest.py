"""Shared fixtures: one dbt build on synthetic data per test session, and its serving file."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from api import db, serving
from tests.fixtures.synthetic_raw import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def dbt_build(tmp_path_factory):
    """(read-only warehouse connection, dbt build log, temp dir, final-map check) for the
    synthetic fixtures.

    The fixtures plant an unmapped resolution code, so they build with code_map_final false.
    The final-map check then reruns the mapping test as the real project does (true), which
    must fail on that code: the brief's alerting. It runs before the read-only connection
    opens, because dbt needs the database file to itself.
    """
    tmp = tmp_path_factory.mktemp("dbt")
    build(tmp / "raw")
    env = os.environ | {
        "LA311_RAW_ROOT": str(tmp / "raw"),
        "LA311_WAREHOUSE": str(tmp / "warehouse.duckdb"),
    }
    dbt = str(Path(sys.executable).parent / "dbt")
    paths = ["--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs")]

    def run_dbt(*args):
        return subprocess.run(
            [dbt, *args, *paths], cwd=ROOT / "dbt", env=env, capture_output=True, text=True
        )

    subprocess.run([dbt, "deps", "--quiet"], cwd=ROOT / "dbt", env=env, check=True)
    run = run_dbt("build", "--vars", "{code_map_final: false}")
    assert run.returncode == 0, run.stdout[-4000:]
    final_map = run_dbt(
        "test", "--select", "assert_all_resolution_codes_mapped", "--vars", "{code_map_final: true}"
    )
    con = duckdb.connect(str(tmp / "warehouse.duckdb"), read_only=True)
    yield con, run.stdout, tmp, final_map
    con.close()


@pytest.fixture(scope="session")
def serving_db(dbt_build):
    """A read-only connection to serving.duckdb built from the fixture warehouse."""
    dest = dbt_build[2] / "serving.duckdb"
    serving.build(dbt_build[2] / "warehouse.duckdb", dest)
    con = duckdb.connect(str(dest), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def agent_db(serving_db, dbt_build):
    """The fixture serving file behind the API's lockdown (api/db.py). A copy, because DuckDB
    won't open one file twice in a process with different settings."""
    dest = dbt_build[2] / "agent_serving.duckdb"
    shutil.copy(dbt_build[2] / "serving.duckdb", dest)
    con = db.connect(dest)
    yield con
    con.close()
