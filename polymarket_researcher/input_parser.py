from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .utils import WALLET_RE, normalize_wallet


def extract_wallets(text: str) -> list[str]:
    """Extract unique 0x wallet addresses from URLs, free text, or plain addresses."""
    seen: set[str] = set()
    wallets: list[str] = []
    for match in WALLET_RE.finditer(text or ""):
        wallet = match.group(0).lower()
        if wallet not in seen:
            seen.add(wallet)
            wallets.append(wallet)
    return wallets


def parse_wallet_file(path: str | Path) -> list[str]:
    return extract_wallets(Path(path).read_text(encoding="utf-8"))


def parse_inputs(input_value: str | None = None, wallet: str | None = None, file: str | None = None) -> list[str]:
    wallets: list[str] = []
    if input_value:
        wallets.extend(extract_wallets(input_value))
    if wallet:
        wallets.extend(extract_wallets(wallet) or [normalize_wallet(wallet)])
    if file:
        wallets.extend(parse_wallet_file(file))
    return dedupe(wallets)


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        wallet = normalize_wallet(value)
        if wallet not in seen:
            seen.add(wallet)
            out.append(wallet)
    return out
