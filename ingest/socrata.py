"""Small Socrata (SODA 2.x) client: view metadata, catalog search, and SoQL queries as CSV.

Transient failures (network errors, HTTP 429 and 5xx) are retried with exponential backoff and
jitter. Client errors such as 403 (private views) fail immediately.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ingest.config import socrata_app_token

log = logging.getLogger(__name__)

USER_AGENT = "la311-closed-vs-fixed (+https://github.com/SkyeJM/la311-closed-vs-fixed)"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


def retrying():
    """Fresh retry decorator: exponential backoff with jitter, six attempts, then re-raise."""
    return retry(
        retry=retry_if_exception(is_retryable),
        wait=wait_exponential_jitter(multiplier=2, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )


class SocrataClient:
    def __init__(
        self,
        domain: str,
        app_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"User-Agent": USER_AGENT}
        token = app_token or socrata_app_token()
        if token:
            headers["X-App-Token"] = token
        self.domain = domain
        self._http = httpx.Client(
            base_url=f"https://{domain}",
            headers=headers,
            timeout=httpx.Timeout(30.0, read=300.0),
            transport=transport,
        )

    def __enter__(self) -> SocrataClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._http.close()

    @retrying()
    def get(self, path: str, params: dict[str, str | int] | None = None) -> httpx.Response:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response

    @retrying()
    def download(self, path: str, dest: Path, params: dict[str, str] | None = None) -> dict:
        """Stream a large response to `dest` via a temp file; a retry restarts from scratch."""
        partial = dest.with_name(dest.name + ".part")
        written = 0
        with self._http.stream("GET", path, params=params) as response:
            response.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in response.iter_bytes(1 << 20):
                    fh.write(chunk)
                    written += len(chunk)
            last_modified = response.headers.get("last-modified")
        partial.replace(dest)
        return {"bytes": written, "last_modified": last_modified}

    def view_metadata(self, dataset_id: str) -> dict:
        return self.get(f"/api/views/{dataset_id}.json").json()

    def catalog_search(self, query: str, page_size: int = 100) -> list[dict]:
        """Every catalog result on this domain that matches a full-text query."""
        results: list[dict] = []
        while True:
            page = self.get(
                "/api/catalog/v1",
                params={
                    "domains": self.domain,
                    "q": query,
                    "limit": page_size,
                    "offset": len(results),
                },
            ).json()
            results.extend(page["results"])
            if not page["results"] or len(results) >= page["resultSetSize"]:
                return results

    def query_csv(self, dataset_id: str, soql: dict[str, str]) -> str:
        """Run a SoQL query on the row API. Headers are API field names, not display names."""
        return self.get(f"/resource/{dataset_id}.csv", params=soql).text
