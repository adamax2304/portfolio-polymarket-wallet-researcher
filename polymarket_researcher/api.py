from __future__ import annotations

from pathlib import Path
from typing import Any
import logging
import time

import requests

from .config import Settings
from .utils import coerce_list, dump_json

LOGGER = logging.getLogger(__name__)


class PolymarketAPI:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-wallet-researcher/0.1"})

    def _get(self, base: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.session.get(url, params=params, timeout=self.settings.request_timeout)
                if response.status_code in {429, 500, 502, 503, 504}:
                    sleep_for = self.settings.rate_limit_sleep * (attempt + 1)
                    LOGGER.warning("HTTP %s for %s; backing off %.1fs", response.status_code, response.url, sleep_for)
                    time.sleep(sleep_for)
                    continue
                response.raise_for_status()
                if not response.text.strip():
                    return {}
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                sleep_for = self.settings.rate_limit_sleep * (attempt + 1)
                LOGGER.warning("Request failed for %s: %s; retrying in %.1fs", url, exc, sleep_for)
                time.sleep(sleep_for)
        raise RuntimeError(f"Failed GET {url}: {last_error}")

    def _paginate_offset(self, path: str, params: dict[str, Any], raw_dir: Path, label: str, limit: int | None = None) -> list[dict[str, Any]]:
        page_limit = limit or self.settings.page_limit
        rows: list[dict[str, Any]] = []
        for page in range(self.settings.max_pages):
            page_params = dict(params)
            page_params.update({"limit": page_limit, "offset": page * page_limit})
            try:
                payload = self._get(self.settings.data_api_base, path, page_params)
            except RuntimeError as exc:
                if rows:
                    LOGGER.warning("Stopping %s pagination after %s rows because page %s failed: %s", label, len(rows), page + 1, exc)
                    break
                raise
            dump_json(raw_dir / f"{label}_{page:04d}.json", payload)
            page_rows = coerce_list(payload)
            rows.extend(page_rows)
            LOGGER.info("Fetched %s page %s: %s rows", label, page + 1, len(page_rows))
            if len(page_rows) < page_limit:
                break
        return rows

    def fetch_activity(self, wallet: str, raw_dir: Path) -> list[dict[str, Any]]:
        return self._paginate_offset("activity", {"user": wallet}, raw_dir, "activity")

    def fetch_trades(self, wallet: str, raw_dir: Path) -> list[dict[str, Any]]:
        return self._paginate_offset("trades", {"user": wallet, "takerOnly": "false"}, raw_dir, "trades", limit=1000)

    def fetch_positions(self, wallet: str, raw_dir: Path) -> list[dict[str, Any]]:
        return self._paginate_offset("positions", {"user": wallet, "sizeThreshold": 0}, raw_dir, "positions")

    def fetch_closed_positions(self, wallet: str, raw_dir: Path) -> list[dict[str, Any]]:
        return self._paginate_offset("closed-positions", {"user": wallet}, raw_dir, "closed_positions")

    def fetch_profile(self, wallet: str, raw_dir: Path) -> dict[str, Any]:
        try:
            payload = self._get(self.settings.gamma_api_base, "public-profile", {"address": wallet})
        except RuntimeError as exc:
            LOGGER.warning("Profile fetch failed for %s: %s", wallet, exc)
            payload = {}
        dump_json(raw_dir / "profile.json", payload)
        return payload if isinstance(payload, dict) else {}

    def fetch_traded_count(self, wallet: str, raw_dir: Path) -> dict[str, Any]:
        try:
            payload = self._get(self.settings.data_api_base, "traded", {"user": wallet})
        except RuntimeError as exc:
            LOGGER.warning("Traded-count fetch failed for %s: %s", wallet, exc)
            payload = {}
        dump_json(raw_dir / "traded_count.json", payload)
        return payload if isinstance(payload, dict) else {}

    def fetch_market_metadata(self, *, slug: str | None = None, condition_id: str | None = None, token_id: str | None = None) -> dict[str, Any]:
        candidates: list[tuple[str, dict[str, Any]]] = []
        if slug:
            candidates.extend([
                (f"markets/slug/{slug}", {}),
                ("markets", {"slug": slug}),
            ])
        if condition_id:
            candidates.extend([
                ("markets", {"condition_ids": condition_id}),
                ("markets", {"conditionId": condition_id}),
            ])
        if token_id:
            candidates.extend([
                (f"markets/token/{token_id}", {}),
                ("markets", {"token_ids": token_id}),
            ])
        for path, params in candidates:
            try:
                payload = self._get(self.settings.gamma_api_base, path, params)
            except RuntimeError:
                continue
            if isinstance(payload, dict) and payload:
                return payload
            rows = coerce_list(payload)
            if rows:
                return rows[0]
        return {}
