"""Find 311 datasets on the portal that sources.yml doesn't account for (e.g. a "Cases 2027")."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.config import Registry

SEARCH_TERMS = ("MyLA311", "311")
NAME_PATTERN = re.compile(r"311", re.IGNORECASE)


@dataclass(frozen=True)
class CatalogHit:
    id: str
    name: str
    asset_type: str
    updated_at: str
    status: str  # "registered", "ignored", or "new"


def classify(results: list[dict], registry: Registry) -> list[CatalogHit]:
    """Deduplicate catalog results whose name mentions 311 and label each one; new ones first."""
    registered = {d.id for d in registry.datasets}
    hits: dict[str, CatalogHit] = {}
    for result in results:
        resource = result["resource"]
        if resource["id"] in hits or not NAME_PATTERN.search(resource["name"]):
            continue
        if resource["id"] in registered:
            status = "registered"
        elif resource["id"] in registry.ignored:
            status = "ignored"
        else:
            status = "new"
        hits[resource["id"]] = CatalogHit(
            id=resource["id"],
            name=resource["name"],
            asset_type=resource.get("type", ""),
            updated_at=(resource.get("data_updated_at") or "")[:10],
            status=status,
        )
    return sorted(hits.values(), key=lambda h: (h.status != "new", h.name))
