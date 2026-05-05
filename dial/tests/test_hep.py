"""tests/test_hep.py — HEP offline unit tests (v2 unchanged, 6 tests)."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from dial.schemas.hep_schema import HEPValidator
from dial.residual_stream import ResidualStream

def _stream():
    s = ResidualStream(); s.eliminated = []; return s

class TestHEPValidator(unittest.TestCase):
    def test_valid_candidate_passes(self):
        v = HEPValidator(evidence=["Service latency doubled", "New deployment occurred"])
        c = {"id":"C1","description":"Deployment caused latency",
             "claim":"New deployment caused latency doubling",
             "proof_sketch":"deployment occurred before latency spike"}
        self.assertTrue(v.validate(c, {}, _stream())["valid"])

    def test_missing_proof_sketch_fails(self):
        v = HEPValidator(evidence=["Any evidence here"])
        c = {"id":"C1","description":"test","claim":"Something caused something","proof_sketch":""}
        r = v.validate(c, {}, _stream())
        self.assertFalse(r["valid"])
        self.assertTrue(any("MissingCausalAccount" in x for x in r["violations"]))

    def test_prior_elimination_rejected(self):
        v = HEPValidator(evidence=["Some evidence"])
        stream = _stream()
        stream.eliminated = [{"candidateid":"C0",
            "reason":"deployment caused latency increase because of configuration drift"}]
        c = {"id":"C1","description":"deployment caused latency increase",
             "claim":"deployment latency cause configuration",
             "proof_sketch":"deployment happened then latency increased due to configuration"}
        self.assertFalse(v.validate(c, {}, stream)["valid"])

    def test_evidence_gap_recorded_as_scope_narrowing(self):
        v = HEPValidator(evidence=["Completely unrelated evidence item alpha beta"])
        c = {"id":"C1","description":"XYZ","claim":"XYZ caused ABC",
             "proof_sketch":"XYZ led to ABC via indirect mechanism"}
        r = v.validate(c, {}, _stream())
        self.assertTrue(r["valid"])
        self.assertGreater(len(r.get("scope_narrowings", [])), 0)

    def test_multiple_evidence_items(self):
        v = HEPValidator(evidence=["CPU usage increased","Memory stable","Network latency increased"])
        c = {"id":"C1","description":"CPU spike caused latency",
             "claim":"CPU usage increase caused network latency spike",
             "proof_sketch":"CPU usage increased leading to network latency degradation"}
        self.assertTrue(v.validate(c, {}, _stream())["valid"])

    def test_valid_result_structure(self):
        v = HEPValidator(evidence=["Test evidence"])
        c = {"id":"C1","description":"test","claim":"cause effect","proof_sketch":"causal argument here"}
        r = v.validate(c, {}, _stream())
        self.assertIn("valid", r)
        if r["valid"]: self.assertIn("scope_narrowings", r)
        else:
            self.assertIn("violations", r); self.assertIn("challenge_id", r)

if __name__ == "__main__":
    unittest.main(verbosity=2)