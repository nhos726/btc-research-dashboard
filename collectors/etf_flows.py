from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser

import pandas as pd
import requests

from config import SETTINGS
from collectors.http import DataSourceError

FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("th", "td") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _flow_number(value: str) -> float | None:
    s = str(value).strip().replace(",", "").replace("$", "")
    if not s or s in {"-", "–", "—", "N/A", "n/a"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1].strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if negative else x


def parse_farside_html(html: str) -> pd.DataFrame:
    parser = _TableParser()
    parser.feed(html)
    target = None
    for table in parser.tables:
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if "Date" in header and "Total" in header and "IBIT" in header:
            target = table
            break
    if target is None:
        raise DataSourceError("Farside ETF table not found")

    header = [c.strip() for c in target[0]]
    rows = []
    for raw in target[1:]:
        if len(raw) < len(header):
            raw = raw + [""] * (len(header) - len(raw))
        row = dict(zip(header, raw[:len(header)]))
        if str(row.get("Date", "")).strip().lower() == "total":
            continue
        dt = pd.to_datetime(row.get("Date"), format="%d %b %Y", errors="coerce", utc=True)
        if pd.isna(dt):
            continue
        parsed = {"date": dt}
        for col in header[1:]:
            parsed[col] = _flow_number(row.get(col, ""))
        rows.append(parsed)

    if not rows:
        raise DataSourceError("Farside ETF table contained no dated rows")
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last").set_index("date")


def _complete_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Conservative completion rule: all currently active ETF columns must be populated.

    Farside uses '-' both while a value is unavailable and in some historical rows. We do
    not convert '-' to zero. Active columns are inferred from the latest 60 published rows;
    a row is complete only when each of those columns and Total is numeric.
    """
    etf_cols = [c for c in df.columns if c != "Total"]
    recent = df.tail(60)
    active = [c for c in etf_cols if recent[c].notna().any()]
    required = active + ["Total"]
    return df[df[required].notna().all(axis=1)].copy()


def fetch_etf_flows():
    try:
        response = requests.get(
            FARSIDE_URL,
            timeout=SETTINGS.request_timeout,
            headers={"User-Agent": "Mozilla/5.0 BTC-Research-Dashboard/0.2.8"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DataSourceError(f"Farside request failed: {type(exc).__name__}") from exc

    history = parse_farside_html(response.text)
    complete = _complete_rows(history)
    if complete.empty:
        raise DataSourceError("No complete Farside ETF flow day found")

    latest = complete.iloc[-1]
    latest_date = complete.index[-1]
    summary = {
        "latest_date": latest_date,
        "latest_total_m": float(latest["Total"]),
        "five_day_total_m": float(complete["Total"].tail(5).sum()),
        "twenty_day_total_m": float(complete["Total"].tail(20).sum()),
        "latest_breakdown_m": {c: float(latest[c]) for c in complete.columns if c != "Total" and pd.notna(latest[c])},
        "complete_days": int(len(complete)),
    }
    return summary, complete, datetime.now(timezone.utc)
