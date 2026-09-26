# BTC Research Dashboard v0.3.6

A mobile-first Streamlit research terminal for quickly observing what is happening in the Bitcoin market.

The dashboard deliberately does **not** generate BUY/SELL signals, price forecasts, or a composite bullish/bearish score. It keeps different market dimensions visible so the user can interpret them independently.

## What it monitors

- **Overview** — BTC/USD, 24h and 7d change, distance from ATH.
- **Market State** — deterministic descriptions of trend, positioning, volatility, options, and futures curve. Missing or stale inputs become `N/A` rather than being guessed.
- **Price & Trend** — BTCUSDT history, 50d/200d/50w moving averages, 52-week-high distance, RSI, ATR, and 30d realized volatility.
- **Derivatives** — Deribit BTC-PERPETUAL current open interest, 8h-equivalent funding, perpetual premium, and listed dated-futures basis. Historical OI changes remain N/A until point-in-time observations are accumulated.
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
- **Funding** is the Deribit BTC-PERPETUAL 8h-equivalent funding rate; it is not annualized.
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

No API key is required for the current v0.3.6 data sources.

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

v0.3.5 replaces the cloud-blocked Binance futures collector with free public Deribit BTC futures/perpetual data for current OI, funding, perpetual premium, and the dated-futures curve. OI history/change is intentionally not estimated when unavailable.

Future directions include point-in-time snapshot storage and historical/similar-market-state research, without turning the dashboard into an automated trading system.


## v0.3.6

- Market State futures-curve classification ignores contracts with less than 7 days remaining, preventing unstable near-expiry annualization from dominating the state label. Short-dated contracts remain visible in the curve cards.
- Adds a machine-readable `latest_snapshot.json` export generated from the same in-memory observations shown in the UI. Missing data stays `null`; values are not refetched or estimated.
- The Streamlit runtime filesystem is ephemeral. v0.3.6 provides the snapshot schema/export foundation; durable point-in-time history and a stable public JSON endpoint require persistent storage or a scheduled GitHub workflow and are intentionally not claimed yet.

## Automated point-in-time archive (v0.3.8)

GitHub Actions runs the headless `collect_snapshot.py` collector once per hour
(at minute 17 UTC, subject to normal GitHub Actions scheduling delay). It publishes
one hourly UTC snapshot to the separate `snapshots` branch under
`data/history/YYYY/MM/DD/HH.json` and updates `data/latest_snapshot.json`. Keeping data
off `main` avoids redeploying the Streamlit app every hour. The collector records partial results rather than
inventing missing observations.

The latest machine-readable snapshot is intended to be publicly readable at:

`https://raw.githubusercontent.com/nhos726/btc-research-dashboard/snapshots/data/latest_snapshot.json`

This archive is the foundation for later OI 24h/7d changes and point-in-time
"similar history" research. OI changes should only be calculated after enough
real snapshots have accumulated; they are not backfilled or estimated.

## AI-readable public endpoint (v0.3.8)

The hourly collector also publishes the newest snapshot to a dedicated `gh-pages`
branch. After GitHub Pages is enabled for **Deploy from a branch → `gh-pages` →
`/(root)`**, the stable endpoint is:

`https://nhos726.github.io/btc-research-dashboard/data/latest_snapshot.json`

This endpoint is deliberately separate from Streamlit. It is static JSON and is
intended for browsers, scripts, and AI/web retrieval. The `snapshots` branch remains
the point-in-time archive.

v0.3.8 also fixes the archive copy path so hourly observations are retained at
`data/history/YYYY/MM/DD/HH.json` instead of being lost during branch publication.
