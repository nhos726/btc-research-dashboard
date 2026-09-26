# BTC Research Dashboard v0.3.3

A mobile-first Streamlit research terminal for quickly observing what is happening in the Bitcoin market.

The dashboard deliberately does **not** generate BUY/SELL signals, price forecasts, or a composite bullish/bearish score. It keeps different market dimensions visible so the user can interpret them independently.

## What it monitors

- **Overview** — BTC/USD, 24h and 7d change, distance from ATH.
- **Market State** — deterministic descriptions of trend, positioning, volatility, options, and futures curve. Missing or stale inputs become `N/A` rather than being guessed.
- **Price & Trend** — BTCUSDT history, 50d/200d/50w moving averages, 52-week-high distance, RSI, ATR, and 30d realized volatility.
- **Derivatives** — Binance BTCUSDT perpetual open interest, OI changes, funding, perpetual premium, and dated-futures basis.
- **Options** — Deribit ~30d ATM IV, IV minus realized volatility, and 25-delta risk reversal.
- **Crypto Liquidity** — DefiLlama USD-pegged stablecoin supply, 7d/30d/90d changes, USDT dominance, and a two-year supply chart.
- **Flows** — Farside US spot BTC ETF net flows and Coin Metrics aggregate BTC exchange netflow.
- **Research Links** — shortcuts to external tools for liquidation heatmaps, charts, mempool activity, ETF flows, and options.

## Data sources

| Area | Provider | Scope | Frequency / use |
|---|---|---|---|
| BTC/USD snapshot | CoinGecko | Bitcoin USD market data | Current snapshot |
| Price & trend | Binance Spot | BTCUSDT | Daily candles |
| OI / funding / futures curve | Binance USDⓈ-M | BTCUSDT derivatives | Current + history |
| Options | Deribit | BTC options | Current books / Greeks |
| Stablecoin supply | DefiLlama | USD-pegged stablecoins | Daily history |
| US spot BTC ETF flows | Farside Investors | US spot BTC ETFs | Trading days |
| BTC exchange netflow | Coin Metrics Community | Aggregate identified exchanges | Daily |

All displayed timestamps are UTC. Values from different venues/providers need not reconcile exactly.

## Important definitions and caveats

- **OI** is Binance USDⓈ-M BTCUSDT only, not market-wide OI.
- **Funding** is the latest Binance BTCUSDT perpetual funding rate for one funding interval; it is not annualized.
- **~30d ATM IV** uses the listed Deribit expiry nearest 30 calendar days and the strike nearest that expiry's underlying price. It is not constant-maturity interpolation.
- **25Δ Risk Reversal** is `IV(25Δ Call) − IV(25Δ Put)`. Delta comes from Deribit Greeks. It describes relative option pricing, not pure demand/order flow and not a forecast.
- **Stablecoin supply** is an observation variable, not a fear/greed or bullish/bearish signal.
- **ETF latest complete day** excludes a recent Farside row if any active ETF field or Total is still incomplete (`-` is never silently treated as zero).
- **Exchange Netflow** is `FlowInExNtv − FlowOutExNtv` from Coin Metrics' aggregate identified-exchange series. Exchange-to-exchange transfers are excluded by the source methodology. Negative netflow is not itself a trading signal.
- **Exchange Balance** is intentionally not shown because a suitable free automated source has not been adopted.
- **Liquidations** are intentionally not collected. Coin Metrics exposes relevant metric metadata, but the requested liquidation time series is not available with anonymous Community API credentials. The dashboard links to CoinGlass for manual liquidation-heatmap inspection instead.

## Failure behavior

Each external collector is isolated. If one source fails, that section displays `N/A` or an unavailable notice while the rest of the dashboard continues running. Missing data is not estimated.

Public APIs and webpages can change schemas, impose rate limits, block regions, or become temporarily unavailable. Treat source failures as expected operational events rather than as market information.

## Run locally

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Then install and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

This repository is designed to be deployed directly from GitHub.

1. Push the repository to GitHub.
2. Open Streamlit Community Cloud and connect the GitHub account.
3. Create an app from the repository.
4. Select the `main` branch and `app.py` as the entrypoint.
5. Deploy.

No API key is required for the current v0.3.3 data sources.

### Future paid APIs / secrets

Never commit API keys, tokens, passwords, or `.streamlit/secrets.toml` to GitHub. `.streamlit/secrets.toml` is already ignored by this repository. For Streamlit Community Cloud, store future credentials in the app's Secrets settings and read them through `st.secrets`.

## Repository structure

```text
app.py                  Streamlit UI and independent section failure handling
config.py               Endpoints and application settings
collectors/             External data collectors
indicators.py           Indicator calculations
market_state.py         Deterministic market-state classification
tests/                  Calculation and behavior tests
.streamlit/config.toml  Streamlit theme/configuration
requirements.txt        Python dependencies
```

## Development principles

1. Observation before prediction.
2. No hidden composite market score.
3. Do not fabricate unavailable data.
4. Preserve source/venue identity instead of silently combining unlike series.
5. A failed source must not take down the whole dashboard.
6. Keep the interface mobile-first.
7. Prefer free, official, or clearly documented public data sources where practical.
8. Add paid data only when its incremental research value justifies the dependency.

## AI handoff notes

When modifying this project with an AI coding assistant:

- Read this README and the current source before proposing changes.
- Preserve the dashboard's observation-not-signal philosophy.
- Do not convert descriptive states into BUY/SELL recommendations or a single sentiment score.
- Do not silently substitute another provider when a source fails.
- Preserve the existing header/mobile CSS unless the task specifically concerns it.
- Keep unsupported data as unsupported rather than estimating it.
- Run the test suite after changes.
- Increment the displayed version when producing a new release.

## Current status

v0.3.3 is the cloud-ready packaging of the working v0.3.2 dashboard. Market calculations and dashboard sections are unchanged; the release cleans repository artifacts and updates documentation for public GitHub + Streamlit Community Cloud deployment.

Future directions include point-in-time snapshot storage and historical/similar-market-state research, without turning the dashboard into an automated trading system.
