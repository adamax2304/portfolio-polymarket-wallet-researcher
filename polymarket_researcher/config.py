from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path.cwd()
    data_api_base: str = os.getenv("POLYMARKET_DATA_API_BASE", "https://data-api.polymarket.com")
    gamma_api_base: str = os.getenv("POLYMARKET_GAMMA_API_BASE", "https://gamma-api.polymarket.com")
    request_timeout: float = float(os.getenv("POLYMARKET_REQUEST_TIMEOUT", "20"))
    page_limit: int = int(os.getenv("POLYMARKET_PAGE_LIMIT", "500"))
    max_pages: int = int(os.getenv("POLYMARKET_MAX_PAGES", "40"))
    rate_limit_sleep: float = float(os.getenv("POLYMARKET_RATE_LIMIT_SLEEP", "1.5"))

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def exports_dir(self) -> Path:
        return self.project_root / "exports"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "polymarket_research.sqlite3"
