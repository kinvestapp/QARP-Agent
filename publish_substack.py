"""
publish_substack.py
Creates a DRAFT post on Substack using the unofficial `python-substack` library.

By design this never auto-publishes. PUBLISH_MODE controls behavior:
  - "draft"   (default): creates a draft only, you review + hit publish manually
  - "publish": actually publishes — only use this once you fully trust the pipeline

Substack has no official public API for this, so this relies on session-cookie
auth via python-substack, which can break if Substack changes their internals.
If it does, the review email (send_email.py) still goes out — treat the
Substack step as a convenience, not a hard dependency.
"""

import os
import logging

log = logging.getLogger("substack")


def build_post_body_markdown(ranked_stocks, commentary_by_ticker, scan_date: str) -> str:
    lines = [f"# QARP Weekly — {scan_date}\n"]
    lines.append(
        "Five stocks that passed this week's Quality-At-a-Reasonable-Price screen "
        "across NYSE, NASDAQ, and OMX Stockholm.\n"
    )
    for stock in ranked_stocks:
        m = stock.metrics
        lines.append(f"## {stock.ticker} — {m.get('name', '')}\n")
        if stock.is_outlier_flag:
            lines.append(f"*⚠ {stock.outlier_reason}*\n")
        lines.append(commentary_by_ticker.get(stock.ticker, "") + "\n")
        lines.append(
            f"ROE: {m.get('roe')} · ROIC: {m.get('roic')} · P/E: {m.get('trailing_pe')} · "
            f"PEG: {m.get('peg')} · Debt/Equity: {m.get('debt_to_equity')}\n"
        )
    lines.append(
        "\n---\n*Not investment advice. This is an automated quantitative screen based on "
        "public fundamental data; verify independently before acting.*"
    )
    return "\n".join(lines)


def create_draft(ranked_stocks, commentary_by_ticker, scan_date: str):
    mode = os.environ.get("PUBLISH_MODE", "draft").lower()

    try:
        from substack import Api
        from substack.post import Post
    except ImportError:
        log.warning("python-substack not installed — skipping Substack step. "
                    "Review email was still sent.")
        return None

    api = Api(
        email=os.environ["SUBSTACK_EMAIL"],
        password=os.environ["SUBSTACK_PASSWORD"],
        publication_url=os.environ["SUBSTACK_PUBLICATION_URL"],
    )

    body_md = build_post_body_markdown(ranked_stocks, commentary_by_ticker, scan_date)
    title = f"QARP Weekly — {scan_date}"

    post = Post(title=title, subtitle="Quality-at-a-reasonable-price picks", user_id=api.get_user_id())
    post.add(body_md, post_type="markdown")

    draft = api.post_draft(post.get_draft())
    log.info(f"Substack draft created: {draft.get('id', 'unknown id')}")

    if mode == "publish":
        api.publish_draft(draft["id"])
        log.info("Substack post PUBLISHED (PUBLISH_MODE=publish).")
    else:
        log.info("Substack draft left unpublished (PUBLISH_MODE=draft, the default). "
                  "Review and publish manually.")

    return draft
