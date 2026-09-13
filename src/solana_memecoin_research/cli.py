from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .analysis import Analyzer
from .backtest import run_backtest
from .fixtures import (
    FixtureBirdeye,
    FixtureDex,
    FixtureJupiter,
    FixtureSolana,
    FixtureX,
    load_fixture,
)
from .http import HttpClient
from .models import ResearchInput
from .providers import (
    BirdeyeClient,
    DexScreenerClient,
    JupiterClient,
    SolanaRpcClient,
    XClient,
    is_solana_address,
)
from .reporting import render_markdown, write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memecoin-research",
        description="Read-only Solana memecoin research reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="generate a point-in-time report")
    report.add_argument("--mint", required=True, help="exact Solana token mint")
    report.add_argument("--dex-url")
    report.add_argument("--x-url", action="append", default=[])
    report.add_argument("--suspected-wallet", action="append", default=[])
    report.add_argument("--holding-period", default="unspecified")
    report.add_argument("--position-usd", type=float, default=500.0)
    report.add_argument("--history-signatures", type=int, default=200)
    report.add_argument("--wallet-scan", action="store_true")
    report.add_argument(
        "--cohort-file",
        type=Path,
        help="JSONL or JSON array of prior point-in-time report snapshots",
    )
    report.add_argument("--output", type=Path, help="Markdown report path")
    report.add_argument("--json-output", type=Path, help="JSON snapshot path")
    report.add_argument(
        "--offline-fixture",
        type=Path,
        help="deterministic provider fixture; performs no network requests",
    )

    backtest = sub.add_parser("backtest", help="evaluate timestamped report outcomes")
    backtest.add_argument("--dataset", required=True, type=Path)
    backtest.add_argument("--output", type=Path)
    return parser


def _load_cohorts(path: Path | None) -> list[dict]:
    if not path:
        return []
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise SystemExit("--cohort-file JSON must be an array or JSONL")
        return value
    reports = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if "report" in value:
            value = value["report"]
        if not isinstance(value, dict):
            raise SystemExit(f"--cohort-file line {line_number} is not an object")
        reports.append(value)
    return reports


def _analyzer(args: argparse.Namespace) -> Analyzer:
    cohorts = _load_cohorts(args.cohort_file)
    if args.offline_fixture:
        data = load_fixture(args.offline_fixture)
        return Analyzer(
            dex=FixtureDex(data),
            solana=FixtureSolana(data),
            jupiter=FixtureJupiter(data),
            birdeye=FixtureBirdeye(data) if "wallet_research" in data else None,
            x_client=FixtureX(data) if "social" in data else None,
            cohort_reports=cohorts,
        )
    http = HttpClient()
    rpc_url = os.environ.get(
        "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
    )
    helius_key = os.environ.get("HELIUS_API_KEY")
    if helius_key and "SOLANA_RPC_URL" not in os.environ:
        rpc_url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
    birdeye_key = os.environ.get("BIRDEYE_API_KEY")
    x_token = os.environ.get("X_BEARER_TOKEN")
    return Analyzer(
        dex=DexScreenerClient(http),
        solana=SolanaRpcClient(http, rpc_url),
        jupiter=JupiterClient(http, os.environ.get("JUPITER_API_KEY")),
        birdeye=BirdeyeClient(http, birdeye_key) if birdeye_key else None,
        x_client=XClient(http, x_token) if x_token else None,
        cohort_reports=cohorts,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "backtest":
        result = run_backtest(args.dataset)
        rendered = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.position_usd <= 0:
        raise SystemExit("--position-usd must be positive")
    if not 10 <= args.history_signatures <= 10_000:
        raise SystemExit("--history-signatures must be between 10 and 10000")
    if not args.offline_fixture and not is_solana_address(args.mint):
        raise SystemExit("--mint must be a valid 32-byte base58 Solana address")
    research_input = ResearchInput(
        mint=args.mint,
        dex_url=args.dex_url,
        x_urls=args.x_url,
        suspected_wallets=args.suspected_wallet,
        holding_period=args.holding_period,
        position_usd=args.position_usd,
        history_signatures=args.history_signatures,
        wallet_scan=args.wallet_scan,
    )
    report = _analyzer(args).analyze(research_input)
    write_report(report, args.output, args.json_output)
    if not args.output:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
