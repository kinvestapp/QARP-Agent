"""
run_qarp_scan.py
Entry point run by GitHub Actions, weekly.

Pipeline:
  1. Fetch universe (NYSE, NASDAQ, OMX Stockholm)
  2. Base QARP filter (qarp_screen)
  3. Multi-year trend check + composite z-score ranking + sector cap (rank_and_select)
  4. Claude-generated commentary per pick (commentary)
  5. Review email to the owner — ALWAYS sent, shows every safeguard flag (send_email)
  6. Substack DRAFT created (never auto-published unless PUBLISH_MODE=publish) (publish_substack)
"""

import os
import sys
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import qarp_screen
from fetch_universe import get_full_universe
from rank_and_select import compute_composite_scores, apply_trend_check, select_top_n
from commentary import generate_all
from send_email import send_review_email
from publish_substack import create_draft

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run")

REFERENCE_MONDAY = date(2026, 9, 7)  # any Monday on/after this counts
CADENCE_DAYS = 7  # weekly; change to 14 to go back to biweekly

STOCKHOLM = ZoneInfo("Europe/Stockholm")
TARGET_LOCAL_HOUR = 23
TOP_N = 5


def is_send_slot(now_utc: datetime) -> bool:
    if os.environ.get("FORCE_RUN", "").lower() == "true":
        return True
    local = now_utc.astimezone(STOCKHOLM)
    if local.weekday() != 0:  # Monday
        return False
    if local.hour != TARGET_LOCAL_HOUR:
        return False
    delta_days = (local.date() - REFERENCE_MONDAY).days
    return delta_days >= 0 and delta_days % CADENCE_DAYS == 0


def main():
    now_utc = datetime.now(ZoneInfo("UTC"))
    if not is_send_slot(now_utc):
        log.info(f"{now_utc.isoformat()} is not the scheduled QARP slot — skipping "
                 f"(set FORCE_RUN=true to override).")
        sys.exit(0)

    scan_date = now_utc.astimezone(STOCKHOLM).strftime("%d %B %Y")

    log.info("Fetching universe...")
    universe = get_full_universe()
    for exch, tickers in universe.items():
        log.info(f"{exch}: {len(tickers)} tickers")

    min_cap = float(os.environ.get("MIN_MARKET_CAP", "0"))
    qarp_screen.MIN_MARKET_CAP = min_cap

    all_passed = []
    for exch, tickers in universe.items():
        if min_cap:
            log.info(f"Pre-filtering {exch} ({len(tickers)} tickers) by market cap...")
            tickers = qarp_screen.prefilter_by_market_cap(tickers, min_cap)
            log.info(f"{exch}: {len(tickers)} tickers cleared the cap floor, proceeding to full QARP scan")
        log.info(f"Screening {exch} ({len(tickers)} tickers)...")
        results = qarp_screen.run_screen(tickers)
        passed = [r for r in results if r.passed]
        log.info(f"{exch}: {len(passed)} passed base QARP filters")
        all_passed.extend(passed)

    if not all_passed:
        log.warning("No stocks passed base QARP filters this cycle — nothing to rank or send.")
        sys.exit(0)

    log.info("Scoring and ranking candidates...")
    ranked = compute_composite_scores(all_passed)
    ranked = apply_trend_check(ranked)
    top5 = select_top_n(ranked, n=TOP_N)

    if not top5:
        log.warning("No candidates survived trend check — nothing to send.")
        sys.exit(0)

    log.info(f"Top {len(top5)} selected: {[s.ticker for s in top5]}")

    log.info("Generating commentary via Claude...")
    commentary_by_ticker = generate_all(top5)

    log.info("Sending review email to owner...")
    send_review_email(top5, commentary_by_ticker, scan_date)

    log.info("Creating Substack draft...")
    create_draft(top5, commentary_by_ticker, scan_date)

    log.info("Done. Check your inbox to review, then publish manually from Substack.")


if __name__ == "__main__":
    main()
