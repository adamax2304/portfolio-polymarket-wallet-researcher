from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from polymarket_researcher.analysis import run_analysis
from polymarket_researcher.api import PolymarketAPI
from polymarket_researcher.config import Settings
from polymarket_researcher.enrich import collect_market_identifiers, enrich_markets
from polymarket_researcher.input_parser import parse_inputs
from polymarket_researcher.normalize import normalize_trades
from polymarket_researcher.profile_resolver import resolve_profile_wallet
from polymarket_researcher.report import export_wallet_files
from polymarket_researcher.storage import ResearchStore
from polymarket_researcher.utils import ensure_dirs, safe_int, setup_logging, utc_now

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research public Polymarket wallet history and classify strategy fingerprints.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "analyze", "full"):
        sub = subparsers.add_parser(command)
        add_source_args(sub)
        sub.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser


def add_source_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Polymarket profile/activity URL or text containing wallet addresses.")
    group.add_argument("--wallet", help="0x wallet address.")
    group.add_argument("--file", help="Text file containing URLs or wallet addresses.")


def main() -> None:
    args = build_parser().parse_args()
    setup_logging(args.verbose)
    settings = Settings(project_root=Path(__file__).resolve().parent)
    wallets = parse_inputs(args.input, args.wallet, args.file)
    if not wallets and args.input:
        resolved = resolve_profile_wallet(args.input)
        if resolved:
            wallets = [resolved]
    if not wallets:
        raise SystemExit("No valid wallets found.")
    ensure_dirs(settings.data_dir, settings.raw_dir, settings.cache_dir, settings.exports_dir)
    store = ResearchStore(settings.db_path)
    store.init_schema()
    api = PolymarketAPI(settings)
    try:
        for wallet in wallets:
            if args.command in {"collect", "full"}:
                collect_wallet(wallet, api, store, settings)
            if args.command in {"analyze", "full"}:
                analyze_wallet(wallet, store, settings)
    finally:
        store.close()


def collect_wallet(wallet: str, api: PolymarketAPI, store: ResearchStore, settings: Settings) -> None:
    LOGGER.info("Collecting %s", wallet)
    raw_dir = settings.raw_dir / wallet
    ensure_dirs(raw_dir)
    store.clear_wallet(wallet)
    activity = api.fetch_activity(wallet, raw_dir)
    trades = api.fetch_trades(wallet, raw_dir)
    positions = api.fetch_positions(wallet, raw_dir)
    closed_positions = api.fetch_closed_positions(wallet, raw_dir)
    profile = api.fetch_profile(wallet, raw_dir)
    traded_count = api.fetch_traded_count(wallet, raw_dir)
    normalized = normalize_trades(wallet, trades)
    identifiers = collect_market_identifiers(activity, trades, positions, closed_positions)
    market_rows = enrich_markets(api, identifiers, settings.cache_dir / "markets")

    store.upsert_wallet(wallet, profile, safe_int(traded_count.get("traded"), None), utc_now())
    store.insert_raw("raw_activity", wallet, activity)
    store.insert_raw("raw_trades", wallet, trades)
    store.insert_trades(normalized)
    store.insert_positions(wallet, positions, "open")
    store.insert_positions(wallet, closed_positions, "closed")
    store.upsert_markets(market_rows)
    LOGGER.info("Collected %s: %s activity rows, %s trades, %s markets", wallet, len(activity), len(trades), len(market_rows))


def analyze_wallet(wallet: str, store: ResearchStore, settings: Settings) -> None:
    LOGGER.info("Analyzing %s", wallet)
    trades = pd.read_sql_query("SELECT * FROM trades_normalized WHERE wallet = ?", store.conn, params=(wallet,))
    positions = pd.read_sql_query("SELECT * FROM positions WHERE wallet = ?", store.conn, params=(wallet,))
    markets = pd.read_sql_query(
        """
        SELECT DISTINCT m.* FROM markets m
        JOIN trades_normalized t ON t.condition_id = m.condition_id OR t.slug = m.slug
        WHERE t.wallet = ?
        """,
        store.conn,
        params=(wallet,),
    )
    activity = [
        dict(row)
        for row in store.conn.execute("SELECT raw_json FROM raw_activity WHERE wallet = ?", (wallet,)).fetchall()
    ]
    activity_rows = [json.loads(row["raw_json"]) for row in activity]
    profile_row = store.conn.execute("SELECT profile_json FROM wallets WHERE wallet = ?", (wallet,)).fetchone()
    profile = json.loads(profile_row["profile_json"]) if profile_row and profile_row["profile_json"] else {}
    analysis = run_analysis(trades, markets)
    generated_at = utc_now()
    store.save_analysis(wallet, generated_at, serializable_analysis(analysis))
    report_path = export_wallet_files(
        wallet,
        settings.exports_dir / wallet,
        activity=activity_rows,
        trades=trades,
        positions=positions,
        markets=markets,
        analysis=analysis,
        profile=profile,
    )
    LOGGER.info("Wrote report %s", report_path)


def serializable_analysis(analysis: dict) -> dict:
    out = dict(analysis)
    for key in ("round_trips", "complement_arbitrage", "cross_market_clusters"):
        out[key] = out[key].to_dict("records")
    return out


if __name__ == "__main__":
    main()
