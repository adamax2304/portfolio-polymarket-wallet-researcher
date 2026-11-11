from __future__ import annotations

from urllib.parse import unquote, urlparse
import html
import logging
import re

import requests

from .utils import WALLET_RE

LOGGER = logging.getLogger(__name__)


PROFILE_HANDLE_RE = re.compile(r"(?:polymarket\.com/(?:@|profile/%40|profile/@)|^@)([^/?#]+)", re.I)


def extract_profile_handle(value: str) -> str | None:
    match = PROFILE_HANDLE_RE.search(value or "")
    if not match:
        return None
    return unquote(match.group(1)).lstrip("@")


def resolve_profile_wallet(value: str, timeout: float = 20.0) -> str | None:
    """Resolve a Polymarket profile handle/url to its proxy wallet by reading public page data."""
    if WALLET_RE.fullmatch((value or "").strip()):
        return value.lower()
    handle = extract_profile_handle(value)
    if not handle:
        return None
    url = f"https://polymarket.com/@{handle}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "polymarket-wallet-researcher/0.1"})
    response.raise_for_status()
    text = html.unescape(response.text)

    handle_escaped = re.escape(handle)
    targeted_patterns = [
        rf'"proxyWallet"\s*:\s*"(0x[a-fA-F0-9]{{40}})"\s*,\s*"name"\s*:\s*"{handle_escaped}"',
        rf'"proxyWallet"\s*:\s*"(0x[a-fA-F0-9]{{40}})"[^{{}}]{{0,600}}"pseudonym"\s*:\s*"{handle_escaped}"',
    ]
    for pattern in targeted_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).lower()

    wallets = re.findall(r'"proxyWallet"\s*:\s*"(0x[a-fA-F0-9]{40})"', text)
    unique = []
    for wallet in wallets:
        wallet = wallet.lower()
        if wallet not in unique:
            unique.append(wallet)
    if len(unique) == 1:
        return unique[0]
    if unique:
        LOGGER.warning("Multiple proxyWallet values found for %s; using first: %s", handle, unique[0])
        return unique[0]
    return None
