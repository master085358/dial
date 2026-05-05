"""
Unit tests for CFFP schema validator — no Ollama required.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schemas.cffp_schema import CFFPValidator
from core.residual_stream import ResidualStream


INVARIANTS = [
    {"id": "I1", "description": "Evaluation terminates for finite rule sets", "class": "termination"},
    {"id": "I2", "description": "Identical inputs → identical evaluation orders", "class": "determinism"},
]
PROBLEM = {"construct": "evaluation_order", "invariants": INVARIANTS}


def test_valid_formalism_survives():
    validator = CFFPValidator(invariants=INVARIANTS)
    stream = ResidualStream()
    candidate = {
        "id": "C1",
        "description": "Left-to-right strict evaluation",
        "claim": "structure: ordered list | evaluation_rule: fold_left(rules, apply) | resolution_rule: declaration order is total",
        "proof_sketch": "I1: strict evaluation terminates for finite rule sets. I2: declaration order is fixed; same input is always deterministic and reproducible.",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert result["valid"], f"Expected valid, got: {result}"
    print("PASS test_valid_formalism_survives")


def test_missing_termination_eliminated():
    validator = CFFPValidator(invariants=INVARIANTS)
    stream = ResidualStream()
    candidate = {
        "id": "C2",
        "description": "Priority-based evaluation",
        "claim": "structure: priority queue | evaluation_rule: by priority | resolution_rule: highest first",
        "proof_sketch": "I2: same priority values always produce same order (reproducible).",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert not result["valid"]
    assert "I1" in result["reason"] or "termination" in result["reason"].lower()
    print("PASS test_missing_termination_eliminated")


def test_missing_determinism_eliminated():
    validator = CFFPValidator(invariants=INVARIANTS)
    stream = ResidualStream()
    candidate = {
        "id": "C3",
        "description": "Random evaluation",
        "claim": "structure: list | evaluation_rule: random order | resolution_rule: first result wins",
        "proof_sketch": "I1: random evaluation terminates for finite rule sets.",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert not result["valid"]
    assert "I2" in result["reason"] or "determinism" in result["reason"].lower()
    print("PASS test_missing_determinism_eliminated")


if __name__ == "__main__":
    test_valid_formalism_survives()
    test_missing_termination_eliminated()
    test_missing_determinism_eliminated()
    print("\nAll CFFP unit tests passed.")
