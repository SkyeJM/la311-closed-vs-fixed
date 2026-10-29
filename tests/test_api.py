"""The FastAPI app offline: data endpoints, and /api/ask's guards, stream, cache and traces.

The agent runs against a scripted client on the fixture serving file, so nothing here calls
the Anthropic API.
"""

import json

import pytest
from fastapi.testclient import TestClient

from ai.agent.loop import Agent, Settings
from api import app as api
from api import db, guards, suggested
from tests.agent_fakes import FakeClient, final, gap_answer, metric_call, reply, tool_turn

pytestmark = pytest.mark.dbt


@pytest.fixture
def client(agent_db, monkeypatch, tmp_path):
    monkeypatch.setattr(db, "shared", lambda: agent_db)
    monkeypatch.setenv("TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # never used: the client is scripted
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "2")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("ASK_ENABLED", raising=False)
    caches = (api.guard, api.agent, api.data_end, suggested.load)
    for cached in caches:
        cached.cache_clear()
    yield TestClient(api.app)
    for cached in caches:  # the originals: tests may have patched the names
        cached.cache_clear()


def scripted(monkeypatch, agent_db, *turns):
    fake = FakeClient(list(turns))
    agent = Agent(fake, agent_db, Settings(model="claude-haiku-5-5"), budget=api.guard())
    monkeypatch.setattr(api, "agent", lambda: agent)
    return fake


def events(response) -> list[dict]:
    out = []
    for block in response.text.strip().split("\n\n"):
        data = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            out.append(json.loads("".join(data)))
    return out


def traces(tmp_path) -> list[dict]:
    lines = []
    for path in (tmp_path / "traces").glob("*.jsonl"):
        lines += [json.loads(line) for line in path.read_text().splitlines()]
    return lines


def test_health_and_catalog(client):
    health = client.get("/api/health").json()
    assert health["ok"] and health["ask_enabled"] and health["data_end"]
    catalog = client.get("/api/metrics").json()
    assert any(m["name"] == "verified_fix_rate" for m in catalog["metrics"])
    assert client.get("/api/codes").json()["codes"]
    assert "headline" in client.get("/api/findings").json()


def test_metric_queries_are_governed_and_show_their_sql(client):
    body = {
        "metric": "closure_rate",
        "group_by": ["unified_category"],
        "filters": {"era": ["current"]},
    }
    result = client.post("/api/metrics/query", json=body).json()
    assert result["sql"].startswith("with grouped") and result["rows"]
    bad = client.post(
        "/api/metrics/query", json={"metric": "closure_rate", "group_by": ["address"]}
    )
    assert bad.status_code == 400


def test_ask_streams_the_agent_and_writes_a_trace(client, monkeypatch, agent_db, tmp_path):
    scripted(
        monkeypatch,
        agent_db,
        tool_turn(("query_metric", metric_call("closed_fixed_gap_pp"))),
        final(gap_answer()),
    )
    response = client.post(
        "/api/ask",
        json={"question": "What is the gap? Email me at jo@example.com"},
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    assert response.status_code == 200
    streamed = events(response)
    assert [e["type"] for e in streamed][-2:] == ["answer", "done"]
    assert len({e["trace_id"] for e in streamed}) == 1
    (trace,) = traces(tmp_path)
    assert trace["outcome"] == "answered" and trace["tool_calls"][0]["sql"]
    assert "[email]" in trace["question"] and "jo@example.com" not in json.dumps(trace)
    assert "203.0.113.9" not in json.dumps(trace) and len(trace["ip_hash"]) == 16


def test_the_rate_limit_counts_live_questions_per_ip(client, monkeypatch, agent_db):
    plain = reply(answer_markdown="No numbers here.", key_numbers=[], query_ids=[])
    scripted(monkeypatch, agent_db, *[final(plain)] * 3)
    asks = [client.post("/api/ask", json={"question": "Anything new?"}) for _ in range(3)]
    assert [r.status_code for r in asks] == [200, 200, 429]
    assert int(asks[2].headers["retry-after"]) > 0


def test_the_kill_switch_and_the_daily_cap(client, monkeypatch):
    monkeypatch.setenv("ASK_ENABLED", "false")
    api.guard.cache_clear()
    assert client.post("/api/ask", json={"question": "Anything?"}).status_code == 503
    monkeypatch.setenv("ASK_ENABLED", "true")
    api.guard.cache_clear()
    api.guard().add(api.guard().policy.daily_cap_usd)
    refused = client.post("/api/ask", json={"question": "Anything?"})
    assert refused.status_code == 503 and "budget" in refused.json()["detail"]


def test_suggested_questions_replay_from_the_cache(client, monkeypatch):
    stored = [{"type": "start"}, {"type": "answer", "answer": {}}, {"type": "done"}]
    question = suggested.SUGGESTED[0]
    monkeypatch.setattr(
        suggested,
        "load",
        lambda: {"data_end": api.data_end(), "answers": {suggested.normalize(question): stored}},
    )
    monkeypatch.setenv("ASK_ENABLED", "false")  # the cache works even with live Ask off
    api.guard.cache_clear()
    response = client.post("/api/ask", json={"question": question.upper()})
    assert response.status_code == 200
    assert all(e["cached"] for e in events(response))


def test_production_needs_a_shared_store_and_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("VERCEL", raising=False)
    assert guards.Policy.from_env(guards.MemoryStore()).enabled
    monkeypatch.setenv("VERCEL", "1")
    assert not guards.Policy.from_env(guards.MemoryStore()).enabled
    monkeypatch.delenv("VERCEL")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    policy = guards.Policy.from_env(guards.MemoryStore())
    assert not policy.enabled and "API key" in policy.disabled_reason


def test_feedback_is_logged(client, tmp_path):
    ok = client.post("/api/feedback", json={"trace_id": "abc123def456", "rating": "down"})
    assert ok.json() == {"ok": True}
    assert traces(tmp_path)[0]["kind"] == "feedback"


class FakeRedis:
    """Just enough of Upstash's REST pipeline for the store: SET NX EX, INCRBYFLOAT, GET."""

    def __init__(self):
        self.values = {}
        self.ttls = {}

    def handle(self, request):
        import httpx

        assert request.headers["authorization"] == "Bearer token"
        results = []
        for command, key, *args in json.loads(request.content):
            if command == "SET":
                if key not in self.values:
                    self.values[key] = args[0]
                    self.ttls[key] = int(args[2])
                results.append({"result": "OK"})
            elif command == "INCRBYFLOAT":
                self.values[key] = str(float(self.values.get(key, "0")) + float(args[0]))
                results.append({"result": self.values[key]})
            elif command == "GET":
                results.append({"result": self.values.get(key)})
        return httpx.Response(200, json=results)


def test_the_upstash_store_counts_with_an_expiry():
    import httpx

    redis = FakeRedis()
    client = httpx.Client(
        transport=httpx.MockTransport(redis.handle), headers={"Authorization": "Bearer token"}
    )
    store = guards.UpstashStore("https://example.upstash.io", "token", client=client)
    assert store.get("k") == 0.0
    assert store.incr("k", 1, 3600) == 1.0
    assert store.incr("k", 0.25, 60) == 1.25
    assert redis.ttls["k"] == 3600  # the first expiry holds
    assert store.get("k") == 1.25


def test_a_dead_store_fails_closed(monkeypatch):
    class Down(guards.Store):
        shared = True

        def incr(self, key, amount, ttl_s):
            raise ConnectionError("down")

        def get(self, key):
            raise ConnectionError("down")

    g = guards.Guards(Down(), guards.Policy(ip_salt="s"))
    with pytest.raises(guards.StoreUnavailable):
        g.take_question("abc")
    with pytest.raises(Exception, match="paused"):
        g.check()
    g.add(0.01)  # recording spend never raises


def test_the_store_comes_from_the_environment(monkeypatch):
    for name in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(guards.store_from_env(), guards.MemoryStore)
    monkeypatch.setenv("KV_REST_API_URL", "https://example.upstash.io")
    monkeypatch.setenv("KV_REST_API_TOKEN", "token")
    assert isinstance(guards.store_from_env(), guards.UpstashStore)
