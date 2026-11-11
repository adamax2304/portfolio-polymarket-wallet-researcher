from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Iterable
import math

import pandas as pd


@dataclass
class Lot:
    timestamp: int
    price: float
    size: float
    notional: float


def basic_stats(trades: pd.DataFrame, markets: pd.DataFrame | None = None) -> dict[str, Any]:
    if trades.empty:
        return {
            "total_trades": 0,
            "total_notional_volume": 0.0,
            "unique_markets": 0,
            "active_days": 0,
            "trades_per_day": 0.0,
            "average_trade_size": 0.0,
            "median_trade_size": 0.0,
            "average_price": 0.0,
            "most_common_price_bands": {},
            "most_traded_categories": {},
            "most_traded_markets": {},
            "buy_sell_ratio": None,
        }
    t = trades.copy()
    t["date"] = pd.to_datetime(t["datetime_utc"], errors="coerce").dt.date
    buys = int((t["side"] == "BUY").sum())
    sells = int((t["side"] == "SELL").sum())
    price_bands = Counter((t["price"].fillna(0).astype(float) * 10).round().astype(int).map(lambda x: f"{x*10}-{x*10+9}c"))
    categories: dict[str, int] = {}
    if markets is not None and not markets.empty:
        joined = t.merge(markets[["condition_id", "category"]], on="condition_id", how="left")
        categories = joined["category"].fillna("Unknown").value_counts().head(10).to_dict()
    return {
        "total_trades": int(len(t)),
        "total_notional_volume": float(t["notional"].fillna(0).sum()),
        "unique_markets": int(t["condition_id"].fillna(t["slug"]).nunique()),
        "active_days": int(t["date"].nunique()),
        "trades_per_day": float(len(t) / max(1, t["date"].nunique())),
        "average_trade_size": float(t["size"].fillna(0).mean()),
        "median_trade_size": float(t["size"].fillna(0).median()),
        "average_price": float(t["price"].fillna(0).mean()),
        "most_common_price_bands": dict(price_bands.most_common(8)),
        "most_traded_categories": categories,
        "most_traded_markets": t["market_title"].fillna(t["slug"]).value_counts().head(10).to_dict(),
        "buy_sell_ratio": round(buys / sells, 3) if sells else (float("inf") if buys else None),
    }


def fifo_round_trips(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    inventory: dict[tuple[str, str, str], deque[Lot]] = defaultdict(deque)
    sort_cols = [c for c in ("timestamp", "transaction_hash") if c in trades.columns]
    for row in trades.sort_values(sort_cols).to_dict("records"):
        key = (row.get("wallet"), row.get("condition_id") or row.get("slug"), row.get("outcome"))
        side = str(row.get("side") or "").upper()
        size = float(row.get("size") or 0)
        price = float(row.get("price") or 0)
        timestamp = int(row.get("timestamp") or 0)
        notional = float(row.get("notional") or price * size)
        if side == "BUY":
            inventory[key].append(Lot(timestamp, price, size, notional))
        elif side == "SELL":
            remaining = size
            while remaining > 1e-12 and inventory[key]:
                lot = inventory[key][0]
                matched = min(remaining, lot.size)
                buy_cost = lot.price * matched
                sell_value = price * matched
                rows.append(
                    {
                        "wallet": row.get("wallet"),
                        "condition_id": key[1],
                        "outcome": key[2],
                        "open_timestamp": lot.timestamp,
                        "close_timestamp": timestamp,
                        "hold_seconds": max(0, timestamp - lot.timestamp),
                        "size": matched,
                        "buy_price": lot.price,
                        "sell_price": price,
                        "realized_pnl_estimate": sell_value - buy_cost,
                        "market_title": row.get("market_title"),
                    }
                )
                lot.size -= matched
                remaining -= matched
                if lot.size <= 1e-12:
                    inventory[key].popleft()
    return pd.DataFrame(rows)


def holding_stats(round_trips: pd.DataFrame) -> dict[str, Any]:
    if round_trips.empty:
        return {
            "round_trips": 0,
            "realized_pnl_estimate": 0.0,
            "average_hold_seconds": None,
            "median_hold_seconds": None,
            "closed_under": {"10s": 0.0, "1m": 0.0, "5m": 0.0, "1h": 0.0, "1d": 0.0},
            "win_rate": None,
            "average_pnl_per_round_trip": None,
        }
    holds = round_trips["hold_seconds"].astype(float)
    total = len(round_trips)
    pnl = round_trips["realized_pnl_estimate"].astype(float)
    thresholds = {"10s": 10, "1m": 60, "5m": 300, "1h": 3600, "1d": 86400}
    return {
        "round_trips": int(total),
        "realized_pnl_estimate": float(pnl.sum()),
        "average_hold_seconds": float(holds.mean()),
        "median_hold_seconds": float(holds.median()),
        "closed_under": {name: float((holds <= seconds).mean()) for name, seconds in thresholds.items()},
        "win_rate": float((pnl > 0).mean()),
        "average_pnl_per_round_trip": float(pnl.mean()),
    }


def detect_complement_arbitrage(trades: pd.DataFrame, windows: Iterable[int] = (5, 30, 60, 300)) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    buys = trades[trades["side"] == "BUY"].copy()
    rows: list[dict[str, Any]] = []
    for condition_id, group in buys.groupby("condition_id", dropna=False):
        group = group.sort_values("timestamp")
        records = group.to_dict("records")
        for i, a in enumerate(records):
            for b in records[i + 1 :]:
                dt = abs(int(b.get("timestamp") or 0) - int(a.get("timestamp") or 0))
                if dt > max(windows):
                    break
                if str(a.get("outcome")).lower() == str(b.get("outcome")).lower():
                    continue
                combined_cost = float(a.get("price") or 0) + float(b.get("price") or 0)
                if combined_cost < 1.0:
                    rows.append(
                        {
                            "condition_id": condition_id,
                            "market_title": a.get("market_title") or b.get("market_title"),
                            "timestamp": min(a.get("timestamp") or 0, b.get("timestamp") or 0),
                            "window_seconds": min(w for w in windows if dt <= w),
                            "outcomes": f"{a.get('outcome')} + {b.get('outcome')}",
                            "combined_cost": combined_cost,
                            "locked_profit_estimate": 1.0 - combined_cost,
                        }
                    )
    return pd.DataFrame(rows)


def detect_cross_market_clusters(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    try:
        from rapidfuzz import fuzz
    except ImportError:
        from difflib import SequenceMatcher

        class fuzz:  # type: ignore
            @staticmethod
            def token_set_ratio(a: str, b: str) -> float:
                return SequenceMatcher(None, a, b).ratio() * 100

    rows: list[dict[str, Any]] = []
    t = trades.sort_values("timestamp").to_dict("records")
    for i, a in enumerate(t):
        for b in t[i + 1 :]:
            dt = int(b.get("timestamp") or 0) - int(a.get("timestamp") or 0)
            if dt > 600:
                break
            if (a.get("condition_id") or a.get("slug")) == (b.get("condition_id") or b.get("slug")):
                continue
            title_a = str(a.get("event_title") or a.get("market_title") or "")
            title_b = str(b.get("event_title") or b.get("market_title") or "")
            score = fuzz.token_set_ratio(title_a, title_b)
            if score >= 82:
                rows.append(
                    {
                        "timestamp": a.get("timestamp"),
                        "window_seconds": dt,
                        "similarity": score,
                        "market_a": a.get("market_title"),
                        "market_b": b.get("market_title"),
                    }
                )
    return pd.DataFrame(rows)


def score_strategy(stats: dict[str, Any], holding: dict[str, Any], complement_count: int, cross_count: int) -> dict[str, int]:
    total_trades = stats.get("total_trades", 0) or 0
    unique_markets = stats.get("unique_markets", 0) or 0
    avg_size = stats.get("average_trade_size", 0) or 0
    trades_per_day = stats.get("trades_per_day", 0) or 0
    under_5m = holding.get("closed_under", {}).get("5m", 0) or 0
    under_1h = holding.get("closed_under", {}).get("1h", 0) or 0
    median_hold = holding.get("median_hold_seconds")

    mm = clamp(20 * under_5m + min(25, total_trades / 20) + min(25, unique_markets / 5) + min(20, trades_per_day / 5) + (10 if avg_size < 25 and total_trades > 20 else 0))
    complement = clamp(min(95, complement_count * 25))
    cross = clamp(min(95, cross_count * 15))
    news = clamp(30 * under_1h + min(30, trades_per_day / 3) + min(20, avg_size / 200) + min(20, total_trades / 50))
    directional = clamp((35 if median_hold and median_hold > 86400 else 10) + (25 if unique_markets and unique_markets < 15 else 5) + min(25, avg_size / 80) + (15 if trades_per_day < 5 else 0))
    return {
        "market_making_likelihood": int(mm),
        "complement_arb_likelihood": int(complement),
        "cross_market_arb_likelihood": int(cross),
        "news_latency_likelihood": int(news),
        "directional_likelihood": int(directional),
    }


def classify(scores: dict[str, int]) -> dict[str, Any]:
    labels = {
        "complement_arb_likelihood": "Complement arbitrage",
        "cross_market_arb_likelihood": "Cross-market arbitrage",
        "market_making_likelihood": "Market making / spread capture",
        "news_latency_likelihood": "News latency trading",
        "directional_likelihood": "Directional forecasting",
    }
    best_key, best_score = max(scores.items(), key=lambda kv: kv[1])
    ordered = sorted(scores.values(), reverse=True)
    confidence = "low"
    if best_score >= 70 and (len(ordered) < 2 or best_score - ordered[1] >= 15):
        confidence = "high"
    elif best_score >= 45:
        confidence = "medium"
    label = labels.get(best_key, "Mixed / unknown") if best_score >= 30 else "Mixed / unknown"
    if len(ordered) > 1 and best_score - ordered[1] < 8:
        label = "Mixed / unknown"
    return {"classification": label, "confidence": confidence, "top_score": int(best_score)}


def run_analysis(trades: pd.DataFrame, markets: pd.DataFrame | None = None) -> dict[str, Any]:
    rounds = fifo_round_trips(trades)
    complement = detect_complement_arbitrage(trades)
    cross = detect_cross_market_clusters(trades)
    stats = basic_stats(trades, markets)
    holding = holding_stats(rounds)
    scores = score_strategy(stats, holding, len(complement), len(cross))
    return {
        "stats": stats,
        "holding": holding,
        "scores": scores,
        "classification": classify(scores),
        "round_trips": rounds,
        "complement_arbitrage": complement,
        "cross_market_clusters": cross,
    }


def clamp(value: float) -> int:
    if math.isnan(value):
        return 0
    return int(max(0, min(100, round(value))))
