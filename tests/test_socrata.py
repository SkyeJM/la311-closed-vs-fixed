import httpx
import pytest
from tenacity import wait_none

from ingest.socrata import SocrataClient


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(SocrataClient.get.retry, "wait", wait_none())


def client_with(handler, **kwargs) -> SocrataClient:
    return SocrataClient("example.org", transport=httpx.MockTransport(handler), **kwargs)


def test_retries_transient_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"id": "abcd"})

    with client_with(handler) as client:
        assert client.view_metadata("abcd") == {"id": "abcd"}
    assert len(calls) == 3


def test_does_not_retry_client_errors():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403)

    with client_with(handler) as client, pytest.raises(httpx.HTTPStatusError):
        client.view_metadata("qdp3-rdjj")
    assert len(calls) == 1


def test_gives_up_after_six_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    with client_with(handler) as client, pytest.raises(httpx.HTTPStatusError):
        client.view_metadata("abcd")
    assert len(calls) == 6


def test_sends_app_token_when_configured():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={})

    with client_with(handler, app_token="secret-token") as client:
        client.view_metadata("abcd")
    assert seen["x-app-token"] == "secret-token"


def test_catalog_search_paginates():
    pages = {0: [{"n": 1}, {"n": 2}], 2: [{"n": 3}]}

    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json={"results": pages.get(offset, []), "resultSetSize": 3})

    with client_with(handler) as client:
        assert [r["n"] for r in client.catalog_search("MyLA311", page_size=2)] == [1, 2, 3]
