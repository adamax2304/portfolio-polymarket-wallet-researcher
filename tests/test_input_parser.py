from polymarket_researcher.input_parser import extract_wallets, parse_inputs


def test_extract_wallet_from_polymarket_url():
    text = "https://polymarket.com/@0x04b6d7e930cf9e493c5e6ef24b496294f95594c8-1774448369789?tab=activity"
    assert extract_wallets(text) == ["0x04b6d7e930cf9e493c5e6ef24b496294f95594c8"]


def test_parse_inputs_dedupes_multiple_sources(tmp_path):
    file_path = tmp_path / "wallets.txt"
    file_path.write_text(
        "0x04b6d7e930cf9e493c5e6ef24b496294f95594c8\n"
        "https://polymarket.com/@0x1111111111111111111111111111111111111111",
        encoding="utf-8",
    )
    wallets = parse_inputs(wallet="0x04b6d7e930cf9e493c5e6ef24b496294f95594c8", file=str(file_path))
    assert wallets == [
        "0x04b6d7e930cf9e493c5e6ef24b496294f95594c8",
        "0x1111111111111111111111111111111111111111",
    ]


def test_parse_inputs_allows_short_profile_url_for_later_resolution():
    assert parse_inputs(input_value="https://polymarket.com/@0x50f7") == []
