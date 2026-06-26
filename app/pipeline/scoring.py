from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from asteval import Interpreter

from app.core.logging import get_logger
from app.models.company import Company
from app.models.score import ScoreBreakdown
from app.models.signal import Signal

log = get_logger(__name__)


@dataclass
class ScoringRule:
    id: str
    label: str
    points: int
    requires_signal: str | None = None
    condition: str | None = None


@dataclass
class ScoringConfig:
    max_score: int
    rules: list[ScoringRule]


def load_scoring_config(path: Path) -> ScoringConfig:
    data = yaml.safe_load(path.read_text())
    rules = [
        ScoringRule(
            id=r["id"],
            label=r.get("label", r["id"]),
            points=int(r["points"]),
            requires_signal=r.get("requires_signal"),
            condition=r.get("condition"),
        )
        for r in data.get("rules", [])
    ]
    return ScoringConfig(max_score=int(data.get("max_score", 100)), rules=rules)


def score_company(
    company: Company,
    signals: list[Signal],
    config: ScoringConfig,
) -> tuple[int, list[ScoreBreakdown]]:
    signal_keys = {s.key for s in signals}
    context = _build_context(company, signal_keys)

    breakdown: list[ScoreBreakdown] = []
    total = 0

    for rule in config.rules:
        if rule.requires_signal and rule.requires_signal not in signal_keys:
            continue
        if rule.condition and not _eval_condition(rule.condition, context):
            continue
        breakdown.append(
            ScoreBreakdown(rule_id=rule.id, label=rule.label, points=rule.points)
        )
        total += rule.points

    if total > config.max_score:
        total = config.max_score

    return total, breakdown


def _build_context(company: Company, signal_keys: set[str]) -> dict[str, Any]:
    return {
        "employee_count": company.employee_count,
        "revenue": company.revenue,
        "industry": company.industry,
        "growth_rate": company.growth_rate or 0.0,
        "location_count": company.location_count or 0,
        "technologies": [t.lower() for t in company.technologies],
        "signal_keys": signal_keys,
    }


def _eval_condition(expr: str, context: dict[str, Any]) -> bool:
    interp = Interpreter(usersyms=context, no_print=True, minimal=False)
    try:
        result = interp(expr)
    except Exception as exc:
        log.warning("scoring.condition_error", expr=expr, error=str(exc))
        return False
    if interp.error:
        log.warning(
            "scoring.condition_error",
            expr=expr,
            error="; ".join(e.msg for e in interp.error),
        )
        return False
    return bool(result)
