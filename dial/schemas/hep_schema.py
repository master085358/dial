"""
HEP Schema v3.

Two validators in one file:
  HEPValidator  — offline Python validator (unit tests, no Ollama)
  HEPPhase3     — live LLM Phase 3: assess → rebuttal → derive
                  Fixes D1 (decisive calibration), D2 (rebuttals: 0), D4 (scope_narrowings: 0)
"""
from __future__ import annotations

import json
import re
import requests

from dial.prompts import get_prompt


# ── Offline validator (used by unit tests) ─────────────────────────────────────

class HEPValidator:
    """Offline Python CUE validator — no Ollama required."""

    def __init__(self, evidence: list[str]):
        self.evidence = evidence

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        violations: list[str] = []
        scope_narrowings: list[str] = []
        claim       = candidate.get("claim", "").lower()
        description = candidate.get("description", "").lower()

        # 1. DirectContradiction
        for ev in self.evidence:
            ev_lower = ev.lower()
            if _contradicts(claim, ev_lower):
                violations.append(
                    f"DirectContradiction: '{candidate['id']}' contradicts evidence '{ev[:60]}'"
                )

        # 2. EvidenceGap
        explains_any = any(
            _explains(claim + " " + description, ev.lower()) for ev in self.evidence
        )
        if not explains_any and self.evidence:
            scope_narrowings.append(
                f"Hypothesis '{candidate['id']}' explains no provided evidence; "
                "scope limited to unexplored explanations"
            )

        # 3. PriorElimination
        for eliminated in stream.eliminated:
            if _semantically_similar(candidate.get("description", ""), eliminated.get("reason", "")):
                violations.append(
                    f"PriorElimination: similar to already-eliminated '{eliminated['candidateid']}'"
                )
                break

        # 4. StructuralRequirements
        if not candidate.get("proof_sketch"):
            violations.append("MissingCausalAccount: candidate lacks proof_sketch required by HEP Phase 2")

        if violations:
            return {
                "valid": False,
                "reason": violations[0],
                "violations": violations,
                "challenge_id": f"CE-{candidate['id']}-{stream.cycle}",
            }
        return {"valid": True, "scope_narrowings": scope_narrowings}


# ── Live Phase3 (v3 — rebuttal pipeline active) ────────────────────────────────

class HEPPhase3:
    """
    Live LLM Phase 3 for HEP.

    Pipeline:
      1. _generate_assessments  — LLM assesses every (hypothesis, evidence) pair
                                   with calibrated weight definitions (D1 fix)
      2. _generate_rebuttals    — for each weight=strong inconsistency, ask the
                                   hypothesis to rebut (D2, D4 fix)
      3. _derive_survivors      — Python logic per hep.cue Derivation rules
    """

    def __init__(self, evidence: list[str], model: str, ollama_url: str):
        self.evidence   = evidence
        self.model      = model
        self.ollama_url = ollama_url

    def run(self, candidates: list[dict], stream) -> dict:
        ev_labeled = [{"id": f"E{i+1}", "description": e} for i, e in enumerate(self.evidence)]
        assessments = self._generate_assessments(candidates, ev_labeled, stream)
        rebuttals   = self._generate_rebuttals(candidates, ev_labeled, assessments)
        return self._derive_survivors(candidates, assessments, rebuttals, stream)

    # ── Step 1: Assessment ───────────────────────────────────────────────────

    def _generate_assessments(
        self,
        candidates: list[dict],
        ev_labeled: list[dict],
        stream,
    ) -> list[dict]:
        phenomenon = stream.problem.get("phenomenon", "") if hasattr(stream, "problem") else ""
        prompt = get_prompt("hep_phase3_assess").format(
            phenomenon=phenomenon,
            candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
            evidence_json=json.dumps(ev_labeled, ensure_ascii=False, indent=2),
        )
        raw    = self._call_llm(prompt)
        result = self._extract_json(raw)
        assessments = result.get("assessments", [])

        if hasattr(stream, "cross_support"):
            stream.cross_support = result.get("cross_support", [])

        # Fallback: safe uninformative set if LLM returns nothing
        if not assessments:
            assessments = [
                {
                    "hypothesisid": c["id"],
                    "evidenceid": e["id"],
                    "consistency": "uninformative",
                    "weight": "weak",
                    "argument": "LLM returned no assessments — defaulting to uninformative",
                }
                for c in candidates
                for e in ev_labeled
            ]
        return assessments

    # ── Step 2: Rebuttal pipeline (D2/D4 fix) ───────────────────────────────

    def _generate_rebuttals(
        self,
        candidates: list[dict],
        ev_labeled: list[dict],
        assessments: list[dict],
    ) -> list[dict]:
        """
        Called for EVERY assessment where:
          consistency == "inconsistent"  AND  weight == "strong"

        decisive → no rebuttal (per hep.cue)
        strong   → rebuttal permitted (refutation | scopenarrowing | evidenceunreliability)
        weak     → pressure recorded, no rebuttal required
        """
        rebuttals: list[dict] = []
        ev_map = {e["id"]: e["description"] for e in ev_labeled}

        for assessment in assessments:
            if (
                assessment.get("consistency") == "inconsistent"
                and assessment.get("weight") == "strong"
            ):
                cid = assessment["hypothesisid"]
                eid = assessment["evidenceid"]
                candidate = next((c for c in candidates if c["id"] == cid), None)
                if not candidate:
                    continue

                prompt = get_prompt("hep_phase3_rebuttal").format(
                    hypothesis_id=cid,
                    hypothesis_json=json.dumps(candidate, ensure_ascii=False, indent=2),
                    evidence_id=eid,
                    evidence_description=ev_map.get(eid, ""),
                    assessment_argument=assessment.get("argument", ""),
                )
                raw     = self._call_llm(prompt)
                rebuttal = self._extract_json(raw)

                rebuttal.setdefault("hypothesisid", cid)
                rebuttal.setdefault("evidenceid", eid)
                rebuttal.setdefault("kind", "scopenarrowing")
                rebuttal.setdefault("valid", True)
                rebuttal.setdefault("limitationdescription", "")

                # scopenarrowing is always valid by definition (hep.cue)
                if rebuttal["kind"] == "scopenarrowing":
                    rebuttal["valid"] = True

                rebuttals.append(rebuttal)

        return rebuttals

    # ── Step 3: Derive survivors (hep.cue Derivation rules) ─────────────────

    def _derive_survivors(
        self,
        candidates: list[dict],
        assessments: list[dict],
        rebuttals: list[dict],
        stream,
    ) -> dict:
        """
        From hep.cue:
          Eliminated if:
          (a) any decisive inconsistency targets it, OR
          (b) any strong inconsistency targets it with no valid rebuttal
        """
        rebuttal_index: dict[tuple, dict] = {}
        for r in rebuttals:
            key = (r.get("hypothesisid", ""), r.get("evidenceid", ""))
            rebuttal_index[key] = r

        eliminated: list[dict] = []
        survivors:  list[dict] = []
        scope_narrowings: list[str] = []
        cross_support: list[dict]   = []
        assessment_breakdown = {
            "total": len(assessments),
            "decisive": [],
            "strong":   [],
            "weak":     [],
            "uninformative": [],
        }

        for candidate in candidates:
            cid = candidate["id"]
            is_eliminated = False
            elimination_record: dict | None = None
            candidate_narrowings: list[str] = []
            remaining_pressure:   list[str] = []

            my_assessments = [a for a in assessments if a.get("hypothesisid") == cid]

            for a in my_assessments:
                consistency = a.get("consistency", "uninformative")
                weight      = a.get("weight", "weak")
                eid         = a.get("evidenceid", "?")
                key = f"{cid}×{eid}"

                if consistency == "inconsistent":
                    if weight == "decisive":
                        assessment_breakdown["decisive"].append(key)
                        elimination_record = {
                            "candidateid": cid,
                            "reason":     f"decisive_inconsistency ({eid}): {a.get('argument','')[:90]}",
                            "sourceid":   eid,
                            "violations": [a.get("argument", "")],
                        }
                        is_eliminated = True
                        break

                    elif weight == "strong":
                        assessment_breakdown["strong"].append(key)
                        rebuttal = rebuttal_index.get((cid, eid))

                        if rebuttal and rebuttal.get("valid", False):
                            if rebuttal["kind"] == "scopenarrowing":
                                lim = rebuttal.get("limitationdescription", "")
                                if lim:
                                    candidate_narrowings.append(lim)
                                    scope_narrowings.append(lim)
                            elif rebuttal["kind"] in ("refutation", "evidenceunreliability"):
                                pass  # dismissed — no trace
                        else:
                            elimination_record = {
                                "candidateid": cid,
                                "reason":     f"strong_inconsistency_unrebutted ({eid}): {a.get('argument','')[:90]}",
                                "sourceid":   eid,
                                "violations": [a.get("argument", "")],
                            }
                            is_eliminated = True
                            break

                    elif weight == "weak":
                        assessment_breakdown["weak"].append(key)
                        remaining_pressure.append(eid)

                    else:
                        assessment_breakdown["uninformative"].append(key)
                else:
                    assessment_breakdown["uninformative"].append(key)

            if is_eliminated and elimination_record:
                eliminated.append(elimination_record)
            else:
                survivors.append({
                    "candidateid":       cid,
                    "scopenarrowings":   candidate_narrowings,
                    "remainingpressure": remaining_pressure,
                })

        if hasattr(stream, "assessment_breakdown"):
            stream.assessment_breakdown = assessment_breakdown
        if hasattr(stream, "rebuttals_log"):
            stream.rebuttals_log = rebuttals

        return {
            "survivors":            survivors,
            "eliminated":           eliminated,
            "eliminated_with_challenges": eliminated,
            "scope_narrowings":     scope_narrowings,
            "rebuttals":            rebuttals,
            "cross_support":        cross_support,
            "assessment_breakdown": assessment_breakdown,
            "rebuttals_count":      len(rebuttals),
        }

    # ── LLM helpers ──────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        resp = requests.post(
            self.ollama_url + "/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 2048},
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _extract_json(self, raw: str) -> dict:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return {}

    def make_phase3(self, model: str) -> "HEPPhase3":
        """Factory method called by cycle_runner._build_phase3."""
        return HEPPhase3(
            evidence=self.evidence,
            model=model,
            ollama_url=self.ollama_url,
        )


# ── Helper functions ───────────────────────────────────────────────────────────

def _contradicts(claim: str, evidence: str) -> bool:
    negations = ["not", "never", "no ", "cannot", "doesn't", "isn't"]
    for neg in negations:
        if neg in claim and evidence.replace(neg, "").strip() in claim:
            return True
    return False


def _explains(text: str, evidence: str) -> bool:
    ev_words = set(evidence.split()) - {"the", "a", "is", "was", "in", "of"}
    text_words = set(text.split())
    overlap = ev_words & text_words
    return len(overlap) >= 2


def _semantically_similar(text1: str, text2: str) -> bool:
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2) / min(len(words1), len(words2))
    return overlap >= 0.6