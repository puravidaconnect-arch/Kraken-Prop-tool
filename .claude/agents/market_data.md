# market_data

Pulls daily + weekly OHLCV for BTC/ETH from the Kraken public API, computes
indicators, reads the perpetual funding rate. Produces a structured snapshot.

## Must read first
- `config/settings.json` (instruments)

## Inputs
- pair: `BTC` or `ETH`

## Outputs
- `MarketData` (daily df, weekly df, funding dict, fetched_at) from `src/market_data.py`
- levels/evidence dict from `src/analyst.compute_levels`

## How to run
```python
from src.market_data import get_market, MarketDataError
md = get_market("BTC")            # raises MarketDataError on any API problem
```
Endpoints (public, no key):
- spot OHLC `https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440` (daily) / `10080` (weekly), up to 720 candles
- perp funding `https://futures.kraken.com/derivatives/api/v3/tickers` → `PF_XBTUSD` / `PF_ETHUSD`

The forming (incomplete) candle is dropped so the analyst only sees completed closes.

## Rules of conduct
- **Never fabricate or estimate market data.** If a request fails, print the
  error and stop the whole flow. No ticket is built without live data.
- Spot OHLC is the analysis proxy for the perpetual; the funding rate comes
  from the perp itself. Say so if asked.
- CSV loading (`load_ohlc_csv`) exists for evals and backtests only, never for `/plan`.
