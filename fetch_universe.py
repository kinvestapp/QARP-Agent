"""
fetch_universe.py
Builds the full ticker universe for NYSE, NASDAQ, and OMX Stockholm.

NYSE/NASDAQ: pulled live from NASDAQ Trader's public symbol directory
(no auth required). These files are the same source most free screeners use.

OMX Stockholm: Nasdaq Nordic doesn't publish an equivalent free bulk file,
so we ship a curated static list (Large + Mid + Small cap, common stock only,
.ST tickers as required by yfinance). Maintain this list in omx_stockholm.py
as constituents change (IPOs, delistings).
"""

import io
import csv
import requests

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"  # includes NYSE, NYSE American, etc.


def _fetch_pipe_delimited(url: str) -> list[dict]:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    text = resp.text
    # Last line is a file-generation timestamp footer, not data
    lines = [l for l in text.splitlines() if l and not l.startswith("File Creation Time")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
    return list(reader)


def get_nasdaq_tickers() -> list[str]:
    rows = _fetch_pipe_delimited(NASDAQ_LISTED_URL)
    tickers = []
    for r in rows:
        symbol = r.get("Symbol", "").strip()
        test_issue = r.get("Test Issue", "N").strip()
        etf = r.get("ETF", "N").strip()
        if not symbol or test_issue == "Y" or etf == "Y":
            continue
        if any(ch in symbol for ch in (".", "$", "^")):
            continue  # skip warrants/units/preferreds with odd suffixes
        tickers.append(symbol)
    return sorted(set(tickers))


def get_nyse_tickers() -> list[str]:
    rows = _fetch_pipe_delimited(OTHER_LISTED_URL)
    tickers = []
    for r in rows:
        symbol = r.get("ACT Symbol", "").strip()
        exchange = r.get("Exchange", "").strip()  # 'N' = NYSE
        test_issue = r.get("Test Issue", "N").strip()
        etf = r.get("ETF", "N").strip()
        if not symbol or test_issue == "Y" or etf == "Y":
            continue
        if exchange != "N":
            continue
        if any(ch in symbol for ch in (".", "$", "^")):
            continue
        tickers.append(symbol)
    return sorted(set(tickers))


def get_omx_stockholm_tickers() -> list[str]:
    from omx_stockholm import OMX_STOCKHOLM_TICKERS
    return sorted(set(OMX_STOCKHOLM_TICKERS))


def get_full_universe() -> dict[str, list[str]]:
    return {
        "NASDAQ": get_nasdaq_tickers(),
        "NYSE": get_nyse_tickers(),
        "OMX_STOCKHOLM": get_omx_stockholm_tickers(),
    }


if __name__ == "__main__":
    universe = get_full_universe()
    for exch, tickers in universe.items():
        print(f"{exch}: {len(tickers)} tickers")
    total = sum(len(v) for v in universe.values())
    print(f"TOTAL: {total} tickers")
