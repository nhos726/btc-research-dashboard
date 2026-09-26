from __future__ import annotations

from datetime import datetime, timezone
from html import escape

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from collectors.derivatives import fetch_delivery_basis, fetch_derivatives
from collectors.options import fetch_options_summary
from collectors.spot import fetch_daily_ohlcv, fetch_market_snapshot
from collectors.stablecoins import fetch_stablecoin_summary
from collectors.etf_flows import fetch_etf_flows
from collectors.exchange_flows import fetch_exchange_flows
from indicators import attach_confirmed_indicators, completed_daily_candles, enrich_ohlcv, overview_from_prices
from market_state import build_market_state
from snapshot import build_snapshot, snapshot_json

st.set_page_config(page_title="BTC Research Dashboard", page_icon="₿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
  /* Cloud-safe theme fallback. The .streamlit theme remains the primary setting,
     but these rules keep the page readable even if a host/user theme overrides it. */
  html, body, [data-testid="stAppViewContainer"], .stApp {background:#080D14 !important; color:#E8EDF4 !important;}
  [data-testid="stHeader"] {background:rgba(8,13,20,.92) !important;}
  [data-testid="stToolbar"], [data-testid="stDecoration"] {color:#E8EDF4 !important;}
  .stMarkdown, .stMarkdown p, .stMarkdown li, .stCaption, label, h1, h2, h3 {color:#E8EDF4;}
  .block-container {max-width: 1050px; padding-top: 1.8rem; padding-bottom: 4rem;}
  /* Desktop only: keep the title below Streamlit's fixed top chrome. Mobile spacing stays unchanged. */
  @media(min-width:761px){.block-container{padding-top:4.5rem;}}
  h2 {font-size:1.25rem!important; margin-top:1.6rem!important;}
  .dashboard-title {font-size:1.7rem; line-height:1.25; font-weight:700; margin:0 0 .35rem; padding:0; white-space:normal;}
  .dashboard-subtitle {color:#8b98a9; font-size:.9rem; margin-bottom:.85rem;}
  .metric-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin:.35rem 0 .7rem;}
  .metric-card {min-width:0; background:#111827; border:1px solid #263244; border-radius:14px; padding:.72rem .82rem;}
  .metric-label {color:#d4d9e1; font-size:.76rem; line-height:1.25; margin-bottom:.32rem; overflow-wrap:anywhere;}
  .metric-value {font-size:1.28rem; line-height:1.15; font-weight:500; overflow-wrap:anywhere;}
  .muted {color:#8b98a9;font-size:.82rem}.status {padding:.65rem .8rem;border-radius:10px;background:#101722;border:1px solid #263244}
  .unsupported {color:#8b98a9;font-size:.78rem;line-height:1.45;margin:.4rem 0 .9rem;padding:.35rem .05rem;}
  .state-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin:.35rem 0 .7rem;}
  .state-card{background:#0f1724;border:1px solid #263244;border-radius:14px;padding:.78rem .85rem;min-width:0;}
  .state-name{color:#8b98a9;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:.28rem;}
  .state-value{font-size:1.02rem;font-weight:650;line-height:1.25;margin-bottom:.28rem;overflow-wrap:anywhere;}
  .state-detail{color:#8b98a9;font-size:.72rem;line-height:1.35;overflow-wrap:anywhere;}
  @media(max-width:760px){
    .block-container{padding-left:.75rem;padding-right:.75rem;padding-top:4.5rem}
    .dashboard-title{font-size:1.48rem;line-height:1.25;}
    .metric-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}
    .metric-card{padding:.62rem .68rem;border-radius:12px}
    .metric-label{font-size:.72rem}.metric-value{font-size:1.08rem}
    .stPlotlyChart{margin-left:-.35rem;margin-right:-.35rem}
    .state-grid{grid-template-columns:1fr;gap:.5rem}.state-card{padding:.68rem .72rem}
  }
  @media(max-width:350px){.dashboard-title{font-size:1.34rem}.metric-value{font-size:1rem}}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    result, errors = {}, {}
    loaders = {"market": fetch_market_snapshot, "spot": fetch_daily_ohlcv, "derivatives": fetch_derivatives, "delivery": fetch_delivery_basis, "options": fetch_options_summary, "stablecoins": fetch_stablecoin_summary, "etf_flows": fetch_etf_flows, "exchange_flows": fetch_exchange_flows}
    for name, loader in loaders.items():
        try: result[name] = loader()
        except Exception as exc: errors[name] = str(exc)
    return result, errors


def pct(value, digits=1): return "N/A" if value is None or pd.isna(value) else f"{value:+.{digits}f}%"
def pct_plain(value, digits=1): return "N/A" if value is None or pd.isna(value) else f"{value:.{digits}f}%"
def money(value): return "N/A" if value is None or pd.isna(value) else f"${value:,.0f}"
def number(value): return "N/A" if value is None or pd.isna(value) else f"{value:,.0f}"
def flow_money_m(value):
    if value is None or pd.isna(value): return "N/A"
    sign = "+" if value > 0 else "−" if value < 0 else ""
    amount = abs(float(value))
    return f"{sign}${amount/1000:.2f}B" if amount >= 1000 else f"{sign}${amount:,.1f}M"
def stamp(dt): return "N/A" if dt is None else dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def metrics(items):
    cards = []
    for item in items:
        label, value = str(item[0]), str(item[1])
        cards.append(
            f'<div class="metric-card"><div class="metric-label">{escape(label)}</div>'
            f'<div class="metric-value">{escape(value)}</div></div>'
        )
    st.markdown('<div class="metric-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "showTips": False,
}

def lock_chart(fig):
    """Keep Plotly charts readable on mobile: hover is allowed, pan/zoom/axis edits are not."""
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

def unsupported_note(text):
    st.markdown(f'<div class="unsupported">{escape(text)}</div>', unsafe_allow_html=True)

st.markdown('<div class="dashboard-title">₿ BTC Research Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="dashboard-subtitle">v0.3.8 · Market observation, not a trading signal</div>', unsafe_allow_html=True)
if st.button("↻ Refresh", width="stretch"):
    st.cache_data.clear(); st.rerun()

with st.spinner("Loading public market data…"):
    data, errors = load_data()

spot_df = enriched = None
if "spot" in data:
    spot_df, spot_updated = data["spot"]
    confirmed_spot = completed_daily_candles(spot_df)
    confirmed_enriched = enrich_ohlcv(confirmed_spot)
    enriched = attach_confirmed_indicators(spot_df, confirmed_spot)
    technical = overview_from_prices(confirmed_enriched)
else: technical = {}
market, market_updated = data.get("market", ({}, None))

st.header("OVERVIEW")
metrics([
    ("BTC / USD", money(market.get("price_usd"))),
    ("24h change", pct(market.get("change_24h"))),
    ("7d change", pct(market.get("change_7d"))),
    ("From ATH", pct(market.get("ath_change_pct"))),
    ("From 52w high", pct(technical.get("distance_52w"))),
    ("From 50d MA", pct(technical.get("distance_ma50"))),
    ("From 200d MA", pct(technical.get("distance_ma200"))),
    ("From 50w MA", pct(technical.get("distance_ma50w"))),
    ("30d realized vol", pct(technical.get("rv30"))),
])
st.markdown(f'<div class="muted">Price: CoinGecko BTC/USD · Technical metrics: Binance BTC/USDT daily · refreshed {stamp(datetime.now(timezone.utc))}</div>', unsafe_allow_html=True)

# Deterministic market-state descriptors. Each axis is classified independently;
# there is deliberately no composite score, forecast, or BUY/SELL output.
deriv_for_state, oi_for_state = None, None
if "derivatives" in data:
    deriv_for_state, oi_for_state, _, _ = data["derivatives"]
opt_for_state = data["options"][0] if "options" in data else None
delivery_for_state = data["delivery"][0] if "delivery" in data else None
st.header("MARKET STATE")
states = build_market_state(technical, deriv_for_state, oi_for_state, opt_for_state, delivery_for_state)
state_html = []
for item in states:
    state_html.append(
        f'<div class="state-card"><div class="state-name">{escape(item["name"])}</div>'
        f'<div class="state-value">{escape(item["state"])}</div>'
        f'<div class="state-detail">{escape(item["detail"])}</div></div>'
    )
st.markdown('<div class="state-grid">' + ''.join(state_html) + '</div>', unsafe_allow_html=True)
st.caption("Rule-based descriptors only. Each axis is independent; missing inputs remain N/A. No composite bullish/bearish score is calculated.")

with st.expander("Market State definitions"):
    st.markdown("""
- **Trend:** price distance from confirmed 200d MA and 50w MA; both > +10% = well above, both > 0% = above, both < −10% = well below, both < 0% = below, otherwise mixed.
- **Positioning:** Deribit BTC perpetual funding is classified as negative / neutral / positive / very positive. Current Deribit perpetual OI is shown as context. Free public OI history is not estimated, so no OI-level or OI-change label is produced in this cloud-safe version.
- **Funding:** < −0.005%/8h = negative; −0.005% to +0.005% = neutral; > +0.005% to +0.020% = positive; > +0.020% = very positive.
- **Volatility:** 30d annualized RV <30% = low; 30–<50% = moderate; 50–<70% = elevated; ≥70% = high.
- **Options:** ~30d ATM IV minus 30d RV < −5 pp = IV below RV; > +5 pp = IV above RV; otherwise near RV. 25Δ RR adds directional relative pricing: > +0.5 pp = calls richer; < −0.5 pp = puts richer; otherwise near balanced.
- **Futures curve:** the nearest dated future with at least 7 days remaining is used for Market State. Annualized basis <0% = backwardation; 0–<3% = mild contango; 3–<8% = contango; ≥8% = steep contango. Contracts under 7 days remain visible below but are excluded from this classification.

These labels describe the observed state; they do not imply future returns.
""")

st.header("PRICE & TREND")
if enriched is None:
    st.warning("Price history is unavailable. Other sections may still work.")
else:
    lookback = st.segmented_control("Range", ["90D", "1Y", "2Y"], default="1Y")
    days = {"90D": 90, "1Y": 365, "2Y": 730}[lookback]
    chart_df = enriched.tail(days)
    overlays = st.multiselect("Overlays", ["50d MA", "200d MA", "50w MA", "52w high"], default=["50d MA", "200d MA", "50w MA"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.04, row_heights=[.75, .25])
    fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df.close, name="BTC/USDT", line=dict(color="#f5a623", width=2)), row=1, col=1)
    overlay_map = {"50d MA": ("ma50", "#48a9ff"), "200d MA": ("ma200", "#d66efd"), "50w MA": ("ma50w", "#3ddc97"), "52w high": ("high52w", "#9ca3af")}
    for label in overlays:
        col, color = overlay_map[label]
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df[col], name=label, line=dict(color=color, width=1.4)), row=1, col=1)
    fig.add_trace(go.Bar(x=chart_df.index, y=chart_df.volume, name="Volume (BTC)", marker_color="#526172"), row=2, col=1)
    fig.update_layout(height=520, margin=dict(l=4,r=4,t=15,b=4), legend=dict(orientation="h", y=1.02), hovermode="x unified")
    st.plotly_chart(lock_chart(fig), width="stretch", config=PLOTLY_CONFIG)
    metrics([("RSI (14)", number(technical.get("rsi14"))), ("ATR (14) / price", pct(technical.get("atr14_pct"))), ("30d realized vol", pct(technical.get("rv30"))), ("Latest confirmed close", money(technical.get("close")))])
    with st.expander("RSI & realized volatility"):
        sub = make_subplots(rows=2, cols=1, shared_xaxes=True)
        sub.add_trace(go.Scatter(x=chart_df.index, y=chart_df.rsi14, name="RSI 14"), row=1, col=1)
        sub.add_hline(y=70, line_dash="dot", row=1, col=1); sub.add_hline(y=30, line_dash="dot", row=1, col=1)
        sub.add_trace(go.Scatter(x=chart_df.index, y=chart_df.rv30, name="RV 30d %"), row=2, col=1)
        sub.update_layout(height=430, margin=dict(l=4,r=4,t=20,b=4), showlegend=False)
        st.plotly_chart(lock_chart(sub), width="stretch", config=PLOTLY_CONFIG)

st.header("DERIVATIVES")
if "derivatives" not in data:
    st.warning("Deribit derivatives data is currently unavailable.")
else:
    deriv, oi, funding, deriv_updated = data["derivatives"]
    oi_contracts = deriv.get("open_interest_contracts")
    metrics([("Deribit perp OI", "N/A" if oi_contracts is None else f"{oi_contracts:,.0f} contracts"), ("OI 24h change", "N/A"), ("OI 7d change", "N/A"), ("Latest funding / 8h", pct(deriv.get("funding_rate")*100 if deriv.get("funding_rate") is not None else None, 4)), ("Perp premium", pct(deriv.get("spot_perp_basis_pct"), 3)), ("Mark price", money(deriv.get("mark_price")))])
    if not oi.empty:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if enriched is not None:
            recent = enriched[enriched.index >= oi.index.min()]
            fig.add_trace(go.Scatter(x=recent.index, y=recent.close, name="BTC/USDT", line=dict(color="#f5a623")), secondary_y=False)
        fig.add_trace(go.Scatter(x=oi.index, y=oi.oi_usdt/1e9, name="OI ($B)", line=dict(color="#48a9ff")), secondary_y=True)
        fig.update_layout(height=350, margin=dict(l=4,r=4,t=15,b=4), legend=dict(orientation="h"), hovermode="x unified")
        st.plotly_chart(lock_chart(fig), width="stretch", config=PLOTLY_CONFIG)
    if not funding.empty:
        f = go.Figure(go.Bar(x=funding.index, y=funding.funding_rate*100, marker_color=["#3ddc97" if x >= 0 else "#ff667a" for x in funding.funding_rate]))
        f.update_layout(height=280, margin=dict(l=4,r=4,t=30,b=4), title="Funding rate history (%)", showlegend=False)
        st.plotly_chart(lock_chart(f), width="stretch", config=PLOTLY_CONFIG)
    if "delivery" in data:
        delivery, _ = data["delivery"]
        if not delivery.empty:
            st.subheader("Dated futures basis")
            basis_cards = []
            for _, row in delivery.sort_values("days").iterrows():
                expiry = pd.Timestamp(row["expiry"]).strftime("%d %b %Y")
                basis_cards.append((f"{row['contract']} · {int(round(row['days']))}d", f"{row['basis_pct']:+.2f}% · ann. {row['annualized_basis_pct']:+.2f}% · {expiry}"))
            metrics(basis_cards)
    st.caption(f"Deribit · BTC-PERPETUAL and listed BTC dated futures · current OI snapshot · funding shown as 8h equivalent · {stamp(deriv_updated)}")

st.header("OPTIONS")
if "options" not in data:
    st.warning("Deribit options data is currently unavailable.")
else:
    opt, term, opt_updated = data["options"]
    rv = technical.get("rv30")
    spread = opt["atm_30d_iv"] - rv if rv is not None and not pd.isna(rv) else None
    rr = opt.get("rr_25d")
    rr_read = "N/A" if rr is None else ("Calls richer" if rr > 0.5 else "Puts richer" if rr < -0.5 else "Near balanced")
    metrics([("~30d ATM IV", pct(opt["atm_30d_iv"])), ("30d realized vol", pct(rv)), ("IV − RV", pct(spread)), ("25Δ Risk Reversal", pct(rr)), ("RR interpretation", rr_read), ("Selected expiry", opt["atm_30d_expiry"].strftime("%d %b %Y"))])
    fig = go.Figure(go.Scatter(x=term.days, y=term.atm_iv, mode="lines+markers", line=dict(color="#d66efd")))
    fig.update_layout(height=310, margin=dict(l=4,r=4,t=35,b=4), title="ATM IV term structure", xaxis_title="Days to expiry", yaxis_title="IV (%)")
    st.plotly_chart(lock_chart(fig), width="stretch", config=PLOTLY_CONFIG)
    st.caption(f"Deribit BTC options · nearest listed expiry to 30 days ({opt['atm_30d_days']:.1f}d), nearest strike ${opt['atm_30d_strike']:,.0f}, mean of {opt['atm_30d_legs']} available call/put mark IV legs · {stamp(opt_updated)}")
    if opt.get("rr_25d") is not None:
        st.caption(f"25Δ RR = Call IV {opt['call_25d_iv']:.2f}% − Put IV {opt['put_25d_iv']:.2f}% = {opt['rr_25d']:+.2f} pp · Deribit mark IV and Greeks · {opt['rr_25d_method']}")
    else:
        unsupported_note(f"25Δ Risk Reversal unavailable for this expiry; no value is estimated. {opt.get('rr_25d_method', '')}")

st.header("CRYPTO LIQUIDITY")
if "stablecoins" not in data:
    st.warning("DefiLlama stablecoin data is currently unavailable.")
else:
    stable, stable_history, stable_updated = data["stablecoins"]
    metrics([
        ("USD stablecoin supply", f"${stable['total_supply_usd']/1e9:.1f}B"),
        ("7d change", pct(stable.get("change_7d"), 2)),
        ("30d change", pct(stable.get("change_30d"), 2)),
        ("90d change", pct(stable.get("change_90d"), 2)),
        ("USDT dominance", pct_plain(stable.get("usdt_dominance"), 1)),
    ])
    stable_chart = stable_history.tail(730)
    sf = go.Figure(go.Scatter(x=stable_chart.index, y=stable_chart.supply_usd/1e9, name="USD stablecoin supply", line=dict(width=2)))
    sf.update_layout(height=310, margin=dict(l=4,r=4,t=35,b=4), title="USD-pegged stablecoin supply", yaxis_title="$B", hovermode="x unified")
    st.plotly_chart(lock_chart(sf), width="stretch", config=PLOTLY_CONFIG)
    st.caption(f"DefiLlama · USD-pegged stablecoins · circulating peggedUSD supply proxy · latest observation {stamp(stable_updated)}")
    st.caption("Observation only: supply growth/shrinkage is not interpreted here as bullish, bearish, fear, or a BTC return forecast. Price-marked market cap and token supply are conceptually different during a depeg.")

st.header("FLOWS")
st.subheader("US Spot BTC ETF flows")
if "etf_flows" not in data:
    st.warning("Farside US spot BTC ETF flow data is currently unavailable.")
else:
    etf, etf_history, etf_updated = data["etf_flows"]
    metrics([
        ("Latest complete day", flow_money_m(etf.get("latest_total_m"))),
        ("5 trading days", flow_money_m(etf.get("five_day_total_m"))),
        ("20 trading days", flow_money_m(etf.get("twenty_day_total_m"))),
        ("Latest date", pd.Timestamp(etf["latest_date"]).strftime("%d %b %Y")),
    ])
    flow_chart = etf_history["Total"].tail(30).dropna()
    ff = go.Figure(go.Bar(
        x=flow_chart.index, y=flow_chart.values,
        marker_color=["#3ddc97" if x >= 0 else "#ff667a" for x in flow_chart.values],
        name="Net flow (US$m)",
    ))
    ff.add_hline(y=0, line_width=1, line_color="#526172")
    ff.update_layout(height=310, margin=dict(l=4,r=4,t=35,b=4), title="US Spot BTC ETF net flow · latest 30 complete trading days", yaxis_title="US$m", hovermode="x unified", showlegend=False)
    st.plotly_chart(lock_chart(ff), width="stretch", config=PLOTLY_CONFIG)
    with st.expander("Latest ETF breakdown"):
        breakdown = etf.get("latest_breakdown_m", {})
        breakdown_df = pd.DataFrame({"ETF": list(breakdown.keys()), "Net flow (US$m)": list(breakdown.values())})
        st.dataframe(breakdown_df, hide_index=True, width="stretch")
    st.caption(f"Farside Investors · US$m · latest complete day {pd.Timestamp(etf['latest_date']).strftime('%d %b %Y')} · fetched {stamp(etf_updated)}")
    st.caption("Conservative completeness rule: '-' is never treated as zero. A day is used only when all ETF columns currently active in the recent Farside table and Total are populated.")

st.subheader("BTC Exchange Netflow")
if "exchange_flows" not in data:
    st.warning("Coin Metrics BTC exchange-flow data is currently unavailable.")
else:
    ex, ex_history, ex_updated = data["exchange_flows"]
    def btc_flow(value):
        if value is None or pd.isna(value): return "N/A"
        sign = "+" if value > 0 else "−" if value < 0 else ""
        return f"{sign}{abs(float(value)):,.0f} BTC"
    metrics([
        ("Latest Netflow", btc_flow(ex.get("latest_netflow_btc"))),
        ("7d Netflow", btc_flow(ex.get("seven_day_netflow_btc"))),
        ("30d Netflow", btc_flow(ex.get("thirty_day_netflow_btc"))),
        ("Latest date", pd.Timestamp(ex["latest_date"]).strftime("%d %b %Y")),
    ])
    ex_chart = ex_history["Netflow_BTC"].tail(90).dropna()
    ef = go.Figure(go.Bar(
        x=ex_chart.index, y=ex_chart.values,
        marker_color=["#4aa3ff" if x >= 0 else "#a78bfa" for x in ex_chart.values],
        name="Netflow (BTC)",
    ))
    ef.add_hline(y=0, line_width=1, line_color="#526172")
    ef.update_layout(height=310, margin=dict(l=4,r=4,t=35,b=4), title="Aggregate BTC exchange netflow · latest 90 days", yaxis_title="BTC", hovermode="x unified", showlegend=False)
    st.plotly_chart(lock_chart(ef), width="stretch", config=PLOTLY_CONFIG)
    st.caption(f"Coin Metrics Community API · Netflow = exchange inflow − exchange outflow · latest observation {pd.Timestamp(ex['latest_date']).strftime('%d %b %Y')} · fetched {stamp(ex_updated)}")
    st.caption("Aggregate exchange activity identified by Coin Metrics. Exchange-to-exchange activity is excluded from aggregate flows. Negative netflow means outflow exceeded inflow; it is not interpreted here as a trading signal.")
unsupported_note("Exchange balance — not yet supported. Gaps are not estimated.")

# Machine-readable snapshot. This is generated from the same in-memory values
# shown above; it does not refetch or estimate missing data. Streamlit's local
# filesystem is ephemeral, so persistence/public hosting is a separate step.
deriv_snapshot = data["derivatives"][0] if "derivatives" in data else None
options_snapshot = data["options"][0] if "options" in data else None
stable_snapshot = data["stablecoins"][0] if "stablecoins" in data else None
etf_snapshot = data["etf_flows"][0] if "etf_flows" in data else None
exchange_snapshot = data["exchange_flows"][0] if "exchange_flows" in data else None
source_times = {
    "market": data.get("market", (None, None))[1],
    "spot": data.get("spot", (None, None))[1],
    "derivatives": data.get("derivatives", (None, None, None, None))[3],
    "delivery": data.get("delivery", (None, None))[1],
    "options": data.get("options", (None, None, None))[2],
    "stablecoins": data.get("stablecoins", (None, None, None))[2],
    "etf_flows": data.get("etf_flows", (None, None, None))[2],
    "exchange_flows": data.get("exchange_flows", (None, None, None))[2],
}
latest_snapshot = build_snapshot(
    market=market, technical=technical, states=states, deriv=deriv_snapshot,
    options=options_snapshot, stablecoins=stable_snapshot, etf=etf_snapshot,
    exchange_flows=exchange_snapshot, delivery=delivery_for_state,
    source_times=source_times, errors=errors,
)
latest_snapshot_text = snapshot_json(latest_snapshot)

st.header("DATA EXPORT")
st.download_button(
    "Download latest_snapshot.json",
    data=latest_snapshot_text,
    file_name="latest_snapshot.json",
    mime="application/json",
    width="stretch",
)
st.caption("Machine-readable snapshot of the same observations shown on this page. Missing values remain null; no gaps are estimated. Persistence and a stable public JSON URL are the next storage step.")

st.header("RESEARCH LINKS")
st.caption("External tools for deeper inspection. These links do not feed the dashboard calculations.")
research_links = [
    ("🔥 CoinGlass · Liquidation Heatmap", "https://www.coinglass.com/ja/pro/futures/LiquidationHeatMap?coin=BTC&type=symbol", "Estimated BTC liquidation clusters"),
    ("📈 TradingView · BTCUSD", "https://www.tradingview.com/symbols/BTCUSD/", "Interactive BTC chart and indicators"),
    ("⛓️ mempool.space", "https://mempool.space/", "Bitcoin blocks, fees and network activity"),
    ("🏦 Farside · BTC ETF Flows", "https://farside.co.uk/btc/", "Source table for US spot BTC ETF flows"),
    ("⚙️ Deribit · BTC Options", "https://www.deribit.com/options/BTC", "BTC options market and chain"),
]
for i in range(0, len(research_links), 2):
    cols = st.columns(2)
    for col, (label, url, description) in zip(cols, research_links[i:i+2]):
        with col:
            st.link_button(label, url, width="stretch")
            st.caption(description)

st.header("DATA SOURCES")
sources = [
    ["BTC/USD spot & ATH", "CoinGecko", "Aggregated BTC/USD", "Current snapshot", stamp(market_updated)],
    ["OHLCV & indicators", "Binance Spot", "BTCUSDT", "1 day", stamp(data.get("spot", (None,None))[1])],
    ["OI / funding / perp basis", "Deribit", "BTC-PERPETUAL", "current / 8h equivalent", stamp(data.get("derivatives", (None,None,None,None))[3])],
    ["Options IV", "Deribit", "BTC listed options", "Current summary", stamp(data.get("options", (None,None,None))[2])],
    ["Stablecoin supply", "DefiLlama", "USD-pegged stablecoins", "Daily history", stamp(data.get("stablecoins", (None,None,None))[2])],
    ["US Spot BTC ETF flows", "Farside Investors", "US spot BTC ETFs", "Daily / trading days", stamp(data.get("etf_flows", (None,None,None))[2])],
    ["BTC Exchange Netflow", "Coin Metrics Community", "Aggregate identified exchanges", "Daily", stamp(data.get("exchange_flows", (None,None,None))[2])],
]
st.dataframe(pd.DataFrame(sources, columns=["Metric","Provider","Product","Granularity","Updated"]), hide_index=True, width="stretch")
if errors:
    with st.expander("Data source status"):
        for name, error in errors.items(): st.markdown(f'<div class="status"><b>{name}</b>: N/A · {error}</div><br>', unsafe_allow_html=True)
st.caption("All timestamps are UTC. Values can differ across venues. Exchange Netflow is the Coin Metrics aggregate identified-exchange series; other venue-specific values are not cross-exchange aggregated. This dashboard is for research, not investment advice.")
