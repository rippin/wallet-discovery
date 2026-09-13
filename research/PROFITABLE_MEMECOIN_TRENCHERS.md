# How Profitable Memecoin “Trenchers” Actually Trade

**Research date:** August 19, 2026  
**Intended reader:** An active trader with a $1,000–$5,000 dedicated bankroll, four or more monitoring hours per day, some memecoin experience, and a hard 20% strategy drawdown limit.  
**Markets covered:** Solana, Base, Ethereum, Robinhood Chain, BNB Chain, and other EVM markets where comparable data exists.

> This is an educational research framework, not individualized financial advice or a promise of profitability. Memecoins can become untradeable or lose essentially all value. A stop order is not a guarantee of execution.

## Executive conclusion

The evidence does not support a secret indicator that reliably finds winners. It supports a more defensible edge:

1. **Reject manipulated and untradeable tokens faster than other retail traders.**
2. **Identify real acceleration before it becomes a fully crowded move.**
3. **Use successful-wallet activity as confirmation, not as an automatic buy instruction.**
4. **Risk little enough that ordinary losing streaks cannot remove you from the game.**
5. **Realize gains instead of treating temporary account value as profit.**
6. **Measure results after gas, taxes, priority fees, slippage, failed transactions, and alert delay.**

This matters because a cross-chain study of 34,988 memecoins on Ethereum, BNB Chain, Solana, and Base found signs of artificial growth in **82.8% of tokens that returned more than 100%**. The detected mechanisms included wash trading and liquidity-pool-based price inflation; manipulation frequently preceded later profit extraction. That means “it is pumping” is often evidence of danger rather than quality. ([USENIX prepublication](https://www.usenix.org/conference/usenixsecurity26/presentation/mongardini))

The most copyable style for this reader is therefore **confirmed short-horizon momentum**, not first-block sniping: enter after basic safety, ownership, wallet-flow, and participation checks, but before the move becomes obviously parabolic.

## How strong is the evidence?

This report uses four evidence levels:

| Level | Meaning | Examples |
|---|---|---|
| **A — Independent empirical** | Academic or independently published analysis with disclosed data and methodology | USENIX cross-chain manipulation study; MELT; forward paper-trading study |
| **B — Observable market/provider data** | Documented on-chain fields or transparent API methodology | Nansen net flows; Birdeye wallet P&L; DEX Screener pair data |
| **C — Market research** | Useful analysis with meaningful disclosed limitations | CoinGecko/Dune Pump.fun profitability analysis |
| **D — Self-reported** | Interviews, posts, or vendor strategy articles that may contain selection or promotional bias | Trader interviews; X posts; vendor playbooks |

No trading rule below is presented as established fact merely because a trader said it worked. Self-reported advice is used only when it agrees with stronger evidence or becomes a hypothesis to test in the journal.

## 1. What the data says about profitability

### Headline P&L is frequently overstated

CoinGecko’s Pump.fun analysis found that losing was the norm among exited wallets for much of April 2024 through late 2025, although reported realized profitability improved sharply in early 2026. Even the improved data requires caution: it excludes unsold bags, nets unrelated tokens at the wallet level, contains potentially distorted USD prices for illiquid tokens, and does not filter bots or wash trading. ([CoinGecko methodology and results](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback))

Consequences:

- A wallet can look profitable after selling winners while retaining nearly worthless losers.
- A token can show a high unrealized gain at a price where the position cannot actually be sold.
- A wallet may have received tokens rather than bought them.
- Wallet rotation hides the full history of the real operator.
- Public leaderboards select survivors after the outcome is already known.

**Required interpretation:** realized P&L is necessary but insufficient. A credible trader record must include open inventory, per-token accounting, execution costs, funding provenance, and liquidity-adjusted exits.

### Returns are highly dependent on a small number of winners

A 15-day, 190-trade paper deployment reported a 40.5% win rate and positive aggregate returns, but removing only its three best trades—1.6% of the sample—made the strategy unprofitable. Its hour-of-day effect was also not statistically significant. The useful lesson is the fragility, not the headline return: trenching expectancy is commonly positively skewed and can depend on very few outliers. ([Hour-aware adaptive risk study](https://arxiv.org/abs/2606.08232))

This implies:

- A win rate below 50% can still be profitable.
- Cutting every winner at a small fixed percentage can destroy the needed right tail.
- One lucky winner can make an unskilled wallet look excellent.
- Strategy evaluation needs profit concentration and outlier-removal tests.

### Early concentration and coordinated ownership matter

MELT analyzed 41,470 Solana launches and more than 200 million transactions. It found that market activity, holding concentration, and bundle-level features were informative for identifying high-risk launches; adding its model to a simple selection strategy reduced losses by up to 34 percentage points in the authors' experiment. Bundle traces linked accounts likely controlled by the same entity and showed that 36.5% of supply was held by coordinated accounts on average. These are dataset-specific results, not a promised live-trading reduction. ([MELT](https://arxiv.org/abs/2602.13480))

Although its launchpad-specific features do not transfer unchanged to EVM chains, the general principle does: **count economic owners, not addresses**.

### Recurrent early wallets do not automatically cause success

A 2026 study found 1,012 persistent early-buyer cohorts across 166,098 Pump.fun launches. Tokens touched by these cohorts attracted more early flow, but an activity-matched placebo group showed an even larger lift. The authors therefore rejected a strong causal interpretation: highly active wallets may simply select launches that already possess unmeasured attractive qualities. ([coordinated cohort study](https://arxiv.org/abs/2607.02795))

**Practical implication:** “wallet X bought” is weak. The signal becomes useful only after qualifying the wallet, removing related parties, measuring the entry delay, and combining it with independent token evidence.

## 2. The main trader archetypes

| Archetype | Typical horizon | Actual edge | Copyability | Treatment |
|---|---:|---|---|---|
| First-block sniper | Seconds | Infrastructure, ordering, private launch awareness, automation | Very low | Observe for manipulation; do not imitate |
| Minute scalper | 1–20 minutes | Execution speed, order-flow reading, rapid invalidation | Low to medium | Follow only if delayed replay remains profitable |
| Confirmed momentum trencher | 10 minutes–4 hours | Selection, acceleration detection, liquidity awareness | Medium to high | Primary target style |
| Narrative swing trader | Hours–weeks | Cultural/narrative judgment and patience | Medium | Separate strategy and risk bucket |
| Market maker/arbitrageur | Seconds–hours | Spreads, rebates, hedges, privileged infrastructure | Very low | Exclude from “smart trader” copying |
| Developer/insider/coordinated group | Before launch–hours | Allocation or information advantage | None ethically or practically | Risk signal, not smart money |

Public analyses of small samples of profitable Pump.fun traders show median holds ranging from essentially zero to days, confirming that a leaderboard combines incompatible strategies. Those figures are useful for generating hypotheses but remain social-media-derived and should not establish a rule by themselves. ([secondary summary of the 28-wallet analysis](https://www.kucoin.com/news/insight/SOL/6a7f4e7fec098c0007101393))

## 3. What repeatable trenchers appear to do differently

### 3.1 They specialize instead of trading every visible launch

The durable edge is usually narrow: one or two chains, a familiar launchpad/DEX structure, a limited market-cap/age window, and a recognizable setup. Specialization reduces the number of contract patterns, liquidity mechanics, and participant behaviors that must be interpreted in seconds.

- **Evidence:** B, D; consistent with wallet classification methods and trader interviews.
- **Failure mode:** mistaking familiarity for a permanent edge after the market regime changes.
- **Journal field:** `setup_name`, `chain`, `venue`, `age_at_entry_minutes`.

### 3.2 They reject far more tokens than they buy

The cross-chain manipulation evidence and MELT results support an avoidance-first process. Fast traders still need hard gates; speed should shorten analysis, not eliminate it.

- **Evidence:** A.
- **Failure mode:** treating a security scanner’s missing field as “safe.”
- **Journal field:** `rejected`, `rejection_reason`, and the token’s forward 1h/6h/24h result.

Tracking rejected candidates is essential. Otherwise every avoided runner feels like a mistake while the many avoided collapses disappear from memory.

### 3.3 They watch change, not a single snapshot

Useful variables are directional:

- unique buyers over 5, 15, and 60 minutes;
- holder growth and retention;
- liquidity growth versus market-cap growth;
- buy-size distribution rather than raw trade count;
- qualified-wallet net flow;
- developer and connected-cluster net flow;
- unique social authors and repetition rate.

- **Evidence:** A/B; launch-detection studies use activity, ownership, and time-series features.
- **Failure mode:** wash trading creates apparent acceleration.
- **Journal field:** three timestamped snapshots for every entered trade.

### 3.4 They distinguish flow from promotion

DEX Screener explicitly states that purchased boosts multiply a token’s Trending Score. A boost is advertising, not independent demand. ([DEX Screener boosting documentation](https://docs.dexscreener.com/boosting))

Social discovery is useful when it identifies a new cultural catalyst or expanding group of independent authors. It is dangerous when repeated copy, concentrated promoters, or paid visibility are mistaken for adoption.

- **Evidence:** B.
- **Failure mode:** entering after promotion has already produced the price expansion.
- **Journal field:** `catalyst_first_seen_at`, `unique_authors`, `top_promoter_share`, `paid_boosts`.

### 3.5 They use smart-wallet flow as a filter, not an oracle

Nansen documents smart-money net flow, DEX trades, holdings, and historical holdings across numerous chains. Its labels include funds and traders ranked over different windows. Birdeye can rank tokens by smart-wallet net flow or smart-trader count and explicitly recommends using the output as discovery before validating market, holder, and security data. ([Nansen smart-money API](https://docs.nansen.ai/api/smart-money), [Birdeye smart-money token list](https://docs.birdeye.so/reference/get-smart-money-v1-token-list))

- **Evidence:** B.
- **Failure mode:** copying a transfer, a hedge, a market maker, or an already-crowded entry.
- **Journal field:** each triggering wallet, qualification score, transaction type, alert delay, and price movement since its entry.

### 3.6 They exit failed ideas quickly but preserve some upside

Positive-skew evidence argues for asymmetric exits: losses remain bounded while part of a genuine runner is allowed to continue. This does not mean every token deserves a “moonbag”; deteriorating liquidity or connected-holder selling invalidates the trade.

A self-reported trader interview with Wood emphasizes oversizing, round-tripping gains, and emotionally driven re-entry as major failure modes. These claims are not independently audited, but they agree with the statistical fragility and realized-versus-unrealized distinction above. ([Wood interview summary](https://fomo.family/blog/learn/notanicecat69-memecoin-trading-strategy))

- **Evidence:** A for skew/fragility; D for the behavioral account.
- **Failure mode:** mechanically holding a remainder after the thesis has failed.
- **Journal field:** planned invalidation, actual exit reason, maximum favorable excursion (MFE), and maximum adverse excursion (MAE).

### 3.7 They evaluate process rather than screenshots

A serious trader tracks expectancy:

```text
expectancy in R = win_rate × average_win_R − loss_rate × average_loss_R
```

`R` is the amount deliberately risked on one idea. Dollar profit alone cannot compare a $10 test with a $500 bet.

- **Evidence:** inference from P&L limitations and return skew.
- **Failure mode:** increasing size after a lucky outlier.
- **Journal field:** net `R`, fees, slippage, rule adherence, and setup.

## 4. Advantages you should not try to copy

1. **First-block entries:** by the time a public alert arrives, the quoted return may already be gone.
2. **Insider or developer allocation:** a transfer is not evidence of conviction and has a different cost basis from yours.
3. **Bundled or coordinated addresses:** multiple wallets may represent one owner. Bubblemaps links wallets that transferred funds and aggregates clusters, but links are evidence of interaction—not definitive identity. ([Bubblemaps methodology](https://wiki.bubblemaps.io/bubblemaps-v2/how-does-it-work))
4. **Market-making and arbitrage P&L:** the visible wallet may be hedged elsewhere or earning spread rather than directional return.
5. **MEV and private infrastructure:** historical fills may be unobtainable with ordinary RPC and routing.
6. **Rotating wallets:** a newly profitable wallet can be the latest address of an operator whose discarded losses are invisible.
7. **Illiquid marked gains:** a displayed balance is not realizable P&L when its sale moves the pool heavily.

The correct response to these advantages is not to become faster at any cost. It is to exclude uncopyable wallets and focus on the window where information remains useful after your real delay.

## 5. A defensible smart-money methodology

### 5.1 Wallet qualification

Use the following as **initial research thresholds to validate**, not universal truths:

| Test | Initial requirement | Why |
|---|---:|---|
| Closed positions | ≥30 | Reduces one-trade luck |
| Independent tokens | ≥10 | Avoids one-token specialists masquerading as general skill |
| Observation period | ≥60 days, with recent activity | Balances sample depth and relevance |
| Realized P&L | Positive after known costs | Excludes paper-only gains |
| Median closed-trade return | Positive | Resists one huge winner |
| Largest winner contribution | <35% of total profit | Limits outlier dependence |
| Top-three contribution | <60% of total profit | Tests broader repeatability |
| Win rate | Report, do not optimize alone | High win rate can hide rare catastrophic losses |
| Open inventory | Mark at executable sell quote | Avoids fictional liquidity |
| Typical hold time | At least 3× your alert-and-entry delay | Establishes copyability |
| Funding/deployer link | None found | Reduces insider/developer contamination |
| Transfer-derived “entries” | Excluded | Requires actual economic buys |
| Delayed replay expectancy | Positive at 30s, 2m, and 5m scenarios | Tests whether the edge survives discovery |

Birdeye’s documented P&L detail endpoint supplies wallet-wide and token-level results across SVM and EVM networks. Its own copy-signal guide recommends examining the full portfolio rather than one winning token. ([wallet P&L details](https://docs.birdeye.so/reference/post-wallet-v2-pnl-details), [provider implementation guide](https://birdeye.so/data-api/blog/detail/smart-money-copy-trading-birdeye-data))

### 5.2 Consensus signal

For the first 30-day experiment, alert—but do not automatically buy—when:

1. At least **three qualified wallets** make real swaps into the same token within 30 minutes.
2. No pair shares a known funder, deployer relationship, or recurring coordinated cluster.
3. Their combined flow is net positive after sells.
4. The token passes the chain-specific contract and sellability gates.
5. Unique buyers and liquidity are also rising.
6. Developer and connected clusters are not distributing.
7. Price has not moved more than one planned risk unit beyond the first copyable entry.

These numbers are deliberately a starting hypothesis. The journal must compare one-, two-, and three-wallet alerts to determine whether three is actually superior after delay.

### 5.3 Wallet disqualification

Immediately remove or quarantine wallets that exhibit:

- token receipts before their first apparent trade;
- common funding with the deployer or early cluster;
- near-zero median hold times relative to alert latency;
- repeated same-block or same-slot execution with a cohort;
- profit dominated by one token;
- consistent purchases before public liquidity or promotion;
- large unrealized inventory with weak exit liquidity;
- market-making, arbitrage, bridge, router, or exchange behavior;
- sudden strategy change, leverage, or position-size escalation.

## 6. Personal fast-trenching playbook

### 6.1 Chain selection

With a $1,000–$5,000 bankroll, prioritize active low-fee venues such as Solana, Base, BNB Chain, and Robinhood Chain when liquidity and data coverage are adequate. Keep Ethereum mainnet in the opportunity universe, but reject a trade when expected round-trip gas, taxes, and slippage exceed **10% of the trade’s maximum planned loss**. At this bankroll, that rule will often exclude Ethereum mainnet fast trades.

Robinhood Chain mainnet launched only in July 2026. It is an EVM-compatible Arbitrum Layer 2 (chain ID 4663), but its memecoin history, DEX liquidity, indexing, and smart-wallet label coverage are much less mature than Solana, Base, or Ethereum. Treat it as an observation market until position-sized two-way quotes and sufficient tool coverage are demonstrated; EVM compatibility alone does not establish a tradable memecoin venue. ([official Robinhood Chain documentation](https://docs.robinhood.com/chain/connecting/), [mainnet announcement](https://robinhood.com/us/en/newsroom/robinhood-accelerates-global-expansion-robinhood-chain-mainnet-stock-tokens-agentic-trading/))

Always identify assets as `chain_id + contract_address`; ticker symbols are not identities.

### 6.2 Four-hour daily workflow

**First 30 minutes — regime and narrative map**

- Check which chains and launch venues have real volume and liquidity.
- Identify fresh cultural/news catalysts from primary sources.
- Record dominant narratives without buying them yet.
- Review yesterday’s qualified-wallet net flows and exits.

**Next 60 minutes — build the watchlist**

- Collect new/accelerating pairs and smart-money candidates.
- Apply contract, sellability, liquidity, ownership, and developer-history gates.
- Keep no more than 10 active candidates.
- Set alerts for wallet consensus, liquidity, buyer growth, and connected-holder sells.

**Next 120 minutes — execution window**

- Trade only predefined setups.
- Record a snapshot before the order.
- Obtain a position-sized buy and sell quote.
- Do not chase after price exceeds the predefined entry zone.
- Do not average down on a failed trench trade.

**Final 30 minutes — review**

- Reconcile fills and costs.
- Record MFE/MAE and rule adherence.
- Snapshot rejected candidates to measure false negatives.
- Stop monitoring after the scheduled window unless already managing an open position.

### 6.3 Hard token rejection checklist

Reject if any item is confirmed:

- No executable position-sized sell quote.
- Estimated exit impact or taxes make the risk plan invalid.
- Mutable mint/freeze/pause/blacklist/transfer restrictions without a credible reason.
- EVM honeypot behavior, modifiable tax, hidden mint, proxy/admin risk, or trading switch.
- Solana dangerous authority or Token-2022 behavior that has not been understood.
- Liquidity controlled by an unsafe party or rapidly declining.
- Cluster-adjusted ownership is incompatible with the intended exit liquidity.
- Developer or connected wallets are materially selling into promotion.
- Apparent volume is concentrated in repetitive wallets or implausible trade patterns.
- Contract address came only from an unsolicited message or unverified reply.

GoPlus documents free EVM and Solana token-security and transaction-simulation APIs. Its EVM coverage includes honeypots, taxes, modifiable fees, black/whitelists, minting, proxy risk, and liquidity information. Scanner output must still be treated as a fallible input rather than proof of safety. ([GoPlus API overview](https://docs.gopluslabs.io/reference/api-overview), [security fields](https://gopluslabs.io/en/token-security-api))

### 6.4 Entry setup for the experiment

Enter only when all are true:

- hard gates pass;
- the narrative/catalyst can be stated in one sentence;
- unique participation, liquidity, and qualified-wallet flow agree;
- the earliest copyable wallets are holding or adding, not exiting;
- expected execution costs fit the risk budget;
- the exact invalidation and maximum holding time are written before entry;
- the price remains inside the planned zone.

An entry without these fields is an impulse trade and receives no capital during the 30-day program.

### 6.5 Exit framework to test

Use risk units rather than universal percentage targets:

- Exit immediately when the safety or manipulation thesis changes.
- Exit when the prewritten flow/narrative invalidation occurs.
- Apply a time stop when expected acceleration fails to appear within the setup’s tested window.
- At `+1R`, test taking 25–33% off and moving the remainder to a thesis-based stop—not necessarily break-even if normal volatility would trigger it.
- At `+2R`, test realizing another 25–33%.
- Retain the remainder only while liquidity, participation, and holder behavior support continuation.
- No same-day re-entry after a complete exit during the initial experiment. Record missed second moves rather than chasing them.

The ladder is a testable starting policy, not an evidence-proven optimum. Compare it with a full-exit baseline after 30 trades.

## 7. Risk framework for a $1,000–$5,000 bankroll

### Fixed limits

| Rule | $1,000 bankroll | $5,000 bankroll |
|---|---:|---:|
| Risk per idea: 0.5% | $5 | $25 |
| Daily stop: 2% | $20 | $100 |
| Weekly stop: 5% | $50 | $250 |
| Mandatory strategy review: 10% | $100 | $500 |
| Hard stop: 20% | $200 | $1,000 |

Reaching a daily or weekly stop ends new entries for that period. Reaching 10% suspends live trading until the last 20 trades and all rule violations are reviewed. Reaching 20% ends the strategy; do not recapitalize it without a new out-of-sample test.

### Position-size formula

```text
risk dollars = bankroll × 0.005
worst-case loss fraction = planned adverse move + taxes + gas + slippage + gap allowance
maximum position = risk dollars ÷ worst-case loss fraction
```

Examples:

- If the realistic worst case is a complete loss, the maximum position is exactly 0.5% of bankroll: **$5–$25**.
- If the adverse move is 35% and all execution/gap costs add 15%, the total loss fraction is 50%; maximum position becomes **$10–$50**.
- If a minimum practical position or network cost exceeds the calculated size, skip the trade. Do not increase risk to make the trade feel worthwhile.

Assume a larger loss fraction for newer and thinner tokens. A chart stop does not create liquidity.

### Exposure limits

- Maximum four open trench positions.
- Maximum 2% total planned open risk.
- Correlated tokens sharing a narrative, deployer, wallet cohort, or chain event count as one risk group.
- Treasury and long-term assets remain in separate wallets from the trading wallet.

## 8. Thirty-day improvement program

### Days 1–7: observation and rejection calibration

- No live trench trades.
- Record at least 50 candidates, including every rejection.
- Capture 0m, 15m, 1h, 6h, and 24h snapshots.
- Track one-, two-, and three-wallet consensus separately.
- Determine your actual alert-to-fill latency by chain.

### Days 8–14: paper execution

- Paper trade only the fully specified setup.
- Use contemporaneous quotes, not candle prices.
- Record failed transactions, taxes, gas, priority fees, and sell impact.
- Complete at least 10 closed observations.

### Days 15–21: reduced-size live validation

Proceed only if paper expectancy is positive after costs and no safety gate was violated.

- Risk 0.25% per idea.
- Stop after two rule violations, regardless of P&L.
- Do not increase size after a large winner.
- Compare actual versus simulated entry and exit.

### Days 22–30: controlled standard size

Increase to 0.5% risk only when all are true:

- at least 20 combined paper/live closed trades;
- positive net expectancy after costs;
- maximum drawdown below 10%;
- no single winner represents more than 50% of profits;
- at least 90% rule adherence;
- delayed smart-wallet signals remain positive at your real latency.

Otherwise remain at observation or 0.25%. Thirty days passing is not itself a promotion criterion.

### End-of-month evaluation

Require at least 30 closed observations before drawing a preliminary conclusion. Report:

- net P&L and net `R`;
- expectancy and profit factor;
- maximum drawdown;
- median win and median loss;
- MFE/MAE;
- performance by chain, venue, setup, token age, and discovery source;
- results with the largest winner removed;
- results at simulated 30-second, 2-minute, and 5-minute additional delays;
- reject-filter precision and false-negative rate;
- rule-adherent versus rule-breaking performance.

## 9. Free-first tool stack

| Need | Free-first option | Limitation / paid upgrade |
|---|---|---|
| Cross-chain pair discovery | DEX Screener UI/API | Boosts are paid visibility; API is not a complete historical archive |
| Token and pool verification | Chain explorer plus DEX pair page | Each chain needs the correct explorer and contract address |
| EVM/Solana security | GoPlus APIs and simulation | Automated checks can miss new behavior |
| Holder relationships | Bubblemaps where supported; manual explorer tracing | A transfer link does not prove common ownership |
| Historical queries | Dune community queries | Query assumptions and coverage vary |
| Wallet discovery | Public top-trader lists and explorer reconstruction | Nansen/Birdeye provide faster normalized P&L and net-flow data |
| Wallet alerts | Lightweight read-only polling/webhooks | Paid APIs reduce engineering and latency |
| Narrative monitoring | Curated X lists, searches, Telegram/Discord read-only monitoring | Engagement can be bought or coordinated |
| Trading journal | Included CSV template | Automation can be added after fields stabilize |

Nansen’s documented multichain endpoints provide net flow, DEX trades, holdings, and historical holdings for labeled smart money. Birdeye provides multichain smart-money discovery and wallet P&L fields. These are useful paid upgrades, but their labels still require independent copyability and related-party checks. ([Nansen endpoints](https://docs.nansen.ai/about/endpoints-overview), [Birdeye P&L details](https://docs.birdeye.so/reference/post-wallet-v2-pnl-details))

## 10. Highest-value improvements for you

1. **Stop searching for a universal winning coin checklist.** Define one momentum setup and collect 30 comparable outcomes.
2. **Track rejected tokens.** Avoidance is likely the most defensible edge, but it is invisible without counterfactual data.
3. **Replace wallet leaderboards with qualified-wallet cohorts.** Require full-history P&L, independent funding, real swaps, and delayed replay.
4. **Use social media for catalyst timing, not trust.** The contract address, ownership, and money flow remain on-chain facts.
5. **Calculate size from worst-case loss.** Never choose a round dollar position first and invent the risk afterward.
6. **Measure execution latency.** A wallet is not smart money *for you* if its advantage disappears before your fill.
7. **Protect the right tail without worshipping bags.** Scale some profit while the thesis works; liquidate when liquidity or connected-holder behavior invalidates it.
8. **Make rule adherence a promotion criterion.** A profitable month achieved by breaking limits does not validate the method.

## Source appendix

### Independent empirical research

1. Mongardini & Mei, **“A Midsummer Meme’s Dream: Investigating Market Manipulations in the Meme Coin Ecosystem.”** Cross-chain manipulation analysis of 34,988 tokens. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/mongardini) · [preprint](https://arxiv.org/abs/2507.01963)
2. Hu et al., **“MELT: A Behavioral Trace Dataset for High-Risk Memecoin Launch Detection.”** 41,470 launches and more than 200 million transactions. [arXiv](https://arxiv.org/abs/2602.13480)
3. Kamat, **“Hour-Aware Adaptive Risk Management for Autonomous Memecoin Trading.”** Short forward paper deployment; important fragility caveat. [arXiv](https://arxiv.org/abs/2606.08232)
4. Kamat, **“Coordinated Sniper Cohorts on Pump.fun.”** Persistent-wallet cohorts and activity-matched placebo result. [arXiv](https://arxiv.org/abs/2607.02795)

### Market and provider data

5. CoinGecko, **“Pump.fun Traders Are Making a Comeback.”** Realized P&L analysis with explicit methodology limitations. [CoinGecko](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback)
6. Nansen, **Smart Money API and endpoint overview.** Labels, net flow, DEX trades, holdings, and historical holdings. [Smart Money](https://docs.nansen.ai/api/smart-money) · [endpoint overview](https://docs.nansen.ai/about/endpoints-overview)
7. Birdeye, **Smart Money Token List and Wallet P&L Details.** Multichain discovery and wallet/token attribution. [token list](https://docs.birdeye.so/reference/get-smart-money-v1-token-list) · [PnL details](https://docs.birdeye.so/reference/post-wallet-v2-pnl-details)
8. DEX Screener, **API and Boosting documentation.** Pair data and the paid nature of boosts. [API](https://docs.dexscreener.com/api/reference) · [boosting](https://docs.dexscreener.com/boosting)
9. GoPlus, **Security API documentation.** EVM/Solana token checks and transaction simulation. [overview](https://docs.gopluslabs.io/reference/api-overview) · [token-security fields](https://gopluslabs.io/en/token-security-api)
10. Bubblemaps, **“How does it work?”** Transfer-based wallet links and cluster aggregation. [wiki](https://wiki.bubblemaps.io/bubblemaps-v2/how-does-it-work)
11. Robinhood, **Robinhood Chain documentation and mainnet announcement.** EVM-compatible Arbitrum L2, mainnet chain ID 4663, launched July 2026. [documentation](https://docs.robinhood.com/chain/connecting/) · [announcement](https://robinhood.com/us/en/newsroom/robinhood-accelerates-global-expansion-robinhood-chain-mainnet-stock-tokens-agentic-trading/)

### Vendor guidance and self-reported experience — lower confidence

12. Birdeye, **“How to Build a Profitable Smart Money Copy Trading Signal.”** Useful implementation sequence; Birdeye sells the underlying data. [Birdeye](https://birdeye.so/data-api/blog/detail/smart-money-copy-trading-birdeye-data)
13. Fomo, **Wood trader interview summary.** Position sizing, round-tripping, and re-entry lessons; claims are self-reported. [Fomo](https://fomo.family/blog/learn/notanicecat69-memecoin-trading-strategy)
14. Bybit, **Unipcs interview.** Oversizing, overtrading, and planned exits; promotional venue and self-reported results. [Bybit](https://www.bybitglobal.com/en/learn/interviews/unipcs-bonk-guy-interview)
15. KuCoin News, **summary of a social-media analysis of 28 profitable Pump.fun traders.** Useful for hold-time diversity; methodology has not been independently validated. [KuCoin](https://www.kucoin.com/news/insight/SOL/6a7f4e7fec098c0007101393)
