import json
import tempfile
import unittest
from pathlib import Path

from solana_memecoin_research.backtest import run_backtest


class BacktestTests(unittest.TestCase):
    def test_backtest_metrics(self) -> None:
        rows = [
            {
                "report": {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "verdict": "Avoid",
                    "components": {"liquidity": 20, "ownership": 30},
                    "input": {"mint": "A"},
                },
                "outcome": {
                    "return_pct": -90,
                    "max_drawdown_pct": -95,
                    "catastrophic": True,
                },
            },
            {
                "report": {
                    "timestamp": "2026-01-02T00:00:00Z",
                    "verdict": "Consider",
                    "components": {"liquidity": 80, "ownership": 80},
                    "input": {"mint": "B"},
                },
                "outcome": {
                    "return_pct": 25,
                    "max_drawdown_pct": -10,
                    "catastrophic": False,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "outcomes.jsonl"
            dataset.write_text(
                "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
            )
            result = run_backtest(dataset)
        self.assertEqual(result["model"]["catastrophic_loss_avoidance_pct"], 100)
        self.assertEqual(result["model"]["profitable_call_precision_pct"], 100)
        self.assertEqual(result["model"]["mean_selected_return_pct"], 25)


if __name__ == "__main__":
    unittest.main()
