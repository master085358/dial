from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CycleStats:
    llm_calls: int = 0
    total_candidates: int = 0
    total_challenges: int = 0
    total_rebuttals: int = 0
    total_eliminated: int = 0
    cycles_run: int = 0


@dataclass
class ResidualStream:
    candidates: list[dict] = field(default_factory=list)
    survivors: list[dict] = field(default_factory=list)
    eliminated: list[dict] = field(default_factory=list)
    scope_narrowings: list[str] = field(default_factory=list)
    evidence_assessments: list[dict] = field(default_factory=list)  # new
    cross_support: list[dict] = field(default_factory=list)         # new
    accumulated_pressure: list[dict] = field(default_factory=list)  # new
    obligations: list[dict] = field(default_factory=list)
    active_constraints: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    eliminated_with_challenges: list[dict] = field(default_factory=list)  # new
    cycle: int = 0
    x_star: dict | None = None
    stats: CycleStats = field(default_factory=CycleStats)