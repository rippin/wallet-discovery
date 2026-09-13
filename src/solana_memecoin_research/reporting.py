from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ResearchReport


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def render_markdown(report: ResearchReport) -> str:
    data = report.to_dict()
    market = data["market"]
    technical = data["technical"]
    ownership = data["ownership"]
    lines = [
        "# Solana Memecoin Research Report",
        "",
        f"**Verdict:** {data['verdict']}  ",
        f"**Confidence:** {data['confidence']} ({data['evidence_coverage_pct']:.1f}% evidence coverage)  ",
        f"**Score:** {data['score']:.2f}/100  ",
        f"**Timestamp:** {data['timestamp']}  ",
        f"**Mint:** `{data['input']['mint']}`  ",
        f"**Intended position:** {_money(data['input']['position_usd'])}  ",
        f"**Holding period:** {data['input']['holding_period']}",
        "",
        "> This is a time-sensitive research classification, not financial advice or a return guarantee.",
        "",
        "## Decision summary",
        "",
    ]
    if data["hard_gates"]:
        lines.extend(
            f"- **{finding['code']}** — {finding['message']}"
            for finding in data["hard_gates"]
        )
    else:
        lines.append("- No configured hard safety gate failed at the report timestamp.")
    lines.extend(["", "### Weighted components", ""])
    lines.extend(
        f"- {name.replace('_', ' ').title()}: {score:.2f}/100"
        for name, score in data["components"].items()
    )

    lines.extend(
        [
            "",
            "## Technical and liquidity",
            "",
            f"- Token program: {technical.get('program', 'unavailable')}",
            f"- Supply: {technical.get('supply_ui', 'unavailable')}",
            f"- Mint authority: {('unavailable' if not technical.get('available') else technical.get('mint_authority') or 'revoked / absent')}",
            f"- Freeze authority: {('unavailable' if not technical.get('available') else technical.get('freeze_authority') or 'revoked / absent')}",
            f"- Extensions: {technical.get('extensions') or 'none reported'}",
            f"- DEX / pair: {market.get('dex_id', 'unavailable')} / `{market.get('pair_address', 'unavailable')}`",
            f"- Liquidity: {_money(market.get('liquidity_usd'))}",
            f"- 24h volume: {_money((market.get('volume') or {}).get('h24'))}",
            f"- Market cap / FDV: {_money(market.get('market_cap'))} / {_money(market.get('fdv'))}",
            f"- Position liquidity multiple: {float(market.get('position_liquidity_multiple') or 0):.2f}×",
        ]
    )
    cohort = market.get("cohort_normalization") or {}
    lines.append(
        f"- Cohort normalization: "
        f"{'applied' if cohort.get('applied') else 'not applied'} "
        f"({cohort.get('matched_reports', 0)} matching {cohort.get('dex_id') or 'unknown'} / "
        f"{cohort.get('age_bucket') or 'unknown'} reports)"
    )
    quote = market.get("sell_quote") or {}
    if quote.get("available"):
        lines.extend(
            [
                f"- Jupiter sell route: available ({quote.get('route_count', 0)} route legs)",
                f"- Estimated sell price impact: {_pct(quote.get('price_impact_pct'))}",
            ]
        )
    else:
        lines.append("- Jupiter sell route: not verified")

    lines.extend(["", "## Ownership and coordination", ""])
    lines.extend(
        [
            f"- Top-10 resolved account share: {_pct(ownership.get('top_10_share_pct'))}",
            f"- Largest reconstructed cluster share: {_pct(ownership.get('largest_cluster_share_pct'))}",
            f"- Creator candidate: `{(ownership.get('early_activity') or {}).get('creator_candidate') or 'unresolved'}`",
            f"- Early buyers reconstructed: {len((ownership.get('early_activity') or {}).get('early_buyers') or [])}",
        ]
    )
    holders = ownership.get("holders") or []
    if holders:
        lines.extend(
            [
                "",
                "| Rank | Wallet owner | Share | Token account |",
                "|---:|---|---:|---|",
            ]
        )
        for index, holder in enumerate(holders[:10], 1):
            lines.append(
                f"| {index} | `{holder.get('owner') or 'unresolved'}` | "
                f"{_pct(holder.get('share_pct'))} | `{holder['token_account']}` |"
            )
    clusters = ownership.get("clusters") or []
    linked = [cluster for cluster in clusters if cluster["confidence"] != "unclustered"]
    if linked:
        lines.extend(["", "### Observed cluster evidence", ""])
        for cluster in linked:
            lines.append(
                f"- {cluster['cluster_id']} ({_pct(cluster['share_pct'])}, "
                f"{cluster['confidence']}): {'; '.join(cluster['reasons']) or 'timing correlation only'}"
            )

    lines.extend(["", "## Repeat-winner wallet research", ""])
    traders = data["wallet_research"].get("top_traders") or []
    if traders:
        lines.extend(
            [
                "| Wallet | Classification | Realized P&L | Trades | Cost-stress edge | Tags |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for trader in traders[:10]:
            stress = trader.get("copyability_stress") or {}
            lines.append(
                f"| `{trader.get('wallet') or 'unresolved'}` | "
                f"{trader.get('classification', 'unproven')} | "
                f"{_money(trader.get('realized_pnl_usd'))} | "
                f"{trader.get('trade_count', 0)} | "
                f"{(_pct(stress.get('net_edge_pct')) if stress.get('available') else 'unavailable')} | "
                f"{', '.join(map(str, trader.get('tags') or [])) or 'none'} |"
            )
        lines.append(
            "\nWallet labels and cost stress are probabilistic evidence, not proof of "
            "real-world identity, inside information, or copyable future returns."
        )
    else:
        lines.append("- Cross-token realized P&L was not independently available.")

    lines.extend(["", "## Social and narrative", ""])
    social = data["social"]
    if social.get("available"):
        lines.extend(
            [
                f"- Window: {social.get('window')}",
                f"- Posts / unique authors: {social.get('post_count', 0)} / {social.get('unique_authors', 0)}",
                f"- Top-author share: {_pct(social.get('top_author_share_pct'))}",
                f"- Repeated-text share: {_pct(social.get('duplicate_share_pct'))}",
                f"- Total public engagement: {social.get('engagement_total', 0):,}",
                f"- Median observed account age: {social.get('median_account_age_days') or 'unavailable'} days",
            ]
        )
    else:
        lines.append("- Automated X measurement unavailable.")
    for url in social.get("supplied_urls") or []:
        lines.append(f"- Supplied social evidence: {url}")

    lines.extend(["", "## Scenarios", ""])
    lines.extend(f"- **{name.title()}:** {text}" for name, text in data["scenarios"].items())
    lines.extend(["", "## Upgrade conditions", ""])
    lines.extend(f"- {item}" for item in data["upgrade_conditions"])
    lines.extend(["", "## Invalidation conditions", ""])
    lines.extend(f"- {item}" for item in data["invalidation_conditions"])
    lines.extend(["", "## Data limitations", ""])
    lines.extend(f"- {item}" for item in data["limitations"])
    if not data["limitations"]:
        lines.append("- No provider limitation was recorded.")
    lines.extend(["", "## Sources", ""])
    lines.extend(f"- [{source['name']}]({source['url']})" for source in data["sources"])
    lines.append("")
    return "\n".join(lines)


def write_report(
    report: ResearchReport, markdown_path: Path | None, json_path: Path | None
) -> None:
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
