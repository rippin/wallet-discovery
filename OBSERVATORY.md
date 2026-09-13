# Wallet Observatory

A standalone, read-only Solana research application. It samples **Pump.fun and Raydium LaunchLab activity** to discover buyers, follows candidate wallets on supported trading venues, stores point-in-time observations, and provides manual paper entries and exits. No private keys, signing, order submission, paid streams, or automatic live trades.

This application has no third-party Python runtime dependencies and requires Python 3.11+.

## Local preview

```sh
PYTHONPATH=src python3 -m wallet_observatory --demo --port 8765
```

Open <http://127.0.0.1:8765>. Synthetic data is visibly labeled and stored in `data/demo.sqlite3`. It cannot be opened as the live database. The demo's saved prices intentionally become stale after 10 minutes; use a fresh `--db /tmp/new-demo.sqlite3` for another interactive preview. The demo does not fetch real prices or generate real performance claims.

## Live collection on your Docker VPS

1. Create a free Helius account, generate an API key, and leave paid upgrades/autoscaling disabled. No trading wallet or funded account is required.
2. Copy `.env.observatory.example` to `.env.observatory`. Set `HELIUS_API_KEY` and a unique `OBS_PASSWORD` of at least 7 characters locally on the VPS. Set `OBS_LIVE=1`. Keep this file permissioned `600` and out of Git.
3. Run `docker compose up -d --build`. Docker stores observations in the persistent `observatory-data` volume. One application instance owns both the worker and dashboard. Do not start several collectors against the same database.
4. The container publishes **only** `127.0.0.1:8080`. For initial checks, use `ssh -L 8080:127.0.0.1:8080 user@VPS_IP` and open <http://127.0.0.1:8080> locally. Login username: `research`; password: your `OBS_PASSWORD`.
5. Configure HTTPS below for access directly by IP from other devices. Do not change the published binding to `0.0.0.0` to work around TLS setup.

Configuration: `OBS_RPC_URL` overrides the Helius-derived URL. `OBS_MONTHLY_CREDITS=900000` leaves headroom under the advertised 1M free credits. `OBS_RPC_CREDIT_COST=10` conservatively reserves ten credits for every RPC call, including failures. Confirm actual costs in your account before lowering it. Collection defaults to a five-minute cycle; browser refreshes do not make provider requests. Credentials are read from the environment and never returned through the dashboard API.

## IP-based HTTPS, no domain required

Use the VPS's existing reverse proxy where possible. `deploy/nginx.conf.example` is a host-nginx configuration forwarding to the loopback Docker port. It includes request/body limits. Check existing port 80/443 listeners and firewall rules before installation; do not replace unrelated service configurations.

For a server with port 80 free, Certbot 5.4+ supports a free public IP certificate:

```sh
sudo certbot certonly --standalone --preferred-profile shortlived --ip-address YOUR_PUBLIC_IP
```

Follow Certbot's account prompts locally. Port 80 must be reachable for certificate validation. If an existing webserver uses port 80, use its webroot challenge configuration instead of stopping unrelated services. Substitute the returned certificate paths into the nginx example, validate with `sudo nginx -t`, and reload nginx. Access `https://YOUR_PUBLIC_IP` (port 443); an explicit nonstandard HTTPS port can also be configured in nginx.

Enable Certbot's automatic renewal timer and a deploy hook to reload nginx after renewal; verify with `sudo certbot renew --dry-run`. IP certificates last only six days, so renewal is required. The nginx example listens only on 443, leaving standalone renewal port 80 free; reconfigure the challenge if another service later occupies it. This repository does not change your server firewall, install certificates, or accept certificate-service terms automatically.

## What collection actually covers

- Discovery polls the latest 50 finalized signatures for each launchpad program and chooses up to eight previously unseen signatures by a time-windowed hash, **before** knowing outcomes. It detects sampled launchpad **trades**, not every token creation. Active tokens are more likely to appear; this is not a uniform sample of all launches.
- Both successful and unsuccessful token picks remain in the data. The transaction that first discovered a wallet is excluded from prospective rankings.
- Selected wallets are read across supported Pump.fun, LaunchLab, PumpSwap, Raydium AMM/CPMM/CLMM and recognized Jupiter instructions. Each scan caps history at two 50-signature pages. A cap or unavailable transaction is recorded as a coverage event. Unsupported venues, unidentified token-to-token pairs outside explicitly decoded launchpad pairs or known tracked mints, multisigner complexities, and ambiguous multi-token movements are not asserted to be trades.
- Only recognized swap instruction discriminators plus opposite asset/quote balance movements produce trade observations. Plain transfers and allocations are not classified as purchased tokens. Native SOL quantities remain approximate because rent and tips may share the transaction. There is **no claim of exact realized wallet P&L**.
- LaunchLab retains the platform-config address from the official IDL. StonkFun/BONK labels are intentionally not guessed. The token's source records its first observed venue, not proof of where it was originally minted.
- Direct outer SOL transfers involving tracked wallets are saved as evidence. The dashboard can queue the counterparty for research. Transfers are never merged into a common-owner identity. This pilot does not claim comprehensive insider detection, bundle detection, SPL-transfer tracing, or protection against copy-trader farming.
- RPC credits are split 50% tracking, 30% discovery, 20% revisits, with per-day and per-calendar-month ceilings. An exhausted bucket pauses until its next allowance. Local accounting cannot see other applications using the same key; dedicate a key/account allowance and inspect provider usage. No paid fallback is configured.
- DEX Screener prices are sampled in batches of up to 30 mints, at most 120 tokens per cycle, open paper positions first. Remaining tokens rotate by oldest observation. Pre-graduation tokens without indexed pairs remain unpriced. Provider lag is unknown; timestamps record when **we** received data. Data coverage will narrow as the universe grows.

## Evaluation and wallet lifecycle

Under observation rules v2, eligible signals are **subsequent** purchases made after we first recorded the wallet, regardless of detection delay. Purchases before discovery and invalid future timestamps remain excluded. A new purchase of an already known wallet can qualify whether found by a wallet scan or launchpad discovery. Detection age is retained and results are evaluated separately for fresh (≤10 minutes), delayed (>10 minutes to 60 minutes), and late (>60 minutes) detections. Detection time (not retrospective chain time) starts research delays of 5, 15, and 60 minutes. Each delay has fixed holding horizons of 1h, 6h, 24h, 7d, and 28d. The first saved price within ten minutes **after** each target is used. No earlier or later favorable price is substituted. Missing observations remain missing, not zero returns; low-liquidity estimates are explicitly refused.

All standardized outcomes model a fixed $500 entry. The displayed ranking uses 15-minute entry / 24-hour exit. Each token contributes only its first eligible signal per wallet and detection-age cohort **within the rolling 30-day window**. Cohorts are never pooled. Mature signals without an outcome row still count in the coverage denominator. Promotion needs a qualifying individual cohort with at least eight priced token outcomes in the latest 30 days, at least 80% measurable coverage, a positive median return and at least 60% positive outcomes. These are unvalidated pilot thresholds, not a profitability guarantee. Wallet detail includes the other measured horizons. User paper decisions never feed back into the ranking. Wallet detail also reports observed sells within 15 minutes of buys as a behavior flag; this does not establish copy-trader farming, and missed transactions can undercount exits.

Active wallets are scheduled every five minutes; candidates every 30 minutes (15 minutes if an individual cohort has ≥3 priced tokens, ≥80% coverage, positive median and ≥60% wins); cooldown wallets every six hours; dormant wallets daily, within quotas and queue capacity. Poor mature results cause cooldown. No observed activity for seven days takes precedence over old positive results and causes dormancy. New activity returns insufficient-evidence wallets to candidate status; improved measured outcomes can promote them again. History and status changes are retained. Manual reassessment is available. New rediscovery does not erase old losses.

The pilot does not yet provide statistically validated excess returns against a matched market baseline. Missing markets may disproportionately represent failures; always inspect coverage alongside returns. Paper performance is research evidence, not proof of a tradable edge.

## Paper trading

Open a discovered token, record research notes, and choose an entry of **at least $500**. A manual exit can close a percentage of the remaining position. Entries and exits use the latest saved price no more than ten minutes old; a newer unpriced snapshot blocks using an older apparently good one.

The disclosed approximation applies 1% trading/friction costs plus `2 × notional / reported liquidity` price impact on each side. Positions larger than 1% of reported liquidity are refused. This is deliberately an **indicative model**, not a pool-specific simulation or executable route quote. It does not model transfer taxes, MEV, exact priority fees, pool concentration, or guaranteed sellability. Unpriced positions stay open; unavailable exits never become fictional fills. Per-position notes, partial exits, and realized estimates persist through restarts. There is no cash-account balance or portfolio risk allocation engine.

## Storage, API, and operations

SQLite uses WAL and transactional writes. Tables retain raw sampled transactions, normalized trades, token snapshots, directed transfer evidence, signals, outcomes, assessments, paper positions/exits, usage counters and events. Schema version is stored in `meta`. Version 2 adds signal classification and rule-version fields transactionally. Existing signals keep their eligibility and outcomes, are labeled legacy, and do not promote wallets under the new rules. No history or paper positions are deleted. Returning dormant/cooldown wallets are queued immediately when reassessed as candidates. No runtime data is committed to Git. No automatic history deletion is configured: monitor VPS disk use, especially raw transactions and price snapshots, and archive backups before future retention changes.

Read endpoints: `/api/summary`, `/api/wallet?address=...`, `/api/export`. Authenticated write endpoints: `/api/watch`, `/api/read`, `/api/paper/open`, `/api/paper/close`. Writes require same-origin JSON and `X-Observatory: 1`. Login uses HTTP Basic over your HTTPS reverse proxy. Static assets and API responses have restrictive CSP/no-store headers. API exports are capped dashboard snapshots; the SQLite backup is the complete dataset. Discord can later consume saved signals; no bot connection exists yet.

Back up while running with SQLite's online backup API:

```sh
docker compose cp deploy/backup.py observatory:/tmp/backup.py
docker compose exec observatory python /tmp/backup.py /data/backups/observatory-YYYY-MM-DD.sqlite3
docker compose cp observatory:/data/backups/observatory-YYYY-MM-DD.sqlite3 ./backups/
```

Create the local `backups` directory first and use a unique date/name. Keep an off-VPS copy. To restore, stop the application, preserve the existing volume as a rollback copy, replace the database with the verified backup while stopped, and remove only stale WAL/SHM companions associated with the replaced database. Never copy the main SQLite file alone while it is being written.

Update by committing/reviewing changes on a feature branch, backing up, then `docker compose up -d --build`. Keep the previous Git commit to rebuild for rollback. Check Collection health after deployment: provider errors, page gaps, last successful cycle, and quota exhaustion are visible. No successful ranking is promised after a fixed number of days; sufficient future observations are required.

## Verification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check src/wallet_observatory/static/app.js
```

Tests cover swap/transfer separation, launchpad instruction recognition, duplicates, retrospective exclusion, outcome timing, missing markets, liquidity restrictions, partial exits, stale data, quota persistence, reassessment, HTTP authentication and cross-origin write rejection. Desktop/mobile browser checks and a Docker runtime smoke test were performed. A bounded public-RPC check decoded two finalized LaunchLab buys (including an arbitrary quote asset), stored both, and retrieved two market observations, one priced and one unpriced. Those public transactions are regression fixtures. Sustained end-to-end collection on your account still requires your configured free RPC key; no keys are bundled.

## Provider/interface references

- Pump official IDL: https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json
- PumpSwap official IDL: https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json
- LaunchLab official IDL: https://github.com/raydium-io/raydium-idl/blob/master/raydium_launchpad/raydium_launchpad.json
- Raydium addresses: https://docs.raydium.io/reference/program-addresses
- Helius pricing and billing: https://www.helius.dev/pricing and https://www.helius.dev/docs/billing/credits
- DEX Screener API: https://docs.dexscreener.com/api/reference
- IP certificates: https://letsencrypt.org/2026/03/11/shorter-certs-certbot

Instruction account layouts in `instructions.json` are selected from the official Pump and LaunchLab IDLs retrieved on 2026-09-12. Future unknown instructions fail closed until their definitions are reviewed.

## One-command start/update

After cloning the repository once on your VPS:

```sh
git clone --branch codex/wallet-observatory https://github.com/rippin/wallet-discovery.git
cd wallet-discovery
bash deploy/update.sh
```

Run `bash deploy/update.sh` again whenever you want the latest committed version. The script fetches and fast-forwards the branch, reloads its updated script, builds the image, validates configuration without printing secrets, backs up a running instance's database into `backups/`, starts Docker, and verifies the authenticated dashboard responds. It does not delete volumes or automatically roll back a failed deployment.

If `.env.observatory` is missing and `.env` exists, setup copies `.env` to `.env.observatory` with restrictive permissions and preserves the original. Future runs use `.env.observatory`; when both exist, `.env.observatory` takes precedence. If neither exists, first interactive use prompts privately for an HTTPS RPC URL or Helius key and a 7+ character dashboard password (letters/numbers/dash/underscore; Enter to generate one), creates the file with restrictive permissions, and enables live collection. Existing configuration is preserved; an existing file with `OBS_LIVE=0` requires you to change that setting explicitly. Later runs can be noninteractive. When the configured password is missing or empty, the update script generates a random 32-character password and saves it as `OBS_PASSWORD` in `.env.observatory`. Existing nonempty passwords are preserved and must have at least 7 characters. The username is `research`.

Requires Bash, Git, Docker with the Compose v2 plugin (supporting `up --wait`), and permission to use Docker. It stops for local code changes, unexpected remotes/branches, divergent history, failed builds, or failed backups. It never runs `git reset --hard`, stashes your changes, installs Docker, or alters HTTPS/firewall configuration. Keep off-VPS copies of the generated backups; local backups share the server's failure risk. If the previous container is stopped, no automatic backup is taken: use the documented backup/restore procedure before updates requiring data migration.
