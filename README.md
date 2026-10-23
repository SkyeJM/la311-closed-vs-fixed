# Closed ≠ Fixed

When Los Angeles's MyLA311 system marks a service request "Closed," how often was the problem
actually fixed? And did the March 2025 MyLA311 relaunch change what "closed" means?

**Status:** work in progress. Phase 0 (setup and data verification) is done. Findings will appear
here once they're computed from code; this README won't quote a number until then.

Unofficial project, not affiliated with the City of Los Angeles. Data: the City's MyLA311 open
datasets on [data.lacity.org](https://data.lacity.org) (CC0).

## Run it

Requires [uv](https://docs.astral.sh/uv/) and make.

```sh
make setup           # Python 3.12 env + git hooks
make check           # lint + offline tests
make discover        # list 311 datasets on the portal; fails if one isn't registered
make schema-check    # fail if any dataset's columns or saved filter changed
make ingest-sample   # pull ~10K-row samples of five datasets to data/samples/
```

Design notes live in [`docs/DECISIONS.md`](docs/DECISIONS.md) and data quirks in
[`docs/DATA_NOTES.md`](docs/DATA_NOTES.md).
