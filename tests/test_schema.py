from ingest.schema import diff_pins, load_pin, pin_from_metadata, save_pin

META = {
    "id": "abcd-1234",
    "name": "Test view",
    "modifyingViewUid": "pppp-0000",
    "queryString": 'SELECT `a`, `b` WHERE caseless_one_of(`type`, "X")',
    "columns": [
        {"fieldName": "a", "dataTypeName": "text", "name": "A"},
        {"fieldName": "b", "dataTypeName": "number", "name": "B"},
    ],
}


def test_identical_metadata_has_no_drift():
    assert diff_pins(pin_from_metadata(META), pin_from_metadata(META)) == []


def test_filter_hash_ignores_whitespace_only_changes():
    reformatted = {**META, "queryString": META["queryString"].replace(" ", "\n  ")}
    assert pin_from_metadata(reformatted)["filter_hash"] == pin_from_metadata(META)["filter_hash"]


def test_detects_every_kind_of_drift():
    live = {
        **META,
        "queryString": 'SELECT `a`, `c` WHERE caseless_one_of(`type`, "X", "Y")',
        "columns": [
            {"fieldName": "a", "dataTypeName": "number", "name": "A2"},
            {"fieldName": "c", "dataTypeName": "text", "name": "C"},
        ],
    }
    problems = diff_pins(pin_from_metadata(META), pin_from_metadata(live))
    assert "column removed: b" in problems
    assert "column added: c (text)" in problems
    assert "type changed: a text -> number" in problems
    assert "display name changed: a 'A' -> 'A2'" in problems
    assert any(p.startswith("saved filter changed") for p in problems)


def test_pin_round_trips(tmp_path):
    pin = pin_from_metadata(META)
    save_pin(pin, tmp_path)
    assert load_pin("abcd-1234", tmp_path) == pin
