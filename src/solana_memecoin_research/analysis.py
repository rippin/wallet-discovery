from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .http import HttpError
from .models import Finding, ResearchInput, ResearchReport
from .providers import (
    BirdeyeClient,
    DexScreenerClient,
    JupiterClient,
    SolanaRpcClient,
    XClient,
    build_clusters,
)

SOURCES = [
    {
        "name": "MELT high-risk Solana launch study",
        "url": "https://arxiv.org/abs/2602.13480",
    },
    {
        "name": "Solana SPL Token basics",
        "url": "https://solana.com/docs/tokens/basics",
    },
    {
        "name": "Solana Token-2022 transfer fees",
        "url": "https://solana.com/docs/tokens/extensions/transfer-fees",
    },
    {
        "name": "DEX Screener API",
        "url": "https://docs.dexscreener.com/api/reference",
    },
    {
        "name": "Jupiter quote API",
        "url": "https://developers.jup.ag/docs/swap/v1/get-quote",
    },
    {
        "name": "Birdeye top traders API",
        "url": "https://docs.birdeye.so/reference/get-defi-v2-tokens-top_traders",
    },
    {
        "name": "X recent search API",
        "url": "https://docs.x.com/x-api/posts/search-recent-posts",
    },
]


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _extension_types(extensions: list[Any]) -> set[str]:
    result = set()
    for extension in extensions:
        if isinstance(extension, dict):
            result.add(
                str(extension.get("extension") or extension.get("type") or "").lower()
            )
        else:
            result.add(str(extension).lower())
    return result


def _technical_gates(technical: dict[str, Any]) -> tuple[list[Finding], list[Finding]]:
    hard: list[Finding] = []
    findings: list[Finding] = []
    if not technical.get("available"):
        if technical.get("status") == "not_found":
            hard.append(
                Finding(
                    "mint_not_found",
                    "critical",
                    "No on-chain account exists for the supplied mint address.",
                )
            )
        return hard, findings
    if technical.get("mint_authority"):
        hard.append(
            Finding(
                "mint_authority_active",
                "critical",
                "Mint authority remains active and can increase supply.",
                {"authority": technical["mint_authority"]},
            )
        )
    if technical.get("freeze_authority"):
        hard.append(
            Finding(
                "freeze_authority_active",
                "critical",
                "Freeze authority remains active and can freeze token accounts.",
                {"authority": technical["freeze_authority"]},
            )
        )
    extension_types = _extension_types(technical.get("extensions") or [])
    dangerous = {
        value
        for value in extension_types
        if any(
            needle in value
            for needle in ("transferfee", "permanentdelegate", "transferhook", "pausable")
        )
    }
    if dangerous:
        hard.append(
            Finding(
                "dangerous_token_extensions",
                "critical",
                "Token-2022 controls require manual review before the token is tradable.",
                {"extensions": sorted(dangerous)},
            )
        )
    if technical.get("program") == "unknown":
        hard.append(
            Finding(
                "unknown_token_program",
                "critical",
                "Mint is not owned by a recognized SPL token program.",
                {"program_id": technical.get("program_id")},
            )
        )
    if not technical.get("is_initialized"):
        hard.append(Finding("mint_not_initialized", "critical", "Mint is not initialized."))
    return hard, findings


def _ownership_score(
    holders: list[dict[str, Any]], clusters: list[dict[str, Any]]
) -> float:
    top10 = sum(holder["share_pct"] for holder in holders[:10])
    top1 = holders[0]["share_pct"] if holders else 100.0
    largest_cluster = max((cluster["share_pct"] for cluster in clusters), default=top1)
    penalty = top1 * 1.0 + max(0, top10 - 25) * 1.25 + max(0, largest_cluster - 10)
    return _clamp(100 - penalty)


def _liquidity_score(
    market: dict[str, Any], quote: dict[str, Any], position_usd: float
) -> float:
    liquidity = float(market.get("liquidity_usd") or 0)
    multiple = liquidity / position_usd if position_usd > 0 else 0
    multiple_score = _clamp(math.log10(max(multiple, 1)) * 35)
    volume = float((market.get("volume") or {}).get("h24") or 0)
    activity_score = _clamp((volume / liquidity * 50) if liquidity else 0, 0, 25)
    quote_score = 0.0
    if quote.get("available"):
        impact = float(quote.get("price_impact_pct") or 0)
        quote_score = _clamp(25 - impact * 5, 0, 25)
    age_score = 0.0
    created_ms = int(market.get("pair_created_at_ms") or 0)
    if created_ms:
        age_hours = max(
            0,
            (
                datetime.now(timezone.utc).timestamp() - created_ms / 1000
            )
            / 3600,
        )
        age_score = _clamp(math.log10(age_hours + 1) * 10, 0, 15)
    return _clamp(multiple_score + activity_score + quote_score + age_score)


def _wallet_score(wallet_research: dict[str, Any]) -> float:
    traders = wallet_research.get("top_traders") or []
    if not traders:
        return 0.0
    profiles = wallet_research.get("wallet_profiles") or []
    profitable = [trader for trader in traders if trader.get("realized_pnl_usd", 0) > 0]
    tagged_risky = [
        trader
        for trader in traders
        if any(
            str(tag).lower() in {"dev", "bundler", "sniper", "insider"}
            for tag in trader.get("tags") or []
        )
    ]
    trade_depth = sum(1 for trader in traders if trader.get("trade_count", 0) >= 3)
    durable_profiles = [
        profile
        for profile in profiles
        if profile.get("realized_pnl_usd", 0) > 0
        and profile.get("total_trades", 0) >= 10
        and profile.get("win_rate_pct", 0) >= 50
    ]
    durability_bonus = (
        len(durable_profiles) / len(profiles) * 15 if profiles else 0
    )
    return _clamp(
        len(profitable) / len(traders) * 55
        + trade_depth / len(traders) * 35
        - len(tagged_risky) / len(traders) * 40
        + durability_bonus
    )


def _label_wallets(
    wallet_research: dict[str, Any], quote: dict[str, Any]
) -> None:
    profiles = {
        profile.get("wallet"): profile
        for profile in wallet_research.get("wallet_profiles") or []
    }
    current_impact = float(quote.get("price_impact_pct") or 0)
    for trader in wallet_research.get("top_traders") or []:
        wallet = trader.get("wallet")
        tags = {str(tag).lower() for tag in trader.get("tags") or []}
        profile = profiles.get(wallet) or {}
        if tags & {"dev", "bundler", "sniper", "insider"}:
            label = "suspected coordinated"
        elif (
            trader.get("first_trade_time")
            and trader.get("realized_pnl_usd", 0) > 0
            and trader.get("trade_count", 0) >= 5
            and profile.get("realized_pnl_usd", 0) > 0
            and profile.get("total_trades", 0) >= 10
            and profile.get("win_rate_pct", 0) >= 50
        ):
            label = "repeat early profitable"
        else:
            label = "unproven"
        observed_roi = trader.get("observed_roi_pct")
        # This is deliberately conservative and scenario-based. It is not a
        # historical execution reconstruction.
        cost_buffer = 1.0 + current_impact * 2 + 2.0
        trader["classification"] = label
        trader["copyability_stress"] = {
            "available": observed_roi is not None,
            "observed_roi_pct": observed_roi,
            "round_trip_cost_buffer_pct": round(cost_buffer, 4),
            "net_edge_pct": (
                round(float(observed_roi) - cost_buffer, 4)
                if observed_roi is not None
                else None
            ),
            "actionable": bool(
                label == "repeat early profitable"
                and observed_roi is not None
                and float(observed_roi) > cost_buffer
            ),
            "assumptions": (
                "current quote impact in both directions + 1% execution/fee buffer "
                "+ 2% discovery-delay stress; not a historical fill reconstruction"
            ),
        }


def _social_score(social: dict[str, Any]) -> float:
    if not social.get("available"):
        return 0.0
    posts = int(social.get("post_count") or 0)
    authors = int(social.get("unique_authors") or 0)
    if posts == 0:
        return 15.0
    author_score = _clamp(authors / max(posts, 1) * 60, 0, 60)
    concentration_penalty = _clamp(
        float(social.get("top_author_share_pct") or 0) * 0.4, 0, 20
    )
    duplicate_penalty = _clamp(
        float(social.get("duplicate_share_pct") or 0) * 0.4, 0, 20
    )
    breadth = _clamp(math.log10(authors + 1) * 25, 0, 30)
    return _clamp(author_score + breadth + 10 - concentration_penalty - duplicate_penalty)


def _valuation_score(market: dict[str, Any]) -> float:
    liquidity = float(market.get("liquidity_usd") or 0)
    fdv = float(market.get("fdv") or market.get("market_cap") or 0)
    ratio = fdv / liquidity if liquidity else float("inf")
    ratio_score = _clamp(70 - max(0, ratio - 5) * 2.5)
    change = float((market.get("price_change") or {}).get("h24") or 0)
    chase_penalty = max(0, change - 100) * 0.15
    crash_penalty = max(0, -change - 40) * 0.3
    return _clamp(ratio_score + 20 - chase_penalty - crash_penalty)


def _pair_age_bucket(created_ms: int, timestamp: str | None = None) -> str:
    if not created_ms:
        return "unknown"
    try:
        reference = (
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp
            else datetime.now(timezone.utc)
        )
    except ValueError:
        reference = datetime.now(timezone.utc)
    age_hours = max(0.0, reference.timestamp() - created_ms / 1000) / 3600
    if age_hours < 1:
        return "<1h"
    if age_hours < 24:
        return "1-24h"
    if age_hours < 24 * 7:
        return "1-7d"
    if age_hours < 24 * 30:
        return "7-30d"
    return "30d+"


def _normalize_components(
    raw: dict[str, float],
    market: dict[str, Any],
    cohort_reports: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any]]:
    dex_id = market.get("dex_id")
    age_bucket = _pair_age_bucket(int(market.get("pair_created_at_ms") or 0))
    comparable = []
    for snapshot in cohort_reports:
        snapshot_market = snapshot.get("market") or {}
        snapshot_bucket = _pair_age_bucket(
            int(snapshot_market.get("pair_created_at_ms") or 0),
            snapshot.get("timestamp"),
        )
        if snapshot_market.get("dex_id") == dex_id and snapshot_bucket == age_bucket:
            comparable.append(snapshot)
    if len(comparable) < 10:
        return raw, {
            "applied": False,
            "matched_reports": len(comparable),
            "minimum_reports": 10,
            "dex_id": dex_id,
            "age_bucket": age_bucket,
            "method": "raw component scores",
        }
    normalized = {}
    for name, value in raw.items():
        samples = [
            float((snapshot.get("components") or {}).get(name))
            for snapshot in comparable
            if (snapshot.get("components") or {}).get(name) is not None
        ]
        if not samples:
            normalized[name] = value
            continue
        lower = sum(sample < value for sample in samples)
        equal = sum(sample == value for sample in samples)
        normalized[name] = (lower + 0.5 * equal) / len(samples) * 100
    return normalized, {
        "applied": True,
        "matched_reports": len(comparable),
        "minimum_reports": 10,
        "dex_id": dex_id,
        "age_bucket": age_bucket,
        "method": "within-DEX and pair-age percentile rank",
        "raw_components": {name: round(value, 2) for name, value in raw.items()},
    }


class Analyzer:
    def __init__(
        self,
        *,
        dex: DexScreenerClient,
        solana: SolanaRpcClient,
        jupiter: JupiterClient,
        birdeye: BirdeyeClient | None = None,
        x_client: XClient | None = None,
        cohort_reports: list[dict[str, Any]] | None = None,
    ) -> None:
        self.dex = dex
        self.solana = solana
        self.jupiter = jupiter
        self.birdeye = birdeye
        self.x = x_client
        self.cohort_reports = cohort_reports or []

    def analyze(self, research_input: ResearchInput) -> ResearchReport:
        findings: list[Finding] = []
        limitations: list[str] = []
        market: dict[str, Any] = {"available": False, "status": "not_checked"}
        technical: dict[str, Any] = {"available": False, "status": "not_checked"}

        try:
            market = self.dex.token_market(research_input.mint, research_input.dex_url)
        except HttpError as exc:
            market = {"available": False, "status": "provider_error"}
            limitations.append(f"DEX Screener unavailable: {exc}")
        try:
            technical = self.solana.mint_info(research_input.mint)
        except HttpError as exc:
            technical = {"available": False, "status": "provider_error"}
            limitations.append(f"Solana mint lookup unavailable: {exc}")

        hard_gates, technical_findings = _technical_gates(technical)
        findings.extend(technical_findings)

        if not market.get("available") and market.get("status") == "no_pair":
            hard_gates.append(
                Finding("no_active_pair", "critical", "No active Solana DEX pair was found.")
            )

        holders = []
        if technical.get("available"):
            try:
                holders = self.solana.largest_holders(
                    research_input.mint, int(technical.get("supply_raw") or 0)
                )
            except HttpError as exc:
                limitations.append(f"Holder lookup unavailable: {exc}")

        early = {
            "creator_candidate": None,
            "early_buyers": [],
            "history_complete": False,
        }
        try:
            early = self.solana.early_activity(
                research_input.mint, research_input.history_signatures
            )
            if not early.get("history_complete"):
                limitations.append(
                    "Early-activity reconstruction hit the configured signature bound; "
                    "creator and first-buyer labels are candidates, not complete history."
                )
        except HttpError as exc:
            limitations.append(f"Early-activity reconstruction unavailable: {exc}")

        wallet_candidates = {
            holder.owner for holder in holders[:10] if holder.owner
        } | set(research_input.suspected_wallets)
        funding = None
        if research_input.wallet_scan and wallet_candidates:
            try:
                funding = self.solana.funding_evidence(wallet_candidates)
            except HttpError as exc:
                limitations.append(f"Wallet funding scan unavailable: {exc}")
        else:
            limitations.append(
                "Direct/shared funding analysis was not requested; use --wallet-scan for "
                "a bounded, best-effort scan."
            )

        clusters = build_clusters(holders, early.get("early_buyers") or [], funding)
        holder_rows = [asdict(holder) for holder in holders]
        cluster_rows = [asdict(cluster) for cluster in clusters]
        top10_share = sum(holder.share_pct for holder in holders[:10])
        cluster_top = max((cluster.share_pct for cluster in clusters), default=0.0)
        ownership = {
            "holders": holder_rows,
            "clusters": cluster_rows,
            "top_10_share_pct": top10_share,
            "largest_cluster_share_pct": cluster_top,
            "early_activity": early,
            "funding_evidence": funding or {},
        }
        if holders and top10_share >= 50:
            findings.append(
                Finding(
                    "high_holder_concentration",
                    "warning",
                    "The ten largest resolved token accounts control at least half of supply.",
                    {"top_10_share_pct": round(top10_share, 4)},
                )
            )

        quote: dict[str, Any] = {"available": False}
        if market.get("available") and technical.get("available"):
            price = float(market.get("price_usd") or 0)
            decimals = int(technical.get("decimals") or 0)
            if price > 0:
                amount_tokens = research_input.position_usd / price
                amount_raw = max(1, int(amount_tokens * (10**decimals)))
                try:
                    quote = self.jupiter.sell_quote(research_input.mint, amount_raw)
                except HttpError as exc:
                    if exc.status in {400, 404, 422}:
                        hard_gates.append(
                            Finding(
                                "no_sell_route",
                                "critical",
                                "Jupiter did not return a sell route for the intended position.",
                                {"position_usd": research_input.position_usd},
                            )
                        )
                    else:
                        limitations.append(f"Jupiter quote unavailable: {exc}")
            else:
                limitations.append("Position-sized sell quote skipped because USD price is absent.")
        market["sell_quote"] = quote

        liquidity = float(market.get("liquidity_usd") or 0)
        liquidity_multiple = (
            liquidity / research_input.position_usd
            if research_input.position_usd > 0
            else 0
        )
        market["position_liquidity_multiple"] = liquidity_multiple
        if market.get("available") and liquidity_multiple < 50:
            hard_gates.append(
                Finding(
                    "inadequate_position_liquidity",
                    "critical",
                    "Selected pool liquidity is less than 50× the intended position.",
                    {
                        "liquidity_usd": liquidity,
                        "position_usd": research_input.position_usd,
                        "multiple": round(liquidity_multiple, 2),
                    },
                )
            )
        if quote.get("available") and float(quote.get("price_impact_pct") or 0) > 5:
            hard_gates.append(
                Finding(
                    "extreme_price_impact",
                    "critical",
                    "The intended sell quote exceeds 5% estimated price impact.",
                    {"price_impact_pct": quote["price_impact_pct"]},
                )
            )

        wallet_research: dict[str, Any] = {
            "available": False,
            "top_traders": [],
            "labels_are_probabilistic": True,
        }
        if self.birdeye:
            try:
                wallet_research = self.birdeye.top_traders(research_input.mint)
                wallet_research["labels_are_probabilistic"] = True
                candidates = []
                for wallet in [
                    *research_input.suspected_wallets,
                    *[
                        trader.get("wallet")
                        for trader in wallet_research.get("top_traders") or []
                    ],
                ]:
                    if wallet and wallet not in candidates:
                        candidates.append(wallet)
                profiles = []
                profile_failures = 0
                for wallet in candidates[:5]:
                    try:
                        profiles.append(self.birdeye.wallet_pnl_summary(wallet))
                    except HttpError:
                        profile_failures += 1
                wallet_research["wallet_profiles"] = profiles
                wallet_research["profile_wallet_limit"] = 5
                if profile_failures:
                    limitations.append(
                        f"Birdeye wallet-wide P&L failed for {profile_failures} sampled wallet(s)."
                    )
            except HttpError as exc:
                limitations.append(f"Birdeye trader history unavailable: {exc}")
        else:
            limitations.append(
                "BIRDEYE_API_KEY is absent; repeat-winner P&L and cross-token history "
                "could not be independently verified."
            )
        _label_wallets(wallet_research, quote)

        symbol = ((market.get("base_token") or {}).get("symbol")) or None
        social: dict[str, Any] = {
            "available": False,
            "supplied_urls": research_input.x_urls,
        }
        if self.x:
            try:
                social.update(self.x.recent_signal(research_input.mint, symbol))
            except HttpError as exc:
                limitations.append(f"X recent search unavailable: {exc}")
        else:
            limitations.append(
                "X_BEARER_TOKEN is absent; supplied URLs are recorded but recent-post "
                "breadth and repetition are not measured."
            )

        raw_component_values = {
            "ownership": _ownership_score(holder_rows, cluster_rows) if holders else 0.0,
            "liquidity": _liquidity_score(
                market, quote, research_input.position_usd
            )
            if market.get("available")
            else 0.0,
            "wallet_quality": _wallet_score(wallet_research),
            "social": _social_score(social),
            "valuation_timing": _valuation_score(market)
            if market.get("available")
            else 0.0,
        }
        component_values, cohort_status = _normalize_components(
            raw_component_values, market, self.cohort_reports
        )
        market["cohort_normalization"] = cohort_status
        if not cohort_status["applied"]:
            limitations.append(
                "Comparable-cohort normalization was not applied: "
                f"{cohort_status['matched_reports']} matching historical report(s), "
                f"{cohort_status['minimum_reports']} required. Raw component scores are shown."
            )
        availability = {
            "ownership": bool(holders),
            "liquidity": bool(market.get("available")),
            "wallet_quality": bool(wallet_research.get("top_traders")),
            "social": bool(social.get("available")),
            "valuation_timing": bool(market.get("available")),
        }
        weights = {
            "ownership": 0.30,
            "liquidity": 0.25,
            "wallet_quality": 0.20,
            "social": 0.15,
            "valuation_timing": 0.10,
        }
        available_weight = sum(
            weights[name] for name, present in availability.items() if present
        )
        score = (
            sum(
                component_values[name] * weights[name]
                for name, present in availability.items()
                if present
            )
            / available_weight
            if available_weight
            else 0.0
        )
        coverage = available_weight * 100
        if hard_gates or (coverage >= 65 and score < 40):
            verdict = "Avoid"
        elif score >= 70 and coverage >= 65:
            verdict = "Consider"
        else:
            verdict = "Watch"
        confidence = "high" if coverage >= 85 else "medium" if coverage >= 65 else "low"

        scenarios = {
            "bull": (
                "Liquidity and unique participation expand while cluster-adjusted "
                "concentration falls and profitable wallets retain positions."
            ),
            "base": (
                "Narrative attention remains volatile; position sizing and executable "
                "sell liquidity determine whether apparent upside is realizable."
            ),
            "failure": (
                "Connected holders distribute into promotion, liquidity contracts, or "
                "token controls/transfer behavior invalidate sellability."
            ),
        }
        upgrade = [
            "Fresh position-sized Jupiter quote remains below 2% price impact.",
            "Cluster-adjusted top-holder concentration declines without hidden funding links.",
            "Independent repeat-winner history survives fees, slippage, and discovery delay.",
            "Unique-author social growth precedes price expansion instead of following it.",
        ]
        invalidation = [
            "Any mint, freeze, transfer-fee, delegate, hook, or pause authority becomes active.",
            "Pool liquidity falls below 50× the intended position or the sell route disappears.",
            "Developer/connected clusters materially distribute into rising promotion.",
            "Social activity becomes concentrated, duplicated, or predominantly newly created accounts.",
        ]
        return ResearchReport(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            input=research_input,
            verdict=verdict,
            confidence=confidence,
            score=round(score, 2),
            evidence_coverage_pct=round(coverage, 1),
            components={key: round(value, 2) for key, value in component_values.items()},
            hard_gates=hard_gates,
            findings=findings,
            technical=technical,
            market=market,
            ownership=ownership,
            wallet_research=wallet_research,
            social=social,
            scenarios=scenarios,
            upgrade_conditions=upgrade,
            invalidation_conditions=invalidation,
            limitations=limitations,
            sources=SOURCES,
        )
