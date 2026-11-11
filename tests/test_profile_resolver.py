from polymarket_researcher.profile_resolver import extract_profile_handle


def test_extract_short_profile_handle():
    assert extract_profile_handle("https://polymarket.com/@0x50f7") == "0x50f7"


def test_extract_profile_route_handle():
    assert extract_profile_handle("https://polymarket.com/profile/%400x50f7") == "0x50f7"
