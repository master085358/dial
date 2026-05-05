"""
CFFP Validator — Python implementation of the Constraint-First Formalization Protocol.

Checks candidates against:
  1. Declared invariants (termination, determinism, general)
  2. Composition failures with canonical constructs
  3. Static obligations (Phase 5 CFFP)
"""


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

        # 1. Invariant checks
        for inv in self.invariants:
            result = self._check_invariant(candidate, inv)
            if result["violated"]:
                violations.append(
                    f"Counterexample[{inv['id']}]: {result['witness']}"
                )

        # 2. Composition failures (irrebuttable in CFFP)
        for canon in self.canonical_constructs:
            if self._check_composition(candidate, canon):
                violations.append(
                    f"CompositionFailure: conflicts with canonical '{canon}'"
                )

        # 3. Static obligations (Phase 5)
        static = self._check_static_obligations(candidate)
        if not static["provable"]:
            scope_narrowings.append(static["blocker"])

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

        if inv_class == "termination":
            keywords = ["terminat", "finite", "halts", "ends", "конечн", "завершает"]
            if not any(kw in combined for kw in keywords):
                return {
                    "violated": True,
                    "witness": (
                        f"Candidate '{candidate['id']}' does not address "
                        f"termination invariant [{inv['id']}]"
                    ),
                }

        if inv_class == "determinism":
            keywords = ["deterministic", "same input", "идентичн",
                        "одинаков", "воспроизводим", "reproducible"]
            if not any(kw in combined for kw in keywords):
                return {
                    "violated": True,
                    "witness": (
                        f"Candidate '{candidate['id']}' does not guarantee "
                        f"determinism invariant [{inv['id']}]"
                    ),
                }

        return {"violated": False, "witness": None}

    def _check_composition(self, candidate: dict, canon: str) -> bool:
        claim = candidate.get("claim", "").lower()
        canon_lower = canon.lower()
        return f"not {canon_lower}" in claim or f"without {canon_lower}" in claim

    def _check_static_obligations(self, candidate: dict) -> dict:
        proof = candidate.get("proof_sketch", "")
        if len(proof) < 20:
            return {
                "provable": False,
                "blocker": (
                    f"proof_sketch too short for static analysis "
                    f"(need ≥20 chars, got {len(proof)})"
                ),
            }
        return {"provable": True}
