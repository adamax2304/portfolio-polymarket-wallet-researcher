from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json
import sqlite3

from .utils import ensure_dirs


class ResearchStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        ensure_dirs(db_path.parent)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                wallet TEXT PRIMARY KEY,
                profile_json TEXT,
                traded_count INTEGER,
                collected_at TEXT
            );
            CREATE TABLE IF NOT EXISTS raw_activity (
                wallet TEXT,
                timestamp INTEGER,
                condition_id TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS raw_trades (
                wallet TEXT,
                timestamp INTEGER,
                condition_id TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS trades_normalized (
                wallet TEXT,
                timestamp INTEGER,
                datetime_utc TEXT,
                market_id TEXT,
                condition_id TEXT,
                slug TEXT,
                market_title TEXT,
                event_title TEXT,
                outcome TEXT,
                side TEXT,
                price REAL,
                size REAL,
                notional REAL,
                fee REAL,
                transaction_hash TEXT,
                trade_id TEXT,
                maker_taker TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS markets (
                market_key TEXT PRIMARY KEY,
                condition_id TEXT,
                slug TEXT,
                market_title TEXT,
                event_title TEXT,
                category TEXT,
                tags TEXT,
                end_date TEXT,
                resolution_status TEXT,
                outcomes TEXT,
                token_ids TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                wallet TEXT,
                condition_id TEXT,
                slug TEXT,
                outcome TEXT,
                size REAL,
                avg_price REAL,
                current_value REAL,
                realized_pnl REAL,
                status TEXT,
                raw_json TEXT
            );
            CREATE TABLE IF NOT EXISTS analysis_results (
                wallet TEXT,
                generated_at TEXT,
                result_json TEXT
            );
            """
        )
        self.conn.commit()

    def clear_wallet(self, wallet: str) -> None:
        for table in ("raw_activity", "raw_trades", "trades_normalized", "positions", "analysis_results"):
            self.conn.execute(f"DELETE FROM {table} WHERE wallet = ?", (wallet,))
        self.conn.commit()

    def upsert_wallet(self, wallet: str, profile: dict[str, Any], traded_count: int | None, collected_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO wallets(wallet, profile_json, traded_count, collected_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(wallet) DO UPDATE SET
                profile_json=excluded.profile_json,
                traded_count=excluded.traded_count,
                collected_at=excluded.collected_at
            """,
            (wallet, json.dumps(profile, sort_keys=True), traded_count, collected_at),
        )
        self.conn.commit()

    def insert_raw(self, table: str, wallet: str, rows: Iterable[dict[str, Any]]) -> None:
        sql = f"INSERT INTO {table}(wallet, timestamp, condition_id, raw_json) VALUES(?, ?, ?, ?)"
        values = [
            (wallet, row.get("timestamp"), row.get("conditionId") or row.get("condition_id"), json.dumps(row, sort_keys=True))
            for row in rows
        ]
        self.conn.executemany(sql, values)
        self.conn.commit()

    def insert_trades(self, rows: Iterable[dict[str, Any]]) -> None:
        values = [
            (
                row.get("wallet"), row.get("timestamp"), row.get("datetime_utc"), row.get("market_id"),
                row.get("condition_id"), row.get("slug"), row.get("market_title"), row.get("event_title"),
                row.get("outcome"), row.get("side"), row.get("price"), row.get("size"), row.get("notional"),
                row.get("fee"), row.get("transaction_hash"), row.get("trade_id"), row.get("maker_taker"),
                row.get("raw_json"),
            )
            for row in rows
        ]
        self.conn.executemany(
            """
            INSERT INTO trades_normalized VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.conn.commit()

    def upsert_markets(self, rows: Iterable[dict[str, Any]]) -> None:
        values = [
            (
                row.get("market_key"), row.get("condition_id"), row.get("slug"), row.get("market_title"),
                row.get("event_title"), row.get("category"), row.get("tags"), row.get("end_date"),
                row.get("resolution_status"), row.get("outcomes"), row.get("token_ids"), row.get("raw_json"),
            )
            for row in rows
        ]
        self.conn.executemany(
            """
            INSERT INTO markets VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_key) DO UPDATE SET
                condition_id=excluded.condition_id,
                slug=excluded.slug,
                market_title=excluded.market_title,
                event_title=excluded.event_title,
                category=excluded.category,
                tags=excluded.tags,
                end_date=excluded.end_date,
                resolution_status=excluded.resolution_status,
                outcomes=excluded.outcomes,
                token_ids=excluded.token_ids,
                raw_json=excluded.raw_json
            """,
            values,
        )
        self.conn.commit()

    def insert_positions(self, wallet: str, rows: Iterable[dict[str, Any]], status: str) -> None:
        values = [
            (
                wallet, row.get("conditionId") or row.get("condition_id"), row.get("slug"), row.get("outcome"),
                row.get("size"), row.get("avgPrice") or row.get("avg_price"), row.get("currentValue"),
                row.get("realizedPnl"), status, json.dumps(row, sort_keys=True),
            )
            for row in rows
        ]
        self.conn.executemany("INSERT INTO positions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        self.conn.commit()

    def save_analysis(self, wallet: str, generated_at: str, result: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO analysis_results(wallet, generated_at, result_json) VALUES(?, ?, ?)",
            (wallet, generated_at, json.dumps(result, sort_keys=True, default=str)),
        )
        self.conn.commit()
