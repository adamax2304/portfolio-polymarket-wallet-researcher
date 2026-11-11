# polymarket_wallet_researcher

Research public Polymarket wallet activity, store raw API responses, export CSVs, and generate Markdown strategy reports. This project is for historical research and strategy classification only. It does not place orders, cancel orders, or use private/authenticated trading endpoints.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No API keys are required. The tool uses public read endpoints from:

- `https://data-api.polymarket.com`
- `https://gamma-api.polymarket.com`

## Commands

```bash
python main.py collect --wallet 0x04b6d7e930cf9e493c5e6ef24b496294f95594c8
python main.py analyze --wallet 0x04b6d7e930cf9e493c5e6ef24b496294f95594c8
python main.py full --wallet 0x04b6d7e930cf9e493c5e6ef24b496294f95594c8
python main.py full --input "https://polymarket.com/@0x04b6d7e930cf9e493c5e6ef24b496294f95594c8-1774448369789?tab=activity"
python main.py full --file wallets.txt
```

## Outputs

Raw JSON is saved under:

```text
data/raw/{wallet}/
```

SQLite database:

```text
data/polymarket_research.sqlite3
```

Per-wallet exports:

```text
exports/{wallet}/activity.csv
exports/{wallet}/trades.csv
exports/{wallet}/positions.csv
exports/{wallet}/markets.csv
exports/{wallet}/round_trips.csv
exports/{wallet}/strategy_features.csv
exports/{wallet}/strategy_report.md
```

## API Assumptions

- Data API `GET /activity`, `GET /trades`, `GET /positions`, and `GET /closed-positions` accept `user`, `limit`, and `offset` parameters.
- Data API `GET /traded` returns a JSON object with a `traded` count when available.
- Gamma API `GET /public-profile?address=...` returns public profile fields when available.
- Gamma market lookup can vary by identifier, so the enricher tries slug, condition ID, and token ID forms and caches whatever metadata is returned.
- Public fills can support strategy inference, but not proof. Unfilled orders, cancellations, and historical orderbook state are not visible through these public historical endpoints.

## Tests

```bash
python -m compileall .
pytest -q
```
