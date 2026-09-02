"""
qarp_screen.py
Quality At a Reasonable Price screen.

QUALITY filters:
  - Return on Equity (ROE)          >= MIN_ROE
  - Return on Invested Capital*     >= MIN_ROIC
  - Gross margin                    >= MIN_GROSS_MARGIN
  - Debt / Equity                   <= MAX_DEBT_EQUITY
  - Positive trailing EPS (profitable)

REASONABLE PRICE filters:
  - PEG ratio                       <= MAX_PEG
  - Trailing P/E                    within (0, MAX_PE]
  - Price / Free Cash Flow          <= MAX_P_FCF   (if FCF available)

* ROIC is computed manually (yfinance doesn't expose it directly):
    ROIC = NOPAT / Invested Capital
    NOPAT = EBIT * (1 - effective tax rate)
    Invested Capital = Total Debt + Total Equity - Cash & Equivalents
"""

import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("qarp")

# ---- Tunable thresholds ----
MIN_ROE = 0.15
MIN_ROIC = 0.10
MIN_GROSS_MARGIN = 0.30
MAX_DEBT_EQUITY = 1.0
MAX_PEG = 2.0
MAX_PE = 30.0
MAX_P_FCF = 25.0
MIN_MARKET_CAP = 0  # set via env in run_qarp_scan.py; 0 = no floor (full universe)

MAX_WORKERS = 6           # keep concurrency modest for the heavy .info fetch to avoid Yahoo rate-limit bans
QUICK_FILTER_MAX_WORKERS = 15  # fast_info is a much lighter call, safe to run with more concurrency
REQUEST_DELAY_RANGE = (0.4, 1.1)  # jittered delay per request
QUICK_FILTER_DELAY_RANGE = (0.1, 0.3)
MAX_RETRIES = 2


@dataclass
class QarpResult:
    ticker: str
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)


def _safe_get(d: dict, key, default=None):
    v = d.get(key, default)
    return v if v is not None else default


def quick_market_cap_check(ticker: str) -> tuple[str, float | None]:
    """Lightweight pre-filter pass. yfinance's fast_info hits a much cheaper
    endpoint than .info (no financials/balance sheet), so this lets us drop
    thousands of tickers below MIN_MARKET_CAP before ever paying for the
    expensive full fetch in screen_one()."""
    try:
        time.sleep(random.uniform(*QUICK_FILTER_DELAY_RANGE))
        t = yf.Ticker(ticker)
        fi = t.fast_info
        cap = fi.get("market_cap") if hasattr(fi, "get") else getattr(fi, "market_cap", None)
        return ticker, cap
    except Exception:
        return ticker, None


def prefilter_by_market_cap(tickers: list[str], min_cap: float, max_workers: int = QUICK_FILTER_MAX_WORKERS) -> list[str]:
    """Returns only tickers whose market cap clears min_cap. If min_cap is 0
    (no floor set), skips the pre-filter entirely and returns tickers unchanged
    — no point paying for an extra pass with nothing to filter on."""
    if not min_cap:
        return tickers

    survivors = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(quick_market_cap_check, tk): tk for tk in tickers}
        done = 0
        for fut in as_completed(futures):
            done += 1
            ticker, cap = fut.result()
            if cap is not None and cap >= min_cap:
                survivors.append(ticker)
            if done % 500 == 0:
                log.info(f"pre-filtered {done}/{len(tickers)} — {len(survivors)} above cap floor so far")
    log.info(f"Market cap pre-filter: {len(survivors)}/{len(tickers)} tickers cleared ${min_cap:,.0f}")
    return survivors


def _compute_roic(info: dict, financials, balance_sheet) -> float | None:
    try:
        ebit = None
        if financials is not None and not financials.empty and "EBIT" in financials.index:
            ebit = financials.loc["EBIT"].iloc[0]
        if ebit is None:
            ebit = _safe_get(info, "ebitda")  # fallback approximation
        tax_rate = _safe_get(info, "effectiveTaxRate", 0.21) or 0.21
        nopat = ebit * (1 - tax_rate)

        total_debt = _safe_get(info, "totalDebt", 0) or 0
        total_equity = None
        if balance_sheet is not None and not balance_sheet.empty:
            for key in ("Total Stockholder Equity", "Common Stock Equity", "Stockholders Equity"):
                if key in balance_sheet.index:
                    total_equity = balance_sheet.loc[key].iloc[0]
                    break
        if total_equity is None:
            total_equity = _safe_get(info, "marketCap", 0)  # rough fallback
        cash = _safe_get(info, "totalCash", 0) or 0

        invested_capital = (total_debt or 0) + (total_equity or 0) - cash
        if not invested_capital or invested_capital <= 0:
            return None
        return nopat / invested_capital
    except Exception:
        return None


def screen_one(ticker: str) -> QarpResult:
    for attempt in range(MAX_RETRIES + 1):
        try:
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
            t = yf.Ticker(ticker)
            info = t.info
            if not info or info.get("regularMarketPrice") is None:
                return QarpResult(ticker, False, "no market data")

            market_cap = _safe_get(info, "marketCap", 0) or 0
            if MIN_MARKET_CAP and market_cap < MIN_MARKET_CAP:
                return QarpResult(ticker, False, "below market cap floor")

            roe = _safe_get(info, "returnOnEquity")
            gross_margin = _safe_get(info, "grossMargins")
            debt_to_equity = _safe_get(info, "debtToEquity")
            trailing_eps = _safe_get(info, "trailingEps")
            trailing_pe = _safe_get(info, "trailingPE")
            peg = _safe_get(info, "pegRatio")
            fcf = _safe_get(info, "freeCashflow")

            financials = t.financials if hasattr(t, "financials") else None
            balance_sheet = t.balance_sheet if hasattr(t, "balance_sheet") else None
            roic = _compute_roic(info, financials, balance_sheet)

            metrics = {
                "market_cap": market_cap,
                "roe": roe,
                "roic": roic,
                "gross_margin": gross_margin,
                "debt_to_equity": (debt_to_equity / 100 if debt_to_equity and debt_to_equity > 5 else debt_to_equity),
                "trailing_eps": trailing_eps,
                "trailing_pe": trailing_pe,
                "peg": peg,
                "free_cash_flow": fcf,
                "name": _safe_get(info, "shortName", ticker),
                "sector": _safe_get(info, "sector", "—"),
            }

            # ---- Quality gate ----
            if trailing_eps is None or trailing_eps <= 0:
                return QarpResult(ticker, False, "unprofitable", metrics)
            if roe is None or roe < MIN_ROE:
                return QarpResult(ticker, False, "ROE below threshold", metrics)
            if roic is None or roic < MIN_ROIC:
                return QarpResult(ticker, False, "ROIC below threshold", metrics)
            if gross_margin is not None and gross_margin < MIN_GROSS_MARGIN:
                return QarpResult(ticker, False, "gross margin below threshold", metrics)
            de = metrics["debt_to_equity"]
            if de is not None and de > MAX_DEBT_EQUITY:
                return QarpResult(ticker, False, "debt/equity above threshold", metrics)

            # ---- Reasonable price gate ----
            if trailing_pe is None or trailing_pe <= 0 or trailing_pe > MAX_PE:
                return QarpResult(ticker, False, "P/E outside band", metrics)
            if peg is not None and peg > MAX_PEG:
                return QarpResult(ticker, False, "PEG above threshold", metrics)
            if fcf and market_cap:
                p_fcf = market_cap / fcf if fcf > 0 else None
                metrics["p_fcf"] = p_fcf
                if p_fcf is not None and p_fcf > MAX_P_FCF:
                    return QarpResult(ticker, False, "Price/FCF above threshold", metrics)

            return QarpResult(ticker, True, "passed all QARP filters", metrics)

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            return QarpResult(ticker, False, f"error: {e}")


def run_screen(tickers: list[str], max_workers: int = MAX_WORKERS) -> list[QarpResult]:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(screen_one, tk): tk for tk in tickers}
        done = 0
        for fut in as_completed(futures):
            done += 1
            res = fut.result()
            results.append(res)
            if done % 100 == 0:
                log.info(f"screened {done}/{len(tickers)}")
            if res.passed:
                log.info(f"PASS  {res.ticker}  {res.reason}")
    return results
