"""tests/test_cffp.py — CFFP offline unit tests (v3, 6 tests)."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import unittest
from dial.schemas.cffp_schema import CFFPValidator
from dial.residual_stream import ResidualStream

INVARIANTS = [
    {"id": "I1", "description": "Higher priority always dequeued first", "class": "determinism"},
    {"id": "I2", "description": "Dequeue terminates in finite time", "class": "termination"},
]

def _stream():
    s = ResidualStream(); s.eliminated = []; return s

def _candidate(description, claim, proof_sketch):
    return {"id": "C1", "description": description, "claim": claim, "proof_sketch": proof_sketch}

class TestCFFPValidator(unittest.TestCase):
    def test_valid_candidate_passes(self):
        v = CFFPValidator(invariants=INVARIANTS)
        c = _candidate(
            "Max-heap priority queue",
            "structure: max-heap | evaluation_rule: dequeue root | resolution_rule: rebuild",
            "I1: deterministic by heap invariant — highest priority always at root. "
            "I2: dequeue terminates in O(log n) finite time.",
        )
        self.assertTrue(v.validate(c, {}, _stream())["valid"])

    def test_missing_termination_proof_fails(self):
        v = CFFPValidator(invariants=INVARIANTS)
        c = _candidate(
            "Unordered scan",
            "structure: list | evaluation_rule: linear scan | resolution_rule: first found",
            "I1: deterministic scan order. I2: no termination guarantee stated.",
        )
        r = v.validate(c, {}, _stream())
        self.assertFalse(r["valid"])

    def test_missing_determinism_proof_fails(self):
        v = CFFPValidator(invariants=INVARIANTS)
        c = _candidate(
            "Random priority queue",
            "structure: list | evaluation_rule: random selection | resolution_rule: arbitrary",
            "I1: random selection used. I2: terminates in O(n) time.",
        )
        r = v.validate(c, {}, _stream())
        self.assertFalse(r["valid"])

    def test_short_proof_sketch_fails_static_obligation(self):
        v = CFFPValidator(invariants=INVARIANTS)
        c = _candidate("test", "claim", "short")
        r = v.validate(c, {}, _stream())
        self.assertFalse(r["valid"])

    def test_composition_failure_detected(self):
        v = CFFPValidator(invariants=INVARIANTS, canonical_constructs=["stable_sort"])
        c = _candidate(
            "Anti-sort",
            "structure: not stable_sort | evaluation_rule: arbitrary | resolution_rule: none",
            "I1: deterministic enough. I2: terminates eventually in finite bounded time.",
        )
        r = v.validate(c, {}, _stream())
        self.assertFalse(r["valid"])
        self.assertTrue(any("CompositionFailure" in x for x in r.get("violations", [])))

    def test_result_structure(self):
        v = CFFPValidator(invariants=INVARIANTS)
        c = _candidate(
            "Sorted list",
            "structure: sorted_list | evaluation_rule: pop first | resolution_rule: insertion_sort",
            "I1: insertion sort is deterministic — same input always produces same order, reproducible. "
            "I2: pop terminates in O(1) finite time, insertion sort terminates in O(n^2).",
        )
        r = v.validate(c, {}, _stream())
        self.assertIn("valid", r)

if __name__ == "__main__":
    unittest.main(verbosity=2)