"""The API's deploy package: pinned runtime requirements and a complete runtime copy."""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "api"
EXPORT = [
    "uv",
    "export",
    "--frozen",
    "--no-default-groups",
    "--no-hashes",
    "--no-emit-project",
    "--format",
    "requirements-txt",
]


def test_deploy_requirements_match_the_lockfile():
    """`make deploy-requirements` regenerates the file; it must never drift from uv.lock."""
    exported = subprocess.run(EXPORT, cwd=ROOT, capture_output=True, text=True, check=True)
    assert (DEPLOY / "requirements.txt").read_text() == exported.stdout
    assert "dbt-core" not in exported.stdout  # build-time only


def test_the_runtime_copy_is_complete(tmp_path):
    spec = importlib.util.spec_from_file_location("deploy_build", DEPLOY / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    build.HERE = tmp_path
    build.copy_runtime()
    (tmp_path / "main.py").write_text((DEPLOY / "main.py").read_text())
    probe = (
        "import main\n"
        "from ai.agent import charts, prompt\n"
        "from api import app, metrics, suggested\n"
        "files = [prompt.TEMPLATE, prompt.OUTCOMES, charts.SCHEMA_FILE, metrics.METRICS_FILE,\n"
        "         app.FINDINGS, suggested.CACHE]\n"
        "missing = [str(f) for f in files if not f.exists()]\n"
        "assert not missing, missing\n"
        f"assert all(str(f).startswith({str(tmp_path)!r}) for f in files)\n"
    )
    run = subprocess.run(
        [sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr[-2000:]
