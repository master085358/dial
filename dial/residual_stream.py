"""
ResidualStream v3 — adds fields for verbose v3 logging:
  assessment_breakdown, cross_support, rebuttals_log, obligations, problem.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamStats:
    llm_calls:        int = 0
    total_rebuttals:  int = 0
    total_eliminated: int = 0
    cycles_run:       int = 0


class ResidualStream:
    """Holds all state for one Dialectics run."""

    def __init__(self):
        # Core state
        self.candidates:   list[dict] = []
        self.survivors:    list[dict] = []
        self.eliminated:   list[dict] = []
        self.eliminated_with_challenges: list[dict] = []

        # Constraints — accumulate, never reset
        self.active_constraints: list[str] = []

        # Scope narrowings from rebuttal pipeline (v3)
        self.scope_narrowings: list[str] = []

        # Obligation gate
        self.obligations: list[dict] = []

        # x* — set when gate passes
        self.x_star: dict | None = None

        # Run metadata
        self.cycle:   int = 0
        self.history: list[dict] = []
        self.stats:   StreamStats = StreamStats()

        # v3: extra fields for verbose logging
        self.problem:               dict = {}
        self.assessment_breakdown:  dict = {}
        self.cross_support:         list[dict] = []
        self.rebuttals_log:         list[dict] = []

    def has_zero_survivors(self) -> bool:
        return len(self.survivors) == 0

    def snapshot(self) -> None:
        self.stats.cycles_run += 1
        self.history.append({
            "cycle":               self.cycle,
            "candidates":          [c["id"] for c in self.candidates],
            "survivors":           [s["candidateid"] for s in self.survivors],
            "eliminated_this_run": [
                e["candidateid"] for e in self.eliminated
                if e not in self.history
            ],
            "active_constraints":  len(self.active_constraints),
        })

    def to_dict(self) -> dict:
        return {
            "candidates":          self.candidates,
            "survivors":           self.survivors,
            "eliminated":          self.eliminated,
            "active_constraints":  self.active_constraints,
            "scope_narrowings":    self.scope_narrowings,
            "x_star":              self.x_star,
            "stats": {
                "llm_calls":        self.stats.llm_calls,
                "total_rebuttals":  self.stats.total_rebuttals,
                "total_eliminated": self.stats.total_eliminated,
                "cycles_run":       self.stats.cycles_run,
            },
        }