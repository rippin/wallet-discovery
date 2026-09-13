# Wallet Observatory

A read-only Solana wallet-discovery and paper-trading dashboard. It samples Pump.fun and Raydium LaunchLab activity, follows candidate wallets, and measures subsequent token performance after research delays.

## Preview

```sh
PYTHONPATH=src python3 -m wallet_observatory --demo --port 8765
```

Open <http://127.0.0.1:8765>. The demo uses synthetic data in a separate database and does not scan the blockchain.

## Start or update on your VPS

Requires Git, Docker, and Docker Compose v2:

```sh
git clone --branch codex/wallet-observatory https://github.com/rippin/wallet-discovery.git
cd wallet-discovery
bash deploy/update.sh
```

Run `bash deploy/update.sh` again for future updates. The script preserves configuration, backs up a running database, and checks dashboard readiness. On first interactive use it prompts for a Helius key and dashboard password; other RPC providers can be configured through `OBS_RPC_URL` in `.env.observatory` beforehand.

See [OBSERVATORY.md](OBSERVATORY.md) for free-tier configuration, IP-based HTTPS, collection limits, wallet reassessment, and backups.

## Features

- Persistent SQLite observations and quota-limited collection.
- Wallet research, token activity, transfer evidence, and collection-health views.
- Prospective delayed-entry estimates, with missing data reported explicitly.
- Manual paper entries of at least $500 and partial or full exits.

Coverage is sampled. Paper fills are estimates, not executable quotes. The application cannot sign transactions or place real trades.

## Development

Python 3.11+; no third-party runtime dependencies. Optional editable installation:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/wallet-observatory --help
```

Run checks:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check src/wallet_observatory/static/app.js
bash -n deploy/update.sh
```

## Background research

The independent [trenching research notes](research/PROFITABLE_MEMECOIN_TRENCHERS.md) and [journal template](research/trading_journal_template.csv) remain available as reference material.
