from polymarket_researcher.analysis import classify, score_strategy


def test_strategy_scoring_flags_complement_arb():
    stats = {
        "total_trades": 12,
        "unique_markets": 3,
        "average_trade_size": 50,
        "trades_per_day": 2,
    }
    holding = {"closed_under": {"5m": 0.2, "1h": 0.4}, "median_hold_seconds": 120}
    scores = score_strategy(stats, holding, complement_count=4, cross_count=0)
    result = classify(scores)
    assert scores["complement_arb_likelihood"] >= 90
    assert result["classification"] == "Complement arbitrage"


def test_strategy_scoring_directional_long_holds():
    stats = {
        "total_trades": 8,
        "unique_markets": 4,
        "average_trade_size": 250,
        "trades_per_day": 0.5,
    }
    holding = {"closed_under": {"5m": 0.0, "1h": 0.0}, "median_hold_seconds": 172800}
    scores = score_strategy(stats, holding, complement_count=0, cross_count=0)
    assert scores["directional_likelihood"] > scores["market_making_likelihood"]
