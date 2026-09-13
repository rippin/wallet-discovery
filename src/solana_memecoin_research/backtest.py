from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable


def _metrics(rows: list[dict[str, Any]], signal: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    selected = [row for row in rows if signal(row)]
    avoided = [row for row in rows if not signal(row)]
    catastrophic = [row for row in rows if row["outcome"].get("catastrophic")]
    positive = [
        row
        for row in selected
        if float(row["outcome"].get("return_pct") or 0) > 0
    ]
    returns = [float(row["outcome"].get("return_pct") or 0) for row in selected]
    drawdowns = [
        float(row["outcome"].get("max_drawdown_pct") or 0) for row in selected
    ]
    avoided_catastrophic = [
        row for row in avoided if row["outcome"].get("catastrophic")
    ]
    false_avoid = [
        row
        for row in avoided
        if not row["outcome"].get("catastrophic")
        and float(row["outcome"].get("return_pct") or 0) > 0
    ]
    return {
        "cases": len(rows),
        "selected": len(selected),
        "catastrophic_loss_avoidance_pct": (
            len(avoided_catastrophic) / len(catastrophic) * 100 if catastrophic else None
        ),
        "false_avoid_count": len(false_avoid),
        "profitable_call_precision_pct": (
            len(positive) / len(selected) * 100 if selected else None
        ),
        "mean_selected_return_pct": mean(returns) if returns else None,
        "worst_selected_drawdown_pct": min(drawdowns) if drawdowns else None,
    }


def run_backtest(dataset: Path) -> dict[str, Any]:
    rows = []
    for line_number, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if "report" not in row or "outcome" not in row:
            raise ValueError(f"line {line_number} needs report and outcome objects")
        rows.append(row)
    rows.sort(key=lambda row: row["report"].get("timestamp", ""))

    def model(row: dict[str, Any]) -> bool:
        return row["report"].get("verdict") == "Consider"

    def liquidity_only(row: dict[str, Any]) -> bool:
        return float(
            (row["report"].get("components") or {}).get("liquidity") or 0
        ) >= 70

    def ownership_only(row: dict[str, Any]) -> bool:
        return float(
            (row["report"].get("components") or {}).get("ownership") or 0
        ) >= 70

    def deterministic_random(row: dict[str, Any]) -> bool:
        identity = (
            row["report"].get("timestamp", "")
            + str((row["report"].get("input") or {}).get("mint", ""))
        )
        return hashlib.sha256(identity.encode()).digest()[0] < 128

    fold_size = max(1, len(rows) // 3) if rows else 1
    folds = [
        _metrics(rows[start : start + fold_size], model)
        for start in range(0, len(rows), fold_size)
    ]
    return {
        "model": _metrics(rows, model),
        "baselines": {
            "liquidity_only": _metrics(rows, liquidity_only),
            "ownership_only": _metrics(rows, ownership_only),
            "deterministic_random": _metrics(rows, deterministic_random),
        },
        "chronological_folds": folds,
        "note": (
            "Returns must already include the user's chosen delay, fees, slippage, "
            "and position sizing; this command does not manufacture missing outcomes."
        ),
    }

