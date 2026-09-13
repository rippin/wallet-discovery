from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]


@dataclass
class Finding:
    code: str
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Holder:
    token_account: str
    owner: str | None
    amount_raw: int
    amount_ui: float
    share_pct: float


@dataclass
class Cluster:
    cluster_id: str
    wallets: list[str]
    share_pct: float
    confidence: str
    reasons: list[str]


@dataclass
class ResearchInput:
    mint: str
    dex_url: str | None = None
    x_urls: list[str] = field(default_factory=list)
    suspected_wallets: list[str] = field(default_factory=list)
    holding_period: str = "unspecified"
    position_usd: float = 500.0
    history_signatures: int = 200
    wallet_scan: bool = False


@dataclass
class ResearchReport:
    timestamp: str
    input: ResearchInput
    verdict: str
    confidence: str
    score: float
    evidence_coverage_pct: float
    components: dict[str, float]
    hard_gates: list[Finding]
    findings: list[Finding]
    technical: dict[str, Any]
    market: dict[str, Any]
    ownership: dict[str, Any]
    wallet_research: dict[str, Any]
    social: dict[str, Any]
    scenarios: dict[str, str]
    upgrade_conditions: list[str]
    invalidation_conditions: list[str]
    limitations: list[str]
    sources: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

