"""
commentary.py
Generates 2-3 sentences of plain-English commentary per selected stock,
using the Anthropic API. Grounded strictly in the computed metrics —
the prompt forbids inventing facts not present in the metrics dict.
"""

import os
import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You write brief newsletter commentary for a Quality-At-a-Reasonable-Price
(QARP) stock screen for retail investors. For each stock, write exactly 2-3 sentences covering:
(1) why it qualifies as quality (cite the specific metric(s) provided), and
(2) why the valuation looks reasonable (cite the specific metric(s) provided).

Rules:
- Use ONLY the metrics provided. Never invent business details, news, or facts not given to you.
- Do not give a buy/sell recommendation or price target.
- Plain, direct language. No hype words ("amazing", "must-buy").
- End with nothing else — just the 2-3 sentences, no headers or bullet points.
"""


def generate_commentary(ticker: str, metrics: dict) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    metric_summary = (
        f"Ticker: {ticker}\n"
        f"Name: {metrics.get('name', ticker)}\n"
        f"Sector: {metrics.get('sector', '—')}\n"
        f"ROE: {metrics.get('roe')}\n"
        f"ROIC (estimated): {metrics.get('roic')}\n"
        f"Gross margin: {metrics.get('gross_margin')}\n"
        f"Trailing P/E: {metrics.get('trailing_pe')}\n"
        f"PEG ratio: {metrics.get('peg')}\n"
        f"Debt/Equity: {metrics.get('debt_to_equity')}\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=250,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": metric_summary}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


def generate_all(ranked_stocks: list) -> dict:
    """ranked_stocks: list of RankedStock. Returns {ticker: commentary_text}."""
    out = {}
    for stock in ranked_stocks:
        try:
            out[stock.ticker] = generate_commentary(stock.ticker, stock.metrics)
        except Exception as e:
            out[stock.ticker] = f"(commentary generation failed: {e})"
    return out
