from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureDex:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def token_market(self, mint: str, dex_url: str | None = None) -> dict[str, Any]:
        return self.data["market"]


class FixtureSolana:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def mint_info(self, mint: str) -> dict[str, Any]:
        return self.data["technical"]

    def largest_holders(self, mint: str, supply_raw: int) -> list[Any]:
        from .models import Holder

        return [Holder(**holder) for holder in self.data.get("holders", [])]

    def early_activity(self, mint: str, signature_limit: int) -> dict[str, Any]:
        return self.data.get(
            "early_activity",
            {"creator_candidate": None, "early_buyers": [], "history_complete": True},
        )

    def funding_evidence(self, wallets: Any) -> dict[str, Any]:
        return self.data.get("funding_evidence", {})


class FixtureJupiter:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def sell_quote(self, mint: str, amount_raw: int) -> dict[str, Any]:
        return self.data["quote"]


class FixtureBirdeye:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def top_traders(self, mint: str) -> dict[str, Any]:
        result = self.data.get(
            "wallet_research", {"available": True, "top_traders": []}
        ).copy()
        if "traders" in result and "top_traders" not in result:
            result["top_traders"] = result.pop("traders")
        return result

    def wallet_pnl_summary(self, wallet: str) -> dict[str, Any]:
        profiles = self.data.get("wallet_profiles", {})
        return profiles.get(
            wallet,
            {
                "wallet": wallet,
                "available": True,
                "total_trades": 20,
                "wins": 12,
                "losses": 8,
                "win_rate_pct": 60,
                "realized_pnl_usd": 5000,
                "unrealized_pnl_usd": 500,
                "total_invested_usd": 10000,
                "current_value_usd": 1000,
                "source_scope": "fixture all-time wallet P&L summary",
            },
        )


class FixtureX:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def recent_signal(self, mint: str, symbol: str | None) -> dict[str, Any]:
        return self.data.get("social", {"available": True, "post_count": 0})


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
