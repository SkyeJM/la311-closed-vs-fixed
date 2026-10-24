"""`python -m ingest`: discover, pin, check, sample, pull and refresh MyLA311 datasets."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import typer

from ingest import discover as discovery
from ingest.config import RAW_DIR, ROOT, SAMPLES_DIR, Dataset, load_registry
from ingest.profile import Profiler
from ingest.pull import pull_full, refresh_incremental
from ingest.sample import pull_sample
from ingest.schema import diff_pins, load_pin, pin_from_metadata, save_pin
from ingest.socrata import SocrataClient

app = typer.Typer(
    help="Ingest MyLA311 open data from data.lacity.org.",
    no_args_is_help=True,
    add_completion=False,
)

Sources = Annotated[
    list[str] | None, typer.Option("--source", "-s", help="Dataset id; repeat for several.")
]
AllSources = Annotated[bool, typer.Option("--all", help="Every dataset in sources.yml.")]


def _selected(source: list[str] | None, all_: bool) -> list[Dataset]:
    registry = load_registry()
    if all_:
        return list(registry.datasets)
    if not source:
        raise typer.BadParameter("pass --source ID (repeatable) or --all")
    return [registry.get(dataset_id) for dataset_id in source]


def _fail_on_drift(dataset: Dataset, live_pin: dict) -> None:
    problems = diff_pins(load_pin(dataset.id), live_pin)
    if problems:
        typer.secho(f"{dataset.id} ({dataset.name}) drifted from its pin:", fg="red", err=True)
        for problem in problems:
            typer.secho(f"  - {problem}", fg="red", err=True)
        typer.secho("Review the change, then `make pin` to accept it.", fg="red", err=True)
        raise typer.Exit(1)


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.INFO if verbose else logging.WARNING)


@app.command()
def discover() -> None:
    """List 311 datasets on the portal; exit 1 if any is neither registered nor ignored."""
    registry = load_registry()
    with SocrataClient(registry.domain) as client:
        results = [r for term in discovery.SEARCH_TERMS for r in client.catalog_search(term)]
    hits = discovery.classify(results, registry)
    for hit in hits:
        typer.echo(f"{hit.status:<10}  {hit.id}  {hit.asset_type:<8}  {hit.updated_at}  {hit.name}")
    for dataset_id in sorted({d.id for d in registry.datasets} - {h.id for h in hits}):
        typer.secho(f"warning: registered dataset {dataset_id} is not in the catalog", fg="yellow")
    new = [h for h in hits if h.status == "new"]
    if new:
        typer.secho(
            f"{len(new)} unregistered dataset(s): add each to sources.yml (datasets or ignored).",
            fg="red",
        )
        raise typer.Exit(1)


@app.command()
def pin(source: Sources = None, all_: AllSources = False) -> None:
    """Pin each dataset's live columns and saved filter. Do this only after reviewing drift."""
    datasets = _selected(source, all_)
    with SocrataClient(load_registry().domain) as client:
        for dataset in datasets:
            path = save_pin(pin_from_metadata(client.view_metadata(dataset.id)))
            typer.echo(f"pinned {dataset.id} -> {path.relative_to(ROOT)}")


@app.command("schema-check")
def schema_check(source: Sources = None, all_: AllSources = False) -> None:
    """Compare live metadata with the pins; exit 1 on any column or saved-filter drift."""
    drifted = 0
    with SocrataClient(load_registry().domain) as client:
        for dataset in _selected(source, all_):
            try:
                _fail_on_drift(dataset, pin_from_metadata(client.view_metadata(dataset.id)))
                typer.echo(f"ok  {dataset.id}  {dataset.name}")
            except typer.Exit:
                drifted += 1
    if drifted:
        raise typer.Exit(1)


@app.command()
def sample(
    source: Sources = None,
    all_: AllSources = False,
    n: Annotated[int, typer.Option(help="Approximate rows per dataset.")] = 10_000,
) -> None:
    """Pull ~n-row random-cluster samples to data/samples/ (fails on schema drift)."""
    datasets = _selected(source, all_)
    with SocrataClient(load_registry().domain) as client:
        for dataset in datasets:
            live_pin = pin_from_metadata(client.view_metadata(dataset.id))
            _fail_on_drift(dataset, live_pin)
            manifest = pull_sample(client, dataset, n, SAMPLES_DIR, live_pin)
            typer.echo(
                f"{dataset.id}: {manifest['rows']:,} rows over {len(manifest['rows_by_month'])} "
                f"months -> {(SAMPLES_DIR / manifest['file']).relative_to(ROOT)}"
            )


@app.command()
def pull(
    source: Sources = None,
    all_: AllSources = False,
    workers: Annotated[int, typer.Option(help="Datasets downloaded at once.")] = 3,
    keep_csv: Annotated[bool, typer.Option(help="Keep the downloaded export CSV.")] = False,
) -> None:
    """Full pull via the bulk export to data/raw/{id}/full.parquet (fails on schema drift)."""
    datasets = _selected(source, all_)
    with SocrataClient(load_registry().domain) as client:
        live_pins = {}
        for dataset in datasets:  # check every dataset before downloading anything
            live_pins[dataset.id] = pin_from_metadata(client.view_metadata(dataset.id))
            _fail_on_drift(dataset, live_pins[dataset.id])

        def run(dataset: Dataset) -> dict:
            return pull_full(client, dataset, live_pins[dataset.id], RAW_DIR, keep_csv)

        with ThreadPoolExecutor(workers) as pool:
            for m in pool.map(run, datasets):
                diff = m["live_count_after_pull"] - m["rows"]
                check = "matches live count" if diff == 0 else f"live count differs by {diff:+,}"
                typer.secho(
                    f"{m['dataset_id']}: {m['rows']:,} rows ({check}), "
                    f"{m['csv_bytes'] / 1e6:,.0f} MB CSV in {m['seconds']:,.0f} s",
                    fg=None if diff == 0 else "yellow",
                )


@app.command()
def refresh(
    source: Sources = None,
    overlap_days: Annotated[
        int, typer.Option(help="Re-read this many days before the watermark.")
    ] = 3,
) -> None:
    """Incremental refresh of `refresh: incremental` datasets via the row API (systemmodstamp)."""
    registry = load_registry()
    datasets = (
        [registry.get(s) for s in source]
        if source
        else [d for d in registry.datasets if d.refresh == "incremental"]
    )
    with SocrataClient(registry.domain) as client:
        for dataset in datasets:
            live_pin = pin_from_metadata(client.view_metadata(dataset.id))
            _fail_on_drift(dataset, live_pin)
            delta = refresh_incremental(client, dataset, live_pin, RAW_DIR, overlap_days)["deltas"][
                -1
            ]
            typer.echo(
                f"{dataset.id}: {delta['rows']:,} rows modified since {delta['since']} "
                f"(watermark {delta['watermark']}) -> {delta['file']}"
            )


@app.command()
def profile() -> None:
    """Write docs/PROFILE.md and docs/profile/*.csv from the raw pulls (aggregates only)."""
    path = Profiler(RAW_DIR).run()
    typer.echo(f"wrote {path.relative_to(ROOT)}")
