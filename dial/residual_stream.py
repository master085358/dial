from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamStats:
    llm_calls: int = 0
    total_challenges: int = 0
    total_rebuttals: int = 0
    total_eliminated: int = 0


@dataclass
class ResidualStream:
    """State carrier between Attention and CUE phases across all cycles."""

    candidates: list[dict] = field(default_factory=list)
    survivors: list[dict] = field(default_factory=list)
    eliminated: list[dict] = field(default_factory=list)
    scope_narrowings: list[str] = field(default_factory=list)
    active_constraints: list[str] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    evidence_assessments: list[dict] = field(default_factory=list)
    cycle: int = 0
    x_star: Any = None
    history: list[dict] = field(default_factory=list)
    stats: StreamStats = field(default_factory=StreamStats)

    def snapshot(self) -> dict:
        snap = {
            "cycle": self.cycle,
            "candidates_count": len(self.candidates),
            "survivors_count": len(self.survivors),
            "eliminated_count": len(self.eliminated),
            "active_constraints": self.active_constraints.copy(),
            "scope_narrowings": self.scope_narrowings.copy(),
        }
        self.history.append(snap)
        return snap

    def has_converged(self) -> bool:
        """Obligation Gate: all obligations satisfied → system closed."""
        if not self.obligations:
            return False
        return all(o.get("satisfied", False) for o in self.obligations)

    def has_zero_survivors(self) -> bool:
        """Revision Loop trigger."""
        return len(self.survivors) == 0