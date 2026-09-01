# QARP Weekly — Kronos Kapital

Scans full NYSE, NASDAQ, and OMX Stockholm listings, ranks candidates with a
composite QARP score (not a single-metric sort), generates commentary via
Claude, emails you a review copy, and creates a Substack **draft** (never
auto-published by default) every Monday at 23:00 CET/CEST.

## Pipeline

1. `fetch_universe.py` — full ticker list, 3 exchanges
2. `qarp_screen.py` — base quality + reasonable-price filter
3. `rank_and_select.py` — multi-year trend check, composite z-score ranking,
   outlier flagging, sector diversification cap → top 5
4. `commentary.py` — Claude writes 2-3 grounded sentences per pick
5. `send_email.py` — review email to you, always sent, shows every flag
6. `publish_substack.py` — creates a Substack draft; publishes only if
   `PUBLISH_MODE=publish`

## Setup checklist

1. **Repo**: push this folder to a GitHub repo (public repos get unlimited
   free Actions minutes; private repos get 2,000 min/month free).
2. **Gmail**: enable 2FA on the sending account, generate an
   [app password](https://myaccount.google.com/apppasswords).
3. **Anthropic API key**: create one at console.anthropic.com. This is a
   pay-as-you-go API cost (small — a few cents/week for 5 short commentary
   calls), the one piece that isn't fully $0.
4. **Substack**: create the publication in the Substack UI first (name,
   branding, free/paid tier pricing, connect Stripe for payouts). The
   pipeline only drafts *posts* — it doesn't set up the publication itself.
5. **GitHub secrets** (Settings → Secrets and variables → Actions):
   `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL`, `ANTHROPIC_API_KEY`,
   `SUBSTACK_EMAIL`, `SUBSTACK_PASSWORD`, `SUBSTACK_PUBLICATION_URL`,
   and optionally `MIN_MARKET_CAP` / `PUBLISH_MODE`.
6. **Test it**: Actions → QARP Weekly Scan → Run workflow → `force_run: true`.
   Confirm the review email arrives and the Substack draft appears correctly
   — do this a few times before ever setting `PUBLISH_MODE=publish`.
7. **Compliance**: talk to a lawyer about whether publishing paid stock
   picks alongside your ARN-366802 MFD registration needs separate
   disclosure/registration in your jurisdiction — this is research
   commentary, not fund distribution, and the two are regulated differently.
   Add a clear "not personalized advice" disclaimer to the publication
   (a placeholder is already in the generated post body).
8. **Watch it manually first**: leave `PUBLISH_MODE=draft` (the default) for
   several cycles. Review the flagged outliers and trend rejections yourself
   before trusting the pipeline to publish unattended.

## Known constraints

- **Rate limits**: full NYSE+NASDAQ (~6,000 tickers) via yfinance on GitHub's
  shared runners risks Yahoo rate-limiting. Set `MIN_MARKET_CAP` if runs
  start failing.
- **Runtime**: `timeout-minutes: 330` gives headroom under GitHub's 6-hour
  job cap, but very large universes can still time out.
- **OMX Stockholm list**: hand-maintained in `omx_stockholm.py` — no free
  bulk API exists for Nasdaq Nordic constituents.
- **ROIC**: computed manually (EBIT × (1 − effective tax rate) ÷ invested
  capital) since yfinance doesn't expose it directly — treat as approximate.
- **Substack integration**: uses the unofficial `python-substack` library
  (Substack has no public API). If Substack changes its internals this step
  can break — the review email is designed to keep working regardless.
- **No screen predicts future returns.** This ranks historical fundamentals;
  it is not investment advice and should be labeled as such to subscribers.
