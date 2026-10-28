"""Shared fixtures: one dbt build on synthetic data per test session, and its serving file."""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from api import serving
from tests.fixtures.synthetic_raw import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def dbt_build(tmp_path_factory):
    """(read-only warehouse connection, dbt build log, temp dir) for the synthetic fixtures."""
    tmp = tmp_path_factory.mktemp("dbt")
    build(tmp / "raw")
    env = os.environ | {
        "LA311_RAW_ROOT": str(tmp / "raw"),
        "LA311_WAREHOUSE": str(tmp / "warehouse.duckdb"),
    }
    dbt = str(Path(sys.executable).parent / "dbt")
    paths = ["--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs")]
    subprocess.run([dbt, "deps", "--quiet"], cwd=ROOT / "dbt", env=env, check=True)
    run = subprocess.run(
        [dbt, "build", *paths], cwd=ROOT / "dbt", env=env, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout[-4000:]
    con = duckdb.connect(str(tmp / "warehouse.duckdb"), read_only=True)
    yield con, run.stdout, tmp
    con.close()


@pytest.fixture(scope="session")
def serving_db(dbt_build):
    """A read-only connection to serving.duckdb built from the fixture warehouse."""
    dest = dbt_build[2] / "serving.duckdb"
    serving.build(dbt_build[2] / "warehouse.duckdb", dest)
    con = duckdb.connect(str(dest), read_only=True)
    yield con
    con.close()
