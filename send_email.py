"""
send_email.py
Formats QARP scan results into a Kronos Kapital branded HTML email
and sends via Gmail SMTP (app password auth).
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

AUBERGINE = "#2E1A33"
GOLD = "#C9A24B"
CREAM = "#F7F3EC"


def _fmt_pct(v):
    return f"{v * 100:.1f}%" if v is not None else "—"


def _fmt_num(v, digits=2):
    return f"{v:.{digits}f}" if v is not None else "—"


def build_html(results_by_exchange: dict, scan_date: str) -> str:
    rows_html = ""
    total_passed = 0
    for exchange, results in results_by_exchange.items():
        passed = [r for r in results if r.passed]
        total_passed += len(passed)
        if not passed:
            continue
        rows_html += f"""
        <tr><td colspan="7" style="padding:18px 12px 6px;font-family:Georgia,serif;
            color:{GOLD};font-size:14px;letter-spacing:2px;text-transform:uppercase;
            border-bottom:1px solid {GOLD};">{exchange}</td></tr>
        """
        for r in sorted(passed, key=lambda x: x.metrics.get("roic") or 0, reverse=True):
            m = r.metrics
            rows_html += f"""
            <tr style="border-bottom:1px solid #e5ded0;">
                <td style="padding:8px 12px;font-family:Georgia,serif;color:{AUBERGINE};font-weight:bold;">{r.ticker}</td>
                <td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:13px;color:#444;">{m.get('name','')}</td>
                <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:13px;">{_fmt_pct(m.get('roe'))}</td>
                <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:13px;">{_fmt_pct(m.get('roic'))}</td>
                <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:13px;">{_fmt_num(m.get('trailing_pe'),1)}</td>
                <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:13px;">{_fmt_num(m.get('peg'))}</td>
                <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:13px;">{_fmt_pct(m.get('gross_margin'))}</td>
            </tr>
            """

    if total_passed == 0:
        rows_html = f"""
        <tr><td style="padding:24px 12px;font-family:Georgia,serif;color:{AUBERGINE};">
            No stocks met all QARP thresholds this cycle.</td></tr>
        """

    html = f"""
    <html><body style="margin:0;padding:0;background:{CREAM};">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};padding:32px 0;">
    <tr><td align="center">
    <table width="680" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid {GOLD};">
        <tr><td style="background:{AUBERGINE};padding:28px 32px;">
            <div style="font-family:Georgia,serif;color:{GOLD};font-size:22px;letter-spacing:3px;">KRONOS KAPITAL</div>
            <div style="font-family:Georgia,serif;color:{CREAM};font-size:14px;letter-spacing:2px;margin-top:4px;">
                QARP SCREEN &mdash; {scan_date}</div>
        </td></tr>
        <tr><td style="padding:20px 32px 8px;font-family:Arial,sans-serif;color:#444;font-size:13px;">
            Quality-at-a-reasonable-price scan across NYSE, NASDAQ, and OMX Stockholm.
            {total_passed} stock(s) passed all filters this cycle.
        </td></tr>
        <tr><td style="padding:8px 20px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr style="border-bottom:2px solid {AUBERGINE};">
                    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">Ticker</th>
                    <th align="left" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">Name</th>
                    <th align="right" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">ROE</th>
                    <th align="right" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">ROIC</th>
                    <th align="right" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">P/E</th>
                    <th align="right" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">PEG</th>
                    <th align="right" style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;color:{AUBERGINE};text-transform:uppercase;">Gross Marg.</th>
                </tr>
                {rows_html}
            </table>
        </td></tr>
        <tr><td style="background:{AUBERGINE};padding:16px 32px;">
            <div style="font-family:Arial,sans-serif;color:{CREAM};font-size:11px;">
                Automated QARP scan &middot; K-Invest.app / Kronos Kapital &middot; Not investment advice.
            </div>
        </td></tr>
    </table>
    </td></tr>
    </table>
    </body></html>
    """
    return html


def send_email(results_by_exchange: dict):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    scan_date = datetime.now().strftime("%d %B %Y")
    html = build_html(results_by_exchange, scan_date)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Kronos Kapital — QARP Scan ({scan_date})"
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [recipient], msg.as_string())


def send_review_email(ranked_stocks, commentary_by_ticker, scan_date: str):
    """Always sent to the owner (RECIPIENT_EMAIL) before anything touches Substack.
    Shows the top-5 selection plus every safeguard flag (outlier / trend) so nothing
    reaches subscribers without a human glance first."""
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    rows = ""
    for stock in ranked_stocks:
        m = stock.metrics
        flag = f"<div style='color:#b3261e;font-weight:bold;'>⚠ {stock.outlier_reason}</div>" if stock.is_outlier_flag else ""
        rows += f"""
        <div style="border:1px solid #ddd;margin-bottom:14px;padding:14px;font-family:Arial,sans-serif;">
            <h3 style="margin:0 0 6px;">{stock.ticker} — {m.get('name','')} (score: {stock.composite_score:.2f})</h3>
            {flag}
            <p style="font-size:13px;color:#333;">{commentary_by_ticker.get(stock.ticker,'')}</p>
            <p style="font-size:12px;color:#666;">
                ROE {_fmt_pct(m.get('roe'))} · ROIC {_fmt_pct(m.get('roic'))} ·
                P/E {_fmt_num(m.get('trailing_pe'),1)} · PEG {_fmt_num(m.get('peg'))} ·
                D/E {_fmt_num(m.get('debt_to_equity'))} · Sector {m.get('sector','—')}
            </p>
        </div>
        """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;">
    <h2>QARP Weekly — Review Before Publish ({scan_date})</h2>
    <p>Substack draft has been created (unpublished). Review below, then publish manually
    from the Substack dashboard once satisfied.</p>
    {rows}
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[REVIEW] QARP Weekly draft — {scan_date}"
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [recipient], msg.as_string())
