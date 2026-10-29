"""Vercel build step for the API service (vercel.json → services.api.buildCommand).

A Vercel service bundles only its own root, and the API's code and definitions live at the repo
root. This copies exactly the runtime set into this directory, then downloads the serving
database pinned in serving.json (a GitHub Release asset) and checks its SHA-256, so a deploy
never ships a data file nobody has checked. Standard library only: it runs before anything else.

    python build.py            # from deploy/api, as Vercel runs it
    python build.py --local    # copy data/serving.duckdb from the repo instead of downloading
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME = [
    "api",
    "ai/__init__.py",
    "ai/pricing.py",
    "ai/agent",
    "findings/__init__.py",
    "findings/build.py",
    "findings/findings.json",
    "metrics.yml",
    "dbt/seeds/closure_outcomes.csv",
]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "__main__.py")


def copy_runtime() -> None:
    for item in RUNTIME:
        src, dest = REPO / item, HERE / item
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, ignore=SKIP)
        else:
            shutil.copy2(src, dest)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_data(local: bool) -> None:
    pin = json.loads((HERE / "serving.json").read_text())
    dest = HERE / "data" / "serving.duckdb"
    dest.parent.mkdir(exist_ok=True)
    if local:
        shutil.copy2(REPO / "data" / "serving.duckdb", dest)
    else:
        with urllib.request.urlopen(pin["url"], timeout=120) as response, dest.open("wb") as f:
            shutil.copyfileobj(response, f, length=1 << 20)
    actual = sha256(dest)
    if actual != pin["sha256"]:
        dest.unlink()
        sys.exit(f"serving.duckdb checksum {actual} doesn't match the pin {pin['sha256']}")
    print(f"serving.duckdb: {dest.stat().st_size / 1e6:.1f} MB, data through {pin['data_end']}")


if __name__ == "__main__":
    copy_runtime()
    fetch_data(local="--local" in sys.argv)
