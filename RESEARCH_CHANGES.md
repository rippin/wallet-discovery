# Research dashboard changes

This update makes the dashboard answer three questions: **What is this wallet doing? Could I have followed it after researching? Does the selected group outperform comparable observations?** It does not make a profitability claim or place trades.

## Where to start

1. Open **Overview**. The latest eight research opportunities show the wallet's selection reason, buy amount, observed position action, detection delay, price movement since its estimated entry, liquidity and missing-data flags. Open the chart and inspect the wallet before using the existing paper-entry form.
2. Click a wallet. **Positions and observed P&L** groups its transactions by token. **Forward tests at your research delay** shows the new results separately from the previous following model.
3. On Overview, inspect **Wallets under closer observation** for actual polling time, queue depth and coverage gaps. Then inspect **Does following this shortlist help?** for the comparison with sampled controls.
4. Continue using **Activity feed** for individual buy/sell quantities, quote amounts, USD estimates and transaction links.

## Position histories and cost basis

Each wallet–token position shows total tokens bought/sold, historical USD totals with priced-trade counts, average entry/exit for the priced subset, observed remaining tokens, latest action, matched realized P&L and the percentage of sold quantity with priced matched acquisitions.

- FIFO matches sells to previously observed acquisitions. Sales beyond observed inventory have unknown cost basis, never zero cost.
- Historical USD accounting accepts a saved quote price only when sampled within ten minutes of the transaction. Later conversions remain visible in the trade feed but are excluded from historical position P&L. Instruction-local routed quote amounts are also excluded from cost basis.
- Native SOL amounts and costs remain estimates; separately unallocated fees are not deducted again. This is not tax accounting.
- Token inflows without a recognized purchase create unknown-cost lots. Outflows without a recognized sale remove inventory without creating proceeds and conservatively invalidate remaining cost basis.
- Positive token holdings visible before the earliest cached transaction are treated as unknown-cost inventory. Transaction balances cover participating token accounts, not a complete account balance query.
- Same-second transactions can have uncertain ordering; their cost basis is treated conservatively.
- Existing cached transaction flows are reconciled incrementally, 100 records per research tick. Values can change during reconciliation or as missed trades arrive. No extra RPC fetches are used for this backfill.

**Observed remaining is not a verified current balance.** Missed history, transfers and unsupported trades can change the actual account's holdings. Matched realized P&L applies only to the covered portion; it is not total wallet profit. Average prices can be blank when historical pricing is missing.

## Frozen selection and closer observation

A seven-day run freezes a shortlist of up to **three wallets** by default. Selection prioritizes wallets qualifying under the existing 24-hour cohort rules, then promising wallets, then recently observed candidates to fill remaining slots. Reasons and prior statistics are saved at selection. Exploratory candidates are explicitly labeled as unproven.

Selection is not changed in response to that run's subsequent wins or losses. The next run selects again. This is an observational forward test, not a randomized controlled experiment.

A separate scheduler attempts research work every **60 seconds**. Each tick polls at most one due shortlisted wallet, fetching at most one page of 20 signatures and two transactions. The per-wallet requested interval is at least **120 seconds**; three wallets typically require at least three ticks for a round. Requests consume the existing tracking quota. Discovery continues under its existing budget, and normal wallet scans remain enabled for historical coverage.

The queue and cursors survive restarts. Missing transactions have three attempts. Signature gaps and queue omissions are reported, not silently treated as complete history. Focus queues hold at most 2,000 pending records per wallet. The displayed gap count combines known omitted records and gap incidents; it is not a precise number of all missed transactions.

**Actual detection latency matters more than the configured interval.** Provider limits, high wallet activity and long-running work can delay observations. Pending queue age and last successful poll remain visible. Closer observation does not mean every transaction is captured.

## New prospective results

Only new eligible fresh-cohort buys detected after the run started enter the new experiment. Discovery/backfill observations and older signals are excluded. Each wallet–token contributes only its first signal in that run. The launchpad admission filters still govern wallet discovery; subsequent buys of an already tracked wallet can be smaller than $100.

For each signal, the new model records:

- Entry delays of **1, 5, 15 and 60 minutes after detection**.
- Holding periods of **1, 6 and 24 hours**.
- Fixed **$500** liquidity-modeled entries and exits, using the existing 1% plus size/liquidity impact allowance on each side.
- Entry and exit observations no later than **two minutes after the target time**; actual timestamps are saved. Missing observations are never reconstructed using today's price.
- Explicit missing-entry, missing-exit, unexecutable-entry and unexecutable-exit statuses.
- Best and worst *sampled* returns after entry, number of path samples and maximum gap between those samples.
- Time between consecutive profitable samples only where the interval is at most two minutes. This is sampled evidence, not proof that an exit remained continuously available.
- Price disadvantage relative to the source wallet's usable observed entry estimate, and observed tokens sold between its buy and the hypothetical entry.

Best sampled returns are not booked as profit. Unavailable exits remain unresolved, not zeros or wins. Completed results are immutable. New results are separate from older 5/15/60-minute outcome records and do not rewrite their eligibility or ranks.

Research pricing covers at most 30 active experiment tokens per tick, prioritizing the oldest sample equally across selected and control tokens. Active tokens are sampled through 26 hours after detection. Mature-result calculation handles at most 50 due samples per tick. If the universe grows beyond the free budget, missing coverage remains visible.

Wallet summaries show mean, median, win rate, average losing return, coverage and mean with the largest winner removed. The wallet detail response contains the latest 240 result rows and labels that bound; the path table displays 24. These are descriptive estimates, not confidence-adjusted profitability forecasts.

## Baseline comparison

Controls come from **other tracked wallets in the same sampled universe**, not every Solana buyer. Matching requires:

- Different wallet and token; control tokens occurring in the selected arm are excluded.
- Detection within six hours.
- Market cap and liquidity each within a factor of two.
- Same observed-age bucket: under one hour, one hour to one day, or over one day.

Attributes use a price snapshot at or before detection, no more than ten minutes old. Unknown matching attributes stay unmatched. “Token age” currently means **time since our first observation**, not verified launch age.

Matching is chronological and independent of returns, with each control used at most once. Provisional matches may change as observations arrive; a completed run's sample set stabilizes after enrollment ends. The comparison counts each token once per arm, reports unmatched selected tokens, distinct selected days and priced-pair coverage. A direct SOL link already observed before the run excludes that wallet pair; this does not identify all related accounts or prove common ownership.

The paired difference compares only pairs with usable returns on both sides. Missing results remain in each side's mature coverage denominator. Missingness and different observation delays can bias the comparison. A positive mean difference alone does not prove an edge; inspect coverage, losses, sample size, token concentration and performance without the best winner.

The UI shows the current run. Earlier runs, members, samples and results remain in SQLite. The versioned rules are stored with each run.

## Optional size-specific quote checks

With `JUPITER_API_KEY` configured, shortlisted tokens with a new experiment signal in the last hour can receive an indicative **500 USDC buy followed by a sell quote for the quoted token output**. The service uses Jupiter V2 `/order` without a taker, so no transaction is assembled for an account, signed or executed.

At most two tokens are considered per tick; checks for a token are spaced at least five minutes apart. Each side consumes one request in an independent daily quote budget (default 100); failed attempts count too. Quote failure or an unavailable exit is saved explicitly. Returned token quantities remain integer base units, avoiding token-decimal conversion errors.

Checks display the expected round-trip USDC output, status and timestamp. Buy/sell price-impact fields and router are saved when supplied. These are same-time indicative checks, **not the hypothetical future exit**, and they do not replace the liquidity-model experiment results. They exclude unmodeled network fees, movement and execution slippage; USDC is not silently claimed to be exactly one USD. Quotes older than two minutes are flagged as stale even though the request interval is five minutes.

Without a key, the dashboard says **Size-specific quotes not configured** and makes no Jupiter requests. Your existing RPC credentials are not Jupiter credentials. Nothing in this update purchases API usage.

References: [Jupiter V2 overview](https://developers.jup.ag/docs/swap) and [quote-only requests without a taker](https://developers.jup.ag/docs/swap/order-and-execute).

## Configuration

Continue using only `.env`. Existing RPC URLs, passwords, wallet records and paper positions are preserved.

```dotenv
OBS_FOCUS_WALLETS=3
OBS_FOCUS_SECONDS=120
OBS_RESEARCH_SECONDS=60
# Optional; leave blank to disable route checks.
JUPITER_API_KEY=
OBS_QUOTE_DAILY_CAP=100
```

`OBS_FOCUS_WALLETS` is bounded to 0–10 and applies when selecting the next run; it does not rewrite an existing frozen membership. Research ticks are at least 30 seconds and focus intervals at least 60 seconds. Quote caps are bounded to 0–1,000 requests/day. All RPC calls still obey the existing provider and bucket budgets.

Deploy with the usual `bash deploy/update.sh`. It creates a consistent backup before restart. Schema changes are additive; no observation tables are cleared. Additional snapshots, flow records, queues and results consume disk; this release does not introduce automatic deletion of research evidence.

## Validation and practical limits

Regression tests cover frozen membership, no retrospective enrollment or future-price matching, one sample per wallet/token, missing and unexecutable exits, immutable outcomes, path gaps, FIFO partial sales, unknown transfers, later-price exclusions, bounded focus polling, and capped quote-only requests. Existing dashboard, discovery, provider fallback, password/update and paper tests also run.

New forward results must mature after deployment. Position histories and covered P&L are immediately usable, but unknown history remains unknown. There are no automatic trades, guaranteed returns, verified insider labels, full balance reconciliation, verified launch-age matching or proven statistical significance. Paid RPC could improve coverage; it would not by itself establish profitable wallet selection.

## Overview counters and discovery correction

Overview again shows total observed wallets (separate from the three-wallet research shortlist), wallets added in 24 hours, discovered tokens and recorded trades. A discovery funnel exposes purchase filtering, pending admission, parser ambiguity, skipped work and the timestamp of each launchpad's newest inspected transaction.

Discovery windows now inspect at most two signature pages before fetching a new head. The previous 20-page cap could keep discovery paging backward for minutes, even after freshest-first transaction inspection was introduced. The two-page cap improves head freshness with the same request allowance, at the cost of more explicit pagination gaps. This remains sparse sampling and does not fix every ambiguous transaction or guarantee a higher admitted-wallet count.

Pump.fun V2 routed swaps now support scoped checked-transfer quote flows, matching the existing LaunchLab approach. This recovers swaps whose intermediate quote token has zero net wallet movement. Transfer authority, named user/vault accounts and instruction scope are required; missing scope and invalid authorities remain excluded. These amounts are labeled instruction-local and remain excluded from historical position cost basis. A cached 200-transaction ambiguous sample recovered 104 Pump.fun swaps (42 buys and 62 sells); this is a diagnostic sample, not an overall recovery-rate claim. Historical discovery-window ambiguity counters retain their original inspection counts.

## List pagination

Dashboard tables now default to 10 rows per page; card lists default to 5. Previous/Next controls, loaded-record ranges and a 5/10/25/50 page-size selector appear above and below each list. Lists paginate independently, including wallet positions, trades, forward results, older outcomes and transfers. Selections persist through automatic refreshes and tab changes within the current browser page; changing a wallet filter resets its directory to the first page. Existing API history caps remain in place, so ranges explicitly say “loaded.” Pagination does not issue RPC requests. The previous eight-opportunity and 24/30-outcome display slices have been removed, allowing navigation through all records already returned by the API.
