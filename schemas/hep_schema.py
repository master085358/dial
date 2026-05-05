"""
HEP Validator — Python implementation of the Hypothesis Elimination Protocol schema.

Three pressure types (from hep.cue Phase 3):
  DirectContradiction  — hypothesis directly contradicts documented evidence
  EvidenceGap          — hypothesis explains none of the provided evidence
  PriorElimination     — semantically similar to an already-eliminated candidate
"""


class HEPValidator:
    def __init__(self, evidence: list[str]):
        self.evidence = evidence

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        violations: list[str] = []
        scope_narrowings: list[str] = []

        claim = candidate.get("claim", "").lower()
        description = candidate.get("description", "").lower()
        text = claim + " " + description

        # 1. DirectContradiction
        for ev in self.evidence:
            if _contradicts(claim, ev.lower()):
                violations.append(
                    f"DirectContradiction: '{candidate['id']}' "
                    f"contradicts evidence: '{ev[:60]}'"
                )

        # 2. EvidenceGap — scope narrowing, not full elimination
        explains_any = any(_explains(text, ev.lower()) for ev in self.evidence)
        if not explains_any and self.evidence:
            scope_narrowings.append(
                f"Hypothesis {candidate['id']} explains none of the provided "
                f"evidence — scope limited to unexplored explanations"
            )

        # 3. PriorElimination
        for eliminated in stream.eliminated:
            if _semantically_similar(
                candidate.get("description", ""),
                eliminated.get("reason", ""),
            ):
                violations.append(
                    f"PriorElimination: semantically similar to already-eliminated "
                    f"'{eliminated['candidateid']}'"
                )
                break

        # 4. StructuralRequirement — must have proof_sketch (HEP Phase 2)
        if not candidate.get("proof_sketch"):
            violations.append(
                "MissingCausalAccount: candidate lacks proof_sketch "
                "(required by HEP Phase 2)"
            )

        if violations:
            return {
                "valid": False,
                "reason": violations[0],
                "violations": violations,
                "challenge_id": f"CE-{candidate['id']}-{stream.cycle}",
            }

        return {"valid": True, "scope_narrowings": scope_narrowings}


# ── Lexical helpers ────────────────────────────────────────────────────────────

def _contradicts(claim: str, evidence: str) -> bool:
    """Simple negation-pattern contradiction check."""
    negations = ["not ", "never ", "no ", "cannot ", "doesn't ", "isn't ", "нет "]
    for neg in negations:
        if neg in claim:
            base = evidence.replace(neg, "").strip()
            if base and base in claim:
                return True
    return False


def _explains(text: str, evidence: str) -> bool:
    """Keyword-overlap heuristic: ≥2 meaningful words shared."""
    stop = {"the", "a", "is", "was", "in", "of", "and", "to", "for", "that", "it"}
    ev_words = set(evidence.split()) - stop
    text_words = set(text.split())
    return len(ev_words & text_words) >= 2


def _semantically_similar(text1: str, text2: str) -> bool:
    """Bag-of-words Jaccard similarity (v2: replace with embeddings)."""
    w1 = set(text1.lower().split())
    w2 = set(text2.lower().split())
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) > 0.6
