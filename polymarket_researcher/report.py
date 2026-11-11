from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .utils import utc_now


def export_wallet_files(
    wallet: str,
    export_dir: Path,
    *,
    activity: list[dict[str, Any]],
    trades: pd.DataFrame,
    positions: pd.DataFrame,
    markets: pd.DataFrame,
    analysis: dict[str, Any],
    profile: dict[str, Any],
) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(activity).to_csv(export_dir / "activity.csv", index=False)
    trades.to_csv(export_dir / "trades.csv", index=False)
    positions.to_csv(export_dir / "positions.csv", index=False)
    markets.to_csv(export_dir / "markets.csv", index=False)
    analysis["round_trips"].to_csv(export_dir / "round_trips.csv", index=False)
    features = flatten_features(analysis)
    pd.DataFrame([features]).to_csv(export_dir / "strategy_features.csv", index=False)
    report_path = export_dir / "strategy_report.md"
    report_path.write_text(render_report(wallet, profile, analysis, trades, markets), encoding="utf-8")
    return report_path


def flatten_features(analysis: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for section in ("stats", "holding", "scores", "classification"):
        for key, value in analysis.get(section, {}).items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    features[f"{key}_{subkey}"] = subvalue
            else:
                features[key] = value
    return features


def render_report(wallet: str, profile: dict[str, Any], analysis: dict[str, Any], trades: pd.DataFrame, markets: pd.DataFrame) -> str:
    stats = analysis["stats"]
    holding = analysis["holding"]
    scores = analysis["scores"]
    classification = analysis["classification"]
    generated_at = utc_now()
    profile_url = f"https://polymarket.com/@{wallet}"
    data_period = data_period_text(trades)
    top_markets = trades["market_title"].fillna(trades.get("slug")).value_counts().head(10).reset_index() if not trades.empty else pd.DataFrame()
    clusters = interesting_clusters(analysis)
    lines = [
        "# Polymarket Wallet Strategy Report",
        "",
        f"Wallet: `{wallet}`",
        f"Profile URL: {profile_url}",
        f"Data period: {data_period}",
        f"Generated at: {generated_at}",
        "",
        "## Executive Summary",
        f"Final strategy hypothesis: **{classification['classification']}** with **{classification['confidence']}** confidence.",
        evidence_sentence(stats, holding, analysis),
        "",
        "## Key Stats",
        markdown_table(
            ["Metric", "Value"],
            [
                ("Total trades", stats["total_trades"]),
                ("Total notional volume", round(stats["total_notional_volume"], 4)),
                ("Unique markets", stats["unique_markets"]),
                ("Active days", stats["active_days"]),
                ("Trades per day", round(stats["trades_per_day"], 3)),
                ("Average trade size", round(stats["average_trade_size"], 4)),
                ("Median trade size", round(stats["median_trade_size"], 4)),
                ("Average price", round(stats["average_price"], 4)),
                ("Buy/sell ratio", stats["buy_sell_ratio"]),
            ],
        ),
        "",
        "## Strategy Fingerprint Scores",
        markdown_table(
            ["Signal", "Score"],
            [
                ("Market making likelihood", scores["market_making_likelihood"]),
                ("Complement arb likelihood", scores["complement_arb_likelihood"]),
                ("Cross-market arb likelihood", scores["cross_market_arb_likelihood"]),
                ("News latency likelihood", scores["news_latency_likelihood"]),
                ("Directional forecasting likelihood", scores["directional_likelihood"]),
            ],
        ),
        "",
        "## Evidence",
        f"- Holding time: {holding['round_trips']} matched round trips, median hold {fmt_seconds(holding['median_hold_seconds'])}.",
        f"- Market count: {stats['unique_markets']} unique markets across {stats['active_days']} active days.",
        f"- Trade size distribution: average size {stats['average_trade_size']:.4f}, median size {stats['median_trade_size']:.4f}.",
        f"- Market categories: {dict_text(stats.get('most_traded_categories'))}.",
        f"- Repeated patterns: {len(analysis['cross_market_clusters'])} related cross-market clusters and {len(analysis['complement_arbitrage'])} complement arbitrage candidates.",
        f"- Round trips: estimated realized PnL {holding['realized_pnl_estimate']:.4f}; win rate {pct(holding['win_rate'])}.",
        "",
        "## Top Markets",
        dataframe_table(top_markets, ["Market", "Trades"]),
        "",
        "## Suspicious / Interesting Trade Clusters",
        dataframe_table(clusters, ["Type", "Timestamp", "Window Seconds", "Description", "Estimate"]),
        "",
        "## What Cannot Be Known",
        "- Polymarket CLOB order cancellations and unfilled limit orders are not visible from public historical data.",
        "- Historical orderbook snapshots are not available unless collected in real time or bought from a data provider.",
        "- Therefore market making can be inferred but not proven only from fills.",
    ]
    return "\n".join(lines) + "\n"


def data_period_text(trades: pd.DataFrame) -> str:
    if trades.empty:
        return "No trades found"
    dates = pd.to_datetime(trades["datetime_utc"], errors="coerce").dropna()
    if dates.empty:
        return "Unknown"
    return f"{dates.min().date()} to {dates.max().date()}"


def evidence_sentence(stats: dict[str, Any], holding: dict[str, Any], analysis: dict[str, Any]) -> str:
    return (
        f"The wallet shows {stats['total_trades']} public fills, {stats['unique_markets']} markets, "
        f"{len(analysis['complement_arbitrage'])} complement-arb candidates, and "
        f"{pct(holding.get('closed_under', {}).get('5m'))} of matched round trips closing within 5 minutes."
    )


def interesting_clusters(analysis: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in analysis["complement_arbitrage"].head(20).to_dict("records"):
        rows.append(
            {
                "Type": "Complement arb",
                "Timestamp": row.get("timestamp"),
                "Window Seconds": row.get("window_seconds"),
                "Description": f"{row.get('market_title')} ({row.get('outcomes')})",
                "Estimate": row.get("locked_profit_estimate"),
            }
        )
    for row in analysis["cross_market_clusters"].head(20).to_dict("records"):
        rows.append(
            {
                "Type": "Cross-market",
                "Timestamp": row.get("timestamp"),
                "Window Seconds": row.get("window_seconds"),
                "Description": f"{row.get('market_a')} / {row.get('market_b')}",
                "Estimate": row.get("similarity"),
            }
        )
    return pd.DataFrame(rows)


def markdown_table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def dataframe_table(df: pd.DataFrame, headers: list[str]) -> str:
    if df.empty:
        return "_None found._"
    rows = []
    for record in df.head(15).itertuples(index=False):
        values = list(record)
        rows.append(tuple(values[: len(headers)]))
    return markdown_table(headers, rows)


def fmt_seconds(value: Any) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    seconds = float(value)
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    return f"{float(value) * 100:.1f}%"


def dict_text(value: Any) -> str:
    if not value:
        return "unknown"
    return ", ".join(f"{k}: {v}" for k, v in dict(value).items())
