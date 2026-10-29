"""Publish data/serving.duckdb as a GitHub Release asset and pin it for deploys.

    make release-data

The serving file is the only data the deployed API reads, and it holds nothing that can locate
a person (api/serving.py is the allowlist and checks it on every build). It is too big for git,
so each data refresh becomes a release named after the data's last day, and
deploy/api/serving.json pins its URL and SHA-256 for the Vercel build (deploy/api/build.py).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SERVING = ROOT / "data" / "serving.duckdb"
PIN = ROOT / "deploy" / "api" / "serving.json"
REPO = "SkyeJM/la311-closed-vs-fixed"


def main() -> None:
    con = duckdb.connect(str(SERVING), read_only=True)
    data_end = con.execute("select max(created_at) from fct_current_requests").fetchone()[0]
    con.close()
    digest = hashlib.sha256(SERVING.read_bytes()).hexdigest()
    tag = f"data-{data_end:%Y-%m-%d}"
    exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
    if exists:
        sys.exit(f"release {tag} already exists; delete it or wait for newer data")
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            str(SERVING),
            "--title",
            f"Serving data through {data_end:%Y-%m-%d}",
            "--notes",
            "Aggregated marts and the slim current-era fact table the deployed API reads "
            f"(no addresses, coordinates, IDs or crew fields). SHA-256 {digest}. Built from "
            "public CC0 data from data.lacity.org.",
            "--latest=false",
        ],
        check=True,
    )
    pin = {
        "url": f"https://github.com/{REPO}/releases/download/{tag}/serving.duckdb",
        "sha256": digest,
        "bytes": SERVING.stat().st_size,
        "data_end": data_end.isoformat(),
        "tag": tag,
    }
    PIN.write_text(json.dumps(pin, indent=1) + "\n")
    print(f"{tag}: {pin['bytes'] / 1e6:.1f} MB pinned in {PIN.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
