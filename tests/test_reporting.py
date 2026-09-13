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
from solana_memecoin_research.reporting import render_markdown


class ReportingTests(unittest.TestCase):
    def test_markdown_contains_required_sections(self) -> None:
        data = load_fixture(Path(__file__).parent / "fixtures" / "healthy.json")
        report = Analyzer(
            dex=FixtureDex(data),
            solana=FixtureSolana(data),
            jupiter=FixtureJupiter(data),
            birdeye=FixtureBirdeye(data),
            x_client=FixtureX(data),
        ).analyze(ResearchInput(mint="MINT"))
        rendered = render_markdown(report)
        for heading in (
            "Technical and liquidity",
            "Ownership and coordination",
            "Repeat-winner wallet research",
            "Social and narrative",
            "Upgrade conditions",
            "Data limitations",
        ):
            self.assertIn(heading, rendered)


if __name__ == "__main__":
    unittest.main()
