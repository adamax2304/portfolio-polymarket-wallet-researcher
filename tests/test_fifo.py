import pandas as pd

from polymarket_researcher.analysis import fifo_round_trips


def test_fifo_round_trip_partial_lots():
    trades = pd.DataFrame(
        [
            {"wallet": "0xabc", "condition_id": "m1", "outcome": "YES", "side": "BUY", "price": 0.40, "size": 10, "timestamp": 100, "notional": 4, "market_title": "M"},
            {"wallet": "0xabc", "condition_id": "m1", "outcome": "YES", "side": "BUY", "price": 0.50, "size": 10, "timestamp": 110, "notional": 5, "market_title": "M"},
            {"wallet": "0xabc", "condition_id": "m1", "outcome": "YES", "side": "SELL", "price": 0.70, "size": 15, "timestamp": 200, "notional": 10.5, "market_title": "M"},
        ]
    )
    result = fifo_round_trips(trades)
    assert len(result) == 2
    assert result["size"].tolist() == [10, 5]
    assert round(result["realized_pnl_estimate"].sum(), 6) == 4.0
    assert result["hold_seconds"].tolist() == [100, 90]
