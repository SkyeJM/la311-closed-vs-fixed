from ingest.config import Dataset, Registry
from ingest.discover import classify

REGISTRY = Registry(
    domain="data.lacity.org",
    datasets=(Dataset(id="aaaa-0001", name="MyLA311 Cases 2026", era="current", year=2026),),
    ignored={"bbbb-0002": "derived view"},
)


def hit(dataset_id: str, name: str) -> dict:
    return {
        "resource": {
            "id": dataset_id,
            "name": name,
            "type": "filter",
            "data_updated_at": "2026-10-23T00:00:00.000Z",
        }
    }


def test_labels_registered_ignored_and_new_and_skips_non_311():
    results = [
        hit("aaaa-0001", "MyLA311 Cases 2026"),
        hit("bbbb-0002", "MyLA311 Streetlight Service Request Data"),
        hit("cccc-0003", "MyLA311 Cases 2027"),
        hit("dddd-0004", "Building Permits"),
        hit("cccc-0003", "MyLA311 Cases 2027"),  # same id from a second search term
    ]
    hits = classify(results, REGISTRY)
    assert {h.id: h.status for h in hits} == {
        "aaaa-0001": "registered",
        "bbbb-0002": "ignored",
        "cccc-0003": "new",
    }
    assert hits[0].id == "cccc-0003"  # new datasets sort first
    assert hits[0].updated_at == "2026-10-23"
