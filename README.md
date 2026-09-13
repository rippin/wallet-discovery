# Wallet research workspace

The new continuous scanner and dashboard are documented in [OBSERVATORY.md](OBSERVATORY.md). Start a synthetic preview with `PYTHONPATH=src python3 -m wallet_observatory --demo`.

# Solana Memecoin Research

A read-only CLI that produces timestamped **Consider / Watch / Avoid** research
reports for Solana tokens. It combines:

- SPL mint controls and Token-2022 extensions
- DEX Screener market and liquidity data
- position-sized Jupiter sell-route checks
- largest-holder concentration and best-effort wallet clustering
- optional Birdeye trader enrichment
- optional X recent-post concentration and repetition analysis
- point-in-time JSON snapshots and outcome backtesting

It never signs or submits transactions. Wallet labels describe public on-chain
patterns, not real-world identities.

## Quick start

```bash
python3 memecoin_research.py report \
  --mint TOKEN_MINT \
  --dex-url "https://dexscreener.com/solana/PAIR" \
  --position-usd 500 \
  --holding-period "1-7 days" \
  --output reports/token.md \
  --json-output reports/token.json
```

The public Solana RPC and DEX Screener are enough for a basic report. A dedicated
Solana RPC is strongly recommended because public endpoints are rate-limited.
Optional environment variables are documented in `.env.example`.

Optional console-command installation:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/memecoin-research --help
```

Jupiter quote checks use `https://api.jup.ag/swap/v1/quote` when
`JUPITER_API_KEY` is set, with the keyless `lite-api.jup.ag` endpoint as a
best-effort fallback. The tool only requests a quote; it cannot execute it.

## Useful options

```bash
python3 memecoin_research.py report --help
```

- `--position-usd`: sizes liquidity and sellability checks to the intended trade.
- `--suspected-wallet`: repeatable; includes a public wallet in the investigation.
- `--x-url`: repeatable; records supplied social evidence.
- `--history-signatures`: bounds point-in-time early-activity reconstruction.
- `--wallet-scan`: scans sampled holder transactions for direct/shared funding.
- `--cohort-file`: normalizes component scores against at least ten prior reports
  from the same DEX and pair-age bucket.
- `--offline-fixture`: runs deterministically from a saved provider fixture.

## Backtesting

Reports are immutable point-in-time snapshots. After the selected horizon, add an
`outcome` object and save each record as one JSON line:

```json
{"report":{"timestamp":"2026-01-01T00:00:00Z","verdict":"Avoid","score":31,"components":{"ownership":20,"liquidity":35}},"outcome":{"return_pct":-82,"max_drawdown_pct":-91,"catastrophic":true}}
```

Then run:

```bash
python3 memecoin_research.py backtest --dataset outcomes.jsonl
```

The output includes catastrophic-loss avoidance, false positives, profitable-call
precision, average return, maximum drawdown, chronological folds, and simple
liquidity-only, ownership-only, and deterministic-random baselines.

## Interpretation

- **Consider**: no hard safety gate failed, evidence coverage is adequate, and
  the weighted score is favorable.
- **Watch**: incomplete evidence, marginal pricing, or mixed signals.
- **Avoid**: a hard gate failed or measured risk dominates.

These are research classifications, not financial advice or return guarantees.
Fresh quotes and balances are required immediately before any independent decision.

## Trenching research

The evidence-ranked multichain study and its practical 30-day program are in
[research/PROFITABLE_MEMECOIN_TRENCHERS.md](research/PROFITABLE_MEMECOIN_TRENCHERS.md).
A matching data-entry schema is provided in
[research/trading_journal_template.csv](research/trading_journal_template.csv).
