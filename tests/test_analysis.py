import unittest
from pathlib import Path

from solana_memecoin_research.analysis import Analyzer
from solana_memecoin_research.fixtures import (
    FixtureBirdeye,
    FixtureDex,
    FixtureJupiter,
    FixtureSolana,
    FixtureX,
    load_fixture,
)
from solana_memecoin_research.models import ResearchInput
from solana_memecoin_research.http import HttpError

FIXTURES = Path(__file__).parent / "fixtures"


def analyzer_for(name: str) -> Analyzer:
    data = load_fixture(FIXTURES / name)
    return Analyzer(
        dex=FixtureDex(data),
        solana=FixtureSolana(data),
        jupiter=FixtureJupiter(data),
        birdeye=FixtureBirdeye(data) if "wallet_research" in data else None,
        x_client=FixtureX(data) if "social" in data else None,
    )


class AnalysisTests(unittest.TestCase):
    def test_healthy_fixture_is_not_avoid(self) -> None:
        report = analyzer_for("healthy.json").analyze(
            ResearchInput(mint="MINT", position_usd=500)
        )
        self.assertIn(report.verdict, {"Consider", "Watch"})
        self.assertEqual(report.hard_gates, [])
        self.assertEqual(report.evidence_coverage_pct, 100)
        self.assertTrue(report.market["sell_quote"]["available"])
        self.assertEqual(
            report.wallet_research["top_traders"][0]["classification"],
            "repeat early profitable",
        )
        self.assertTrue(
            report.wallet_research["top_traders"][0]["copyability_stress"]["actionable"]
        )

    def test_dangerous_authorities_and_liquidity_force_avoid(self) -> None:
        report = analyzer_for("dangerous.json").analyze(
            ResearchInput(mint="MINT", position_usd=500)
        )
        codes = {finding.code for finding in report.hard_gates}
        self.assertEqual(report.verdict, "Avoid")
        self.assertIn("mint_authority_active", codes)
        self.assertIn("freeze_authority_active", codes)
        self.assertIn("inadequate_position_liquidity", codes)
        self.assertIn("extreme_price_impact", codes)

    def test_missing_enrichment_reduces_confidence(self) -> None:
        report = analyzer_for("dangerous.json").analyze(
            ResearchInput(mint="MINT", position_usd=50)
        )
        self.assertEqual(report.evidence_coverage_pct, 65)
        self.assertTrue(
            any("BIRDEYE_API_KEY" in item for item in report.limitations)
        )

    def test_provider_outage_is_watch_not_avoid(self) -> None:
        class FailingDex:
            def token_market(self, mint: str, dex_url: str | None = None):
                raise HttpError("offline")

        class FailingSolana:
            def mint_info(self, mint: str):
                raise HttpError("offline")

            def early_activity(self, mint: str, signature_limit: int):
                raise HttpError("offline")

        class FailingJupiter:
            pass

        report = Analyzer(
            dex=FailingDex(), solana=FailingSolana(), jupiter=FailingJupiter()
        ).analyze(ResearchInput(mint="MINT"))
        self.assertEqual(report.verdict, "Watch")
        self.assertEqual(report.hard_gates, [])
        self.assertEqual(report.evidence_coverage_pct, 0)

    def test_comparable_cohort_normalizes_components(self) -> None:
        data = load_fixture(FIXTURES / "healthy.json")
        cohorts = [
            {
                "timestamp": f"2026-07-{index + 1:02d}T00:00:00Z",
                "market": {
                    "dex_id": "raydium",
                    "pair_created_at_ms": 1704067200000,
                },
                "components": {
                    "ownership": index * 5,
                    "liquidity": index * 5,
                    "wallet_quality": index * 5,
                    "social": index * 5,
                    "valuation_timing": index * 5,
                },
            }
            for index in range(10)
        ]
        report = Analyzer(
            dex=FixtureDex(data),
            solana=FixtureSolana(data),
            jupiter=FixtureJupiter(data),
            birdeye=FixtureBirdeye(data),
            x_client=FixtureX(data),
            cohort_reports=cohorts,
        ).analyze(ResearchInput(mint="MINT"))
        self.assertTrue(report.market["cohort_normalization"]["applied"])
        self.assertEqual(report.market["cohort_normalization"]["matched_reports"], 10)


if __name__ == "__main__":
    unittest.main()
