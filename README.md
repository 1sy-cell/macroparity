# MacroParity

Currency fair value scanner — combines macro fundamentals with price positioning.

## What it does

Ranks 8 major currencies on three macro inputs (forward real rate, expected rate
path, current account), then checks where each pair trades within its 1Y / 5Y / 10Y
range. A macro divergence only matters if price has not already moved to reflect it.

## Verdicts

- **ENTRY ZONE** — macro direction and price positioning agree
- **LATE** — macro direction is right but price already moved
- **TRAP** — short and long horizons disagree
- **WEAK** — macro gap is within noise (< 0.30)

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
```

## Data

- Prices: Yahoo Finance (daily, 10 years)
- Macro inputs: entered manually, sourced from central banks and tradingeconomics.com
- Suggested update cadence: monthly, plus after each central bank decision

## Disclaimer

Research tool. Not investment advice. Valuation gaps can persist for years.
