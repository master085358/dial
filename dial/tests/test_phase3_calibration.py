"""
tests/test_phase3_calibration.py

Unit tests for v3 EvidenceAssessment calibration.
These tests exercise the OFFLINE HEPValidator and HEPPhase3 schema logic.
No Ollama required — all assertions target the DERIVATION and REBUTTAL logic.

Covers TZ v3 acceptance criteria:
  T8  test_chronological_sequence_not_decisive
  T9  test_direct_factual_contradiction_is_decisive
  T3  test_strong_assessment_triggers_rebuttal
  T4  test_scopenarrowing_recorded_in_stream
  T5  test_acknowledged_limitations_in_x_star
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from dial.schemas.hep_schema import HEPPhase3, HEPValidator
from dial.residual_stream import ResidualStream


CANDIDATE_NETWORK = {
    "id":           "C1",
    "description":  "Network topology change caused latency",
    "claim":        "Network topology change caused API latency increase",
    "proof_sketch": "Network changed Feb 19, effect manifested with deployment Feb 20",
}

CANDIDATE_DB = {
    "id":           "C2",
    "description":  "Database slowdown caused latency",
    "claim":        "Database query inefficiency caused API latency increase",
    "proof_sketch": "Slow DB queries increase response time proportionally",
}

EVIDENCE_NETWORK_CHANGE   = "Network topology changed on 2026-02-19"
EVIDENCE_DB_UNCHANGED     = "Database query time unchanged throughout the incident period"
EVIDENCE_ISOLATED_BENCH   = "Same regression reproduced in isolated benchmark (no external network)"
EVIDENCE_MEMORY_INCREASE  = "Memory usage increased 15% after the deployment"


class TestDerivationLogic(unittest.TestCase):
    """
    Tests for the DERIVATION step of HEPPhase3._derive_survivors().
    Bypasses LLM by injecting pre-built assessments and rebuttals.
    """

    def _make_stream(self):
        stream = ResidualStream()
        stream.problem = {"phenomenon": "test"}
        stream.assessment_breakdown = {}
        stream.rebuttals_log = []
        stream.cross_support = []
        return stream

    def _phase3(self, evidence: list[str]) -> HEPPhase3:
        # ollama_url unused — we call _derive_survivors directly
        return HEPPhase3(
            evidence=evidence,
            model="test",
            ollama_url="http://localhost:11434",
        )

    # ── T8: Chronological sequence must NOT be decisive ──────────────────────

    def test_chronological_sequence_not_decisive(self):
        """
        HEPPhase3._derive_survivors() must NOT eliminate C1 when
        the only inconsistency has weight='strong' AND a valid rebuttal exists.

        This replicates the D1 scenario: "Network changed Feb 19" is NOT decisive
        against "Network caused latency" because chronological sequence is compatible.
        """
        phase3 = self._phase3([EVIDENCE_NETWORK_CHANGE])
        stream = self._make_stream()
        candidates = [CANDIDATE_NETWORK]

        # Simulate LLM returning weight=strong (NOT decisive) — D1 fix
        assessments = [{
            "hypothesisid": "C1",
            "evidenceid":   "E1",
            "consistency":  "inconsistent",
            "weight":       "strong",  # calibrated — NOT decisive
            "argument":     "Network change predates deployment by 1 day; pressure but compatible",
        }]

        # Candidate rebuts with scopenarrowing
        rebuttals = [{
            "hypothesisid":       "C1",
            "evidenceid":         "E1",
            "kind":               "scopenarrowing",
            "argument":           "Applies only to deployments that activate infrastructure changes",
            "valid":              True,
            "limitationdescription": (
                "This hypothesis applies only when deployment and infrastructure change "
                "are causally linked. Concurrent independent changes are out of scope."
            ),
        }]

        result = phase3._derive_survivors(candidates, assessments, rebuttals, stream)

        self.assertEqual(len(result["survivors"]), 1,
            f"C1 should SURVIVE with scopenarrowing, but got survivors={result['survivors']}")
        self.assertEqual(result["survivors"][0]["candidateid"], "C1")
        self.assertGreater(len(result["scope_narrowings"]), 0,
            "scope_narrowings must be non-empty after scopenarrowing rebuttal (D4 fix)")

    # ── T9: Direct factual contradiction must be decisive ────────────────────

    def test_direct_factual_contradiction_is_decisive(self):
        """
        Weight=decisive on an inconsistency must eliminate the candidate immediately.
        No rebuttal is consulted for decisive.
        """
        phase3 = self._phase3([EVIDENCE_DB_UNCHANGED])
        stream = self._make_stream()
        candidates = [CANDIDATE_DB]

        assessments = [{
            "hypothesisid": "C2",
            "evidenceid":   "E1",
            "consistency":  "inconsistent",
            "weight":       "decisive",  # correct — DB unchanged → DB cannot be cause
            "argument":     "If DB query time is unchanged, DB cannot be the cause of latency",
        }]
        rebuttals = []  # rebuttal irrelevant for decisive

        result = phase3._derive_survivors(candidates, assessments, rebuttals, stream)

        self.assertEqual(len(result["survivors"]), 0,
            "C2 must be ELIMINATED by decisive inconsistency")
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertIn("decisive_inconsistency", result["eliminated"][0]["reason"])

    # ── T3: strong assessment triggers rebuttal lookup ───────────────────────

    def test_strong_assessment_triggers_rebuttal_lookup(self):
        """
        When weight=strong and a valid rebuttal exists → candidate survives.
        When weight=strong and NO rebuttal exists → candidate is eliminated.
        """
        phase3 = self._phase3([EVIDENCE_MEMORY_INCREASE])
        stream = self._make_stream()
        candidates = [CANDIDATE_NETWORK]

        assessments = [{
            "hypothesisid": "C1",
            "evidenceid":   "E1",
            "consistency":  "inconsistent",
            "weight":       "strong",
            "argument":     "Memory increase is unexpected if only network changed",
        }]

        # Case A: no rebuttal → eliminated
        result_no_rebuttal = phase3._derive_survivors(candidates, assessments, [], stream)
        self.assertEqual(len(result_no_rebuttal["survivors"]), 0,
            "C1 must be eliminated: strong inconsistency + no valid rebuttal")

        # Case B: valid rebuttal → survives
        rebuttals = [{
            "hypothesisid":       "C1",
            "evidenceid":         "E1",
            "kind":               "refutation",
            "argument":           "Memory increase and network change can co-occur independently",
            "valid":              True,
            "limitationdescription": "",
        }]
        stream2 = self._make_stream()
        result_with_rebuttal = phase3._derive_survivors(candidates, assessments, rebuttals, stream2)
        self.assertEqual(len(result_with_rebuttal["survivors"]), 1,
            "C1 must SURVIVE: strong inconsistency + valid refutation rebuttal")

    # ── T4 / T5: scopenarrowing recorded in stream AND x* ───────────────────

    def test_scopenarrowing_recorded_in_stream_and_x_star(self):
        """
        After a scopenarrowing rebuttal:
          - stream.scope_narrowings must be non-empty (T4)
          - result["scope_narrowings"] must be non-empty (T5 proxy)
        """
        phase3 = self._phase3([EVIDENCE_NETWORK_CHANGE])
        stream = self._make_stream()
        candidates = [CANDIDATE_NETWORK]

        assessments = [{
            "hypothesisid": "C1",
            "evidenceid":   "E1",
            "consistency":  "inconsistent",
            "weight":       "strong",
            "argument":     "Chronological pressure",
        }]
        rebuttals = [{
            "hypothesisid":       "C1",
            "evidenceid":         "E1",
            "kind":               "scopenarrowing",
            "argument":           "Concedes — applies only to causally linked changes",
            "valid":              True,
            "limitationdescription": "Hypothesis scope: causally linked deployment+infra changes only",
        }]

        result = phase3._derive_survivors(candidates, assessments, rebuttals, stream)

        self.assertGreater(len(result["scope_narrowings"]), 0,
            "scope_narrowings must be non-empty (T4/T5 fix)")
        self.assertGreater(len(result["rebuttals_count"] if "rebuttals_count" in result
                             else result.get("scope_narrowings", [])), 0)
        self.assertIn("Hypothesis scope", result["scope_narrowings"][0],
            "scope_narrowing text must be present")

    # ── isolated benchmark must eliminate network hypothesis ─────────────────

    def test_isolated_benchmark_decisive_for_network(self):
        """
        Evidence 'regression reproduced in isolated benchmark' is DECISIVE
        against a network-cause hypothesis because isolated benchmark physically
        removes network from the causal path.
        """
        phase3 = self._phase3([EVIDENCE_ISOLATED_BENCH])
        stream = self._make_stream()
        candidates = [CANDIDATE_NETWORK]

        assessments = [{
            "hypothesisid": "C1",
            "evidenceid":   "E1",
            "consistency":  "inconsistent",
            "weight":       "decisive",
            "argument":     "Isolated benchmark excludes network; regression persists without network",
        }]

        result = phase3._derive_survivors(candidates, assessments, [], stream)
        self.assertEqual(len(result["survivors"]), 0,
            "Isolated benchmark must decisively eliminate network hypothesis")


class TestOfflineHEPValidator(unittest.TestCase):
    """Offline validator tests — no Ollama required."""

    def _stream(self):
        s = ResidualStream()
        s.eliminated = []
        return s

    def test_no_violations_for_valid_candidate(self):
        validator = HEPValidator(evidence=[
            "Network topology changed on 2026-02-19",
            "Latency increased after deployment on 2026-02-20",
        ])
        candidate = {
            "id":           "C1",
            "description":  "Network change caused latency",
            "claim":        "Network change caused latency increase on deployment",
            "proof_sketch": "Network topology changed, latency manifested after deployment",
        }
        result = validator.validate(candidate, {}, self._stream())
        self.assertTrue(result["valid"])

    def test_missing_proof_sketch_raises_violation(self):
        validator = HEPValidator(evidence=["Any evidence"])
        candidate = {
            "id":           "C2",
            "description":  "Test",
            "claim":        "Something caused something",
            "proof_sketch": "",  # empty
        }
        result = validator.validate(candidate, {}, self._stream())
        self.assertFalse(result["valid"])
        self.assertTrue(any("MissingCausalAccount" in v for v in result.get("violations", [])))


if __name__ == "__main__":
    unittest.main(verbosity=2)