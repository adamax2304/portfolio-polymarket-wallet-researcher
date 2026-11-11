from pathlib import Path

from polymarket_researcher.api import PolymarketAPI
from polymarket_researcher.config import Settings


def test_offset_pagination_stops_when_page_short(tmp_path):
    api = PolymarketAPI(Settings(project_root=tmp_path, page_limit=2, max_pages=10))
    calls = []
    payloads = [[{"id": 1}, {"id": 2}], [{"id": 3}]]

    def fake_get(base, path, params):
        calls.append(params["offset"])
        return payloads.pop(0)

    api._get = fake_get  # type: ignore[method-assign]
    rows = api._paginate_offset("activity", {"user": "0xabc"}, Path(tmp_path), "activity", limit=2)
    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert calls == [0, 2]
