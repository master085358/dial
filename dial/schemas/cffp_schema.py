"""
CFFP Schema v3.

Two validators:
  CFFPValidator — offline Python validator (unit tests, no Ollama)
  CFFPPhase3    — live LLM Phase 3: counterexample → rebuttal → derive  (D3 fix)
"""
from __future__ import annotations

import json
import re
import requests

from dial.prompts import get_prompt


# ── Offline validator (used by unit tests) ─────────────────────────────────────

class CFFPValidator:
    """Offline Python CUE validator — no Ollama required."""

    def __init__(self, invariants: list[dict], canonical_constructs: list[str] | None = None):
        self.invariants           = invariants
        self.canonical_constructs = canonical_constructs or []

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        violations:      list[str] = []
        scope_narrowings: list[str] = []

        # Phase 3 CFFP: invariant checks
        for inv in self.invariants:
            check = self._check_invariant(candidate, inv)
            if check["violated"]:
                violations.append(
                    f"Counterexample({inv['id']}): {check['witness']}"
                )

        # Phase 3 CFFP: composition failures (irrebuttable)
        for canon in self.canonical_constructs:
            if self._check_composition(candidate, canon):
                violations.append(f"CompositionFailure: conflicts with canonical '{canon}'")

        # Phase 5 CFFP: static obligations
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
        text  = (claim + " " + proof).lower()
        inv_class = inv.get("class", "")

        if inv_class == "termination":
            if not any(kw in text for kw in ("terminat", "finite", "halts", "ends", "bounded")):
                return {
                    "violated": True,
                    "witness": f"Candidate '{candidate['id']}' does not address termination ({inv['id']})",
                }
        elif inv_class == "determinism":
            if not any(kw in text for kw in ("deterministic", "same input", "reproducible", "stable")):
                return {
                    "violated": True,
                    "witness": f"Candidate '{candidate['id']}' does not guarantee determinism ({inv['id']})",
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
                "blocker": f"proof_sketch too short for static analysis (need ≥20 chars, got {len(proof)})",
            }
        return {"provable": True}

    def make_phase3(self, model: str) -> "CFFPPhase3":
        """Factory method called by cycle_runner._build_phase3."""
        raise ImportError(
            "CFFPPhase3 requires ollama_url. Use CFFPPhase3() directly."
        )


# ── Live Phase3 (v3 — D3 fix) ─────────────────────────────────────────────────

class CFFPPhase3:
    """
    Live LLM Phase 3 for CFFP.

    Pipeline:
      1. _generate_counterexamples  — LLM generates counterexamples per (candidate, invariant)
      2. _generate_rebuttals        — for each violation_found CE, candidate may rebut
      3. _derive_survivors          — Python logic per cffp.cue Derivation rules
    """

    def __init__(
        self,
        invariants: list[dict],
        canonical_constructs: list[str],
        model: str,
        ollama_url: str,
    ):
        self.invariants           = invariants
        self.canonical_constructs = canonical_constructs
        self.model                = model
        self.ollama_url           = ollama_url

    def run(self, candidates: list[dict], stream) -> dict:
        counterexamples = self._generate_counterexamples(candidates)
        rebuttals       = self._generate_rebuttals(candidates, counterexamples)
        return self._derive_survivors(candidates, counterexamples, rebuttals)

    # ── Step 1: Generate counterexamples ────────────────────────────────────

    def _generate_counterexamples(self, candidates: list[dict]) -> list[dict]:
        prompt = get_prompt("cffp_phase3_counterexample").format(
            candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
            invariants_json=json.dumps(self.invariants, ensure_ascii=False, indent=2),
        )
        raw    = self._call_llm(prompt)
        result = self._extract_json(raw)
        return result.get("counterexamples", [])

    # ── Step 2: Rebuttals ────────────────────────────────────────────────────

    def _generate_rebuttals(
        self,
        candidates: list[dict],
        counterexamples: list[dict],
    ) -> list[dict]:
        """
        From cffp.cue: Rebuttal kinds are refutation | scopenarrowing.
        CompositionFailure has NO rebuttal slot — skip those.
        """
        rebuttals: list[dict] = []

        for ce in counterexamples:
            if ce.get("assessment") not in ("violation_found",):
                continue

            candidate = next((c for c in candidates if c["id"] == ce.get("targetcandidate")), None)
            if not candidate:
                continue

            invariant = next(
                (inv for inv in self.invariants if inv["id"] == ce.get("violates")),
                {"id": ce.get("violates", "?"), "description": "", "class": ""},
            )

            prompt = get_prompt("cffp_phase3_rebuttal").format(
                candidate_json=json.dumps(candidate, ensure_ascii=False, indent=2),
                counterexample_json=json.dumps(ce, ensure_ascii=False, indent=2),
                invariant_json=json.dumps(invariant, ensure_ascii=False, indent=2),
            )
            raw      = self._call_llm(prompt)
            rebuttal = self._extract_json(raw)

            rebuttal.setdefault("candidateid", candidate["id"])
            rebuttal.setdefault("counterexampleid", ce.get("id", "?"))
            rebuttal.setdefault("kind", "scopenarrowing")
            rebuttal.setdefault("valid", True)
            rebuttal.setdefault("limitationdescription", "")

            # scopenarrowing is always valid by definition (cffp.cue)
            if rebuttal["kind"] == "scopenarrowing":
                rebuttal["valid"] = True

            rebuttals.append(rebuttal)

        return rebuttals

    # ── Step 3: Derive survivors (cffp.cue Derivation rules) ────────────────

    def _derive_survivors(
        self,
        candidates: list[dict],
        counterexamples: list[dict],
        rebuttals: list[dict],
    ) -> dict:
        """
        From cffp.cue:
          A candidate is eliminated if:
          (a) any counterexample targets it AND has no valid rebuttal, OR
          (b) any composition failure targets it (irrebuttable)
        """
        # Index rebuttals by (candidateid, counterexampleid)
        rebuttal_index: dict[tuple, dict] = {}
        for r in rebuttals:
            key = (r.get("candidateid", ""), r.get("counterexampleid", ""))
            rebuttal_index[key] = r

        eliminated:      list[dict] = []
        survivors:       list[dict] = []
        scope_narrowings: list[str] = []

        # Composition failure check (irrebuttable)
        composition_failures: dict[str, str] = {}
        for candidate in candidates:
            cid   = candidate["id"]
            claim = candidate.get("claim", "").lower()
            for canon in self.canonical_constructs:
                canon_lower = canon.lower()
                if f"not {canon_lower}" in claim or f"without {canon_lower}" in claim:
                    composition_failures[cid] = canon

        for candidate in candidates:
            cid = candidate["id"]

            # Composition failure → irrebuttable
            if cid in composition_failures:
                eliminated.append({
                    "candidateid": cid,
                    "reason":     "compositionfailure",
                    "sourceid":   f"CF-{cid}",
                    "violations": [f"CompositionFailure: conflicts with '{composition_failures[cid]}'"],
                })
                continue

            is_eliminated = False
            elimination_record: dict | None = None
            candidate_narrowings: list[str] = []

            my_ces = [
                ce for ce in counterexamples
                if ce.get("targetcandidate") == cid
                and ce.get("assessment") == "violation_found"
            ]

            for ce in my_ces:
                ce_id    = ce.get("id", "?")
                rebuttal = rebuttal_index.get((cid, ce_id))

                if rebuttal and rebuttal.get("valid", False):
                    if rebuttal["kind"] == "scopenarrowing":
                        lim = rebuttal.get("limitationdescription", "")
                        if lim:
                            candidate_narrowings.append(lim)
                            scope_narrowings.append(lim)
                    # refutation → CE dismissed, no trace
                else:
                    elimination_record = {
                        "candidateid": cid,
                        "reason":     "counterexampleunrebutted",
                        "sourceid":   ce_id,
                        "violations": [f"Counterexample({ce.get('violates','?')}): {ce.get('witness','')[:80]}"],
                    }
                    is_eliminated = True
                    break

            if is_eliminated and elimination_record:
                eliminated.append(elimination_record)
            else:
                survivors.append({
                    "candidateid":     cid,
                    "scopenarrowings": candidate_narrowings,
                })

        return {
            "survivors":                survivors,
            "eliminated":               eliminated,
            "eliminated_with_challenges": eliminated,
            "scope_narrowings":         scope_narrowings,
            "rebuttals":                rebuttals,
            "counterexamples_count":    len(counterexamples),
            "rebuttals_count":          len(rebuttals),
        }

    # ── LLM helpers ──────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        try:
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
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.ollama_url}.\n"
                "Start it with:  ollama serve"
            )

        if resp.status_code == 404:
            pull_tag = self.model if ":" in self.model else f"{self.model}:latest"
            raise RuntimeError(
                f"Ollama returned 404 for model '{self.model}'.\n"
                f"Pull it first:\n\n    ollama pull {pull_tag}\n"
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

    def make_phase3(self, model: str) -> "CFFPPhase3":
        """Factory method called by cycle_runner._build_phase3."""
        return CFFPPhase3(
            invariants=self.invariants,
            canonical_constructs=self.canonical_constructs,
            model=model,
            ollama_url=self.ollama_url,
        )