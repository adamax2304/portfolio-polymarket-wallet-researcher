from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import logging

from .api import PolymarketAPI
from .utils import dump_json, load_json

LOGGER = logging.getLogger(__name__)


def collect_market_identifiers(*row_sets: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    identifiers: list[dict[str, str]] = []
    for rows in row_sets:
        for row in rows:
            slug = str(row.get("slug") or "").strip()
            condition_id = str(row.get("conditionId") or row.get("condition_id") or row.get("market") or "").strip()
            token_id = str(row.get("asset") or row.get("asset_id") or "").strip()
            key = (slug, condition_id, token_id)
            if any(key) and key not in seen:
                seen.add(key)
                identifiers.append({"slug": slug, "condition_id": condition_id, "token_id": token_id})
    return identifiers


def enrich_markets(api: PolymarketAPI, identifiers: list[dict[str, str]], cache_dir: Path) -> list[dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for identifier in identifiers:
        cache_key = identifier.get("slug") or identifier.get("condition_id") or identifier.get("token_id") or "unknown"
        cache_path = cache_dir / f"{safe_filename(cache_key)}.json"
        payload = load_json(cache_path, None)
        if payload is None:
            payload = api.fetch_market_metadata(
                slug=identifier.get("slug") or None,
                condition_id=identifier.get("condition_id") or None,
                token_id=identifier.get("token_id") or None,
            )
            dump_json(cache_path, payload)
        if payload:
            rows.append(flatten_market(payload, fallback=identifier))
        else:
            LOGGER.info("No Gamma metadata found for %s", identifier)
            rows.append(flatten_market({}, fallback=identifier))
    return rows


def flatten_market(payload: dict[str, Any], fallback: dict[str, str]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    tags = payload.get("tags") or event.get("tags") or []
    if isinstance(tags, list):
        tag_text = ", ".join(str(t.get("label") or t.get("name") or t) for t in tags)
    else:
        tag_text = str(tags)
    outcomes = parse_jsonish(payload.get("outcomes"))
    token_ids = parse_jsonish(payload.get("clobTokenIds") or payload.get("tokenIds"))
    condition_id = payload.get("conditionId") or payload.get("condition_id") or fallback.get("condition_id")
    slug = payload.get("slug") or fallback.get("slug")
    market_key = condition_id or slug or fallback.get("token_id") or str(payload.get("id") or "")
    return {
        "market_key": market_key,
        "condition_id": condition_id,
        "slug": slug,
        "market_title": payload.get("question") or payload.get("title") or payload.get("name"),
        "event_title": event.get("title") or event.get("name") or payload.get("eventSlug"),
        "category": payload.get("category") or event.get("category"),
        "tags": tag_text,
        "end_date": payload.get("endDate") or payload.get("end_date"),
        "resolution_status": payload.get("resolutionStatus") or payload.get("closed") or payload.get("resolvedBy"),
        "outcomes": json.dumps(outcomes, sort_keys=True),
        "token_ids": json.dumps(token_ids, sort_keys=True),
        "raw_json": json.dumps(payload, sort_keys=True),
    }


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def safe_filename(value: str) -> str:
    keep = [c if c.isalnum() or c in ("-", "_") else "_" for c in value[:120]]
    return "".join(keep) or "unknown"
