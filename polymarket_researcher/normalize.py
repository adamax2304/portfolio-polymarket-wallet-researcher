from __future__ import annotations

from typing import Any
import json

from .utils import safe_float, safe_int, utc_from_timestamp


def normalize_trade(wallet: str, row: dict[str, Any]) -> dict[str, Any]:
    price = safe_float(row.get("price"))
    size = safe_float(row.get("size"))
    notional = safe_float(row.get("usdcSize"), price * size)
    return {
        "wallet": wallet,
        "timestamp": safe_int(row.get("timestamp") or row.get("match_time") or row.get("created_at")),
        "datetime_utc": utc_from_timestamp(row.get("timestamp") or row.get("match_time") or row.get("created_at")),
        "market_id": row.get("market") or row.get("marketId") or row.get("id"),
        "condition_id": row.get("conditionId") or row.get("condition_id") or row.get("market"),
        "slug": row.get("slug"),
        "market_title": row.get("title") or row.get("marketTitle") or row.get("question"),
        "event_title": row.get("eventTitle") or row.get("eventSlug"),
        "outcome": row.get("outcome") or row.get("outcomeName"),
        "side": infer_side(row),
        "price": price,
        "size": size,
        "notional": notional,
        "fee": safe_float(row.get("fee") or row.get("fee_rate_bps")),
        "transaction_hash": row.get("transactionHash") or row.get("transaction_hash"),
        "trade_id": row.get("tradeId") or row.get("id"),
        "maker_taker": row.get("trader_side") or row.get("makerTaker"),
        "raw_json": json.dumps(row, sort_keys=True),
    }


def normalize_trades(wallet: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_trade(wallet, row) for row in rows]


def infer_side(row: dict[str, Any]) -> str:
    side = row.get("side") or row.get("type")
    if isinstance(side, str) and side.upper() in {"BUY", "SELL"}:
        return side.upper()
    size = safe_float(row.get("size"))
    if size < 0:
        return "SELL"
    return ""
