"""
CFFP Validator — Constraint-First Formalization Protocol (offline shim for unit tests).
"""
from __future__ import annotations


class CFFPValidator:
    def __init__(
        self,
        invariants: list[dict],
        canonical_constructs: list[str] | None = None,
    ):
        self.invariants = invariants
        self.canonical_constructs = canonical_constructs or []

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        violations: list[str] = []
        scope_narrowings: list[str] = []

        for inv in self.invariants:
            result = self._check_invariant(candidate, inv)
            if result["violated"]:
                violations.append(f"Counterexample[{inv['id']}]: {result['witness']}")

        for canon in self.canonical_constructs:
            if self._check_composition(candidate, canon):
                violations.append(f"CompositionFailure: conflicts with canonical '{canon}'")

        proof = candidate.get("proof_sketch", "")
        if not proof or len(proof.strip()) < 20:
            scope_narrowings.append(
                f"proof_sketch too short for static analysis "
                f"(need ≥20 chars, got {len(proof.strip())})"
            )

        if violations:
            return {
                "valid": False,
                "reason": f"invariant_violation: {violations[0]}",
                "violations": violations,
                "challenge_id": f"CFFP-CE-{candidate['id']}",
            }

        return {"valid": True, "scope_narrowings": scope_narrowings}

    def _check_invariant(self, candidate: dict, inv: dict) -> dict:
        claim = candidate.get("claim", "")
        proof = candidate.get("proof_sketch", "")
        combined = (claim + " " + proof).lower()
        inv_class = inv.get("class", "")
        inv_id = inv.get("id", "?")

        if inv_class == "termination":
            positive_kws = ["terminat", "finite", "halts", "ends", "completes",
                            "конечн", "завершает"]
            if not any(kw in combined for kw in positive_kws):
                return {
                    "violated": True,
                    "witness": (
                        f"Candidate '{candidate['id']}' does not address "
                        f"termination invariant [{inv_id}]: proof_sketch lacks "
                        f"'terminates'/'finite'/'halts'"
                    ),
                }

        if inv_class == "determinism":
            # Explicit nondeterminism markers → immediate violation
            nondeterminism_markers = ["random", "nondeterministic", "arbitrary", "shuffle"]
            if any(m in combined for m in nondeterminism_markers):
                return {
                    "violated": True,
                    "witness": (
                        f"Candidate '{candidate['id']}' explicitly uses a nondeterministic "
                        f"mechanism, violating determinism invariant [{inv_id}]"
                    ),
                }
            # Must also assert determinism positively
            positive_kws = [
                "deterministic", "same input", "identical input",
                "reproducible", "идентичн", "одинаков", "воспроизводим",
            ]
            if not any(kw in combined for kw in positive_kws):
                return {
                    "violated": True,
                    "witness": (
                        f"Candidate '{candidate['id']}' does not guarantee "
                        f"determinism invariant [{inv_id}]: proof_sketch lacks "
                        f"'deterministic'/'reproducible'/'same input'"
                    ),
                }

        return {"violated": False, "witness": None}

    def _check_composition(self, candidate: dict, canon: str) -> bool:
        claim = candidate.get("claim", "").lower()
        canon_lower = canon.lower()
        return f"not {canon_lower}" in claim or f"without {canon_lower}" in claim

    def make_phase3(self, model: str):
        from dial.cffp_schema import CFFPPhase3
        return CFFPPhase3(
            invariants=self.invariants, model=model,
            canonical_constructs=self.canonical_constructs,
        )