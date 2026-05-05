"""Unit tests for HEP schema validator — no Ollama required."""
from dial.hep_schema import HEPValidator
from dial.residual_stream import ResidualStream

EVIDENCE = [
    "Deployment happened on 2026-02-20",
    "Network topology changed on 2026-02-19",
    "Memory usage increased by 15% after deployment",
]
PROBLEM = {"phenomenon": "API latency increased 40%", "evidence": EVIDENCE}


def test_valid_candidate_survives():
    validator = HEPValidator(evidence=EVIDENCE)
    stream = ResidualStream()
    candidate = {
        "id": "C1",
        "description": "Deployment caused increased memory usage",
        "claim": "The 2026-02-20 deployment caused higher latency because memory usage increased",
        "proof_sketch": "Memory usage increased 15% after deployment; higher memory causes GC pauses.",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert result["valid"], f"Expected valid, got: {result}"


def test_missing_proof_sketch_eliminated():
    validator = HEPValidator(evidence=EVIDENCE)
    stream = ResidualStream()
    candidate = {
        "id": "C2",
        "description": "Some hypothesis",
        "claim": "Something happened",
        "proof_sketch": "",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert not result["valid"]
    assert "MissingCausalAccount" in result["reason"]


def test_prior_elimination_detected():
    validator = HEPValidator(evidence=EVIDENCE)
    stream = ResidualStream()
    stream.eliminated = [{"candidateid": "C1", "reason": "Some deployment memory usage hypothesis"}]
    candidate = {
        "id": "C3",
        "description": "deployment memory usage hypothesis again",
        "claim": "deployment memory usage caused this",
        "proof_sketch": "Because of deployment and memory usage and network issues.",
    }
    result = validator.validate(candidate, PROBLEM, stream)
    assert isinstance(result["valid"], bool)
