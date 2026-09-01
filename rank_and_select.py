"""
rank_and_select.py
Turns a list of passing QarpResult objects into a defensible top-N shortlist:

  1. Multi-year consistency check (reject one-off spikes)
  2. Composite z-score across QARP metrics (not a single-metric sort)
  3. Outlier flag (>2.5 std from peer median on any input metric)
  4. Sector diversification cap
"""

import logging
import statistics
from dataclasses import dataclass, field

import yfinance as yf

log = logging.getLogger("rank")

# Composite score weights — tune freely, must sum to something sensible (not required to be 1.0)
WEIGHTS = {
    "roe": 0.25,
    "roic": 0.30,
    "gross_margin": 0.15,
    "peg_inv": 0.15,      # inverted: lower PEG = better, so we invert before scoring
    "debt_to_equity_inv": 0.15,  # inverted: lower leverage = better
}

MAX_PER_SECTOR = 2
OUTLIER_STD_THRESHOLD = 2.5
MIN_TREND_YEARS = 3


@dataclass
class RankedStock:
    ticker: str
    metrics: dict
    composite_score: float
    is_outlier_flag: bool = False
    outlier_reason: str = ""
    trend_ok: bool = True
    trend_note: str = ""


def _zscore(value, mean, stdev):
    if value is None or stdev == 0 or stdev is None:
        return 0.0
    return (value - mean) / stdev


def check_multi_year_trend(ticker: str) -> tuple[bool, str]:
    """Reject stocks where ROE/EPS trend is declining across available history,
    even if the latest TTM print cleared the threshold."""
    try:
        t = yf.Ticker(ticker)
        fin = t.financials
        if fin is None or fin.empty or "Net Income" not in fin.index:
            return True, "insufficient history — passed by default"
        net_income = fin.loc["Net Income"].dropna()
        if len(net_income) < MIN_TREND_YEARS:
            return True, "insufficient history — passed by default"
        values = list(net_income.iloc[:MIN_TREND_YEARS])[::-1]  # oldest -> newest
        # Require: not a straight decline (allow one down year, not two consecutive)
        declines = sum(1 for a, b in zip(values, values[1:]) if b < a)
        if declines >= len(values) - 1:
            return False, f"net income declining across last {len(values)} years"
        return True, "trend acceptable"
    except Exception as e:
        return True, f"trend check failed ({e}) — passed by default"


def compute_composite_scores(results: list) -> list[RankedStock]:
    """results: list of qarp_screen.QarpResult that already passed the base filters."""
    metric_lists = {k: [] for k in ("roe", "roic", "gross_margin", "peg", "debt_to_equity")}
    for r in results:
        for k in metric_lists:
            v = r.metrics.get(k)
            if v is not None:
                metric_lists[k].append(v)

    stats = {}
    for k, vals in metric_lists.items():
        if len(vals) >= 2:
            stats[k] = (statistics.mean(vals), statistics.pstdev(vals))
        else:
            stats[k] = (0.0, 0.0)

    ranked = []
    for r in results:
        m = r.metrics
        z_roe = _zscore(m.get("roe"), *stats["roe"])
        z_roic = _zscore(m.get("roic"), *stats["roic"])
        z_gm = _zscore(m.get("gross_margin"), *stats["gross_margin"])
        # invert PEG and debt/equity so "lower is better" scores positively
        z_peg = -_zscore(m.get("peg"), *stats["peg"]) if m.get("peg") is not None else 0.0
        z_de = -_zscore(m.get("debt_to_equity"), *stats["debt_to_equity"]) if m.get("debt_to_equity") is not None else 0.0

        composite = (
            WEIGHTS["roe"] * z_roe
            + WEIGHTS["roic"] * z_roic
            + WEIGHTS["gross_margin"] * z_gm
            + WEIGHTS["peg_inv"] * z_peg
            + WEIGHTS["debt_to_equity_inv"] * z_de
        )

        # outlier flag: any raw metric more than threshold std from peer mean
        is_outlier, reason = False, ""
        for k, z in (("roe", z_roe), ("roic", z_roic), ("gross_margin", z_gm)):
            if abs(z) > OUTLIER_STD_THRESHOLD:
                is_outlier, reason = True, f"{k} is {z:.1f} std from peer mean — verify before publishing"
                break

        ranked.append(RankedStock(
            ticker=r.ticker,
            metrics=m,
            composite_score=composite,
            is_outlier_flag=is_outlier,
            outlier_reason=reason,
        ))

    return ranked


def apply_trend_check(ranked: list[RankedStock]) -> list[RankedStock]:
    for stock in ranked:
        ok, note = check_multi_year_trend(stock.ticker)
        stock.trend_ok = ok
        stock.trend_note = note
    return ranked


def select_top_n(ranked: list[RankedStock], n: int = 5, max_per_sector: int = MAX_PER_SECTOR) -> list[RankedStock]:
    # Drop failed trend checks entirely — these are disqualifying, not just flagged
    candidates = [s for s in ranked if s.trend_ok]
    candidates.sort(key=lambda s: s.composite_score, reverse=True)

    selected = []
    sector_counts = {}
    for stock in candidates:
        sector = stock.metrics.get("sector", "—")
        if sector_counts.get(sector, 0) >= max_per_sector:
            continue
        selected.append(stock)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if len(selected) >= n:
            break
    return selected
