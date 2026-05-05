"""CFFP Phase 3 — Counterexample-driven adversarial pressure."""
from __future__ import annotations
import json
from dial.attention_phase import call_ollama, extract_json_object
from dial.prompts import get_prompt


class CFFPPhase3:
    def __init__(self, invariants: list[dict], model: str, ollama_url: str = "",
                 canonical_constructs: list[str] | None = None):
        self.invariants = invariants
        self.model = model
        self.canonical_constructs = canonical_constructs or []

    def run(self, candidates: list[dict], stream) -> dict:
        all_ces, all_rebuttals = [], []
        for cand in candidates:
            ces = self._generate_counterexamples(cand)
            stream.stats.llm_calls += 1
            all_ces.extend(ces)
            violations = [ce for ce in ces if ce.get("assessment") == "violation_found"]
            if violations:
                rbs = self._generate_rebuttals(cand, violations, stream)
                all_rebuttals.extend(rbs)
        stream.stats.total_challenges += len(
            [ce for ce in all_ces if ce.get("assessment") == "violation_found"]
        )
        return self._derive_survivors(candidates, all_ces, all_rebuttals, stream)

    def _generate_counterexamples(self, candidate: dict) -> list[dict]:
        if not self.invariants:
            return []
        prompt = get_prompt("cffp_phase3_counterexample").format(
            candidate_json=json.dumps(candidate, ensure_ascii=False, indent=2),
            invariants_json=json.dumps(self.invariants, ensure_ascii=False, indent=2),
        )
        raw = call_ollama(prompt, self.model)
        return extract_json_object(raw).get("counterexamples", [])

    def _generate_rebuttals(self, candidate: dict, violations: list[dict], stream) -> list[dict]:
        rebuttals = []
        for ce in violations:
            prompt = get_prompt("cffp_phase3_rebuttal").format(
                candidate_id=candidate["id"],
                candidate_json=json.dumps(candidate, ensure_ascii=False, indent=2),
                ce_id=ce.get("id","CE?"),
                invariant_id=ce.get("violates","?"),
                witness=ce.get("witness",""),
            )
            raw = call_ollama(prompt, self.model)
            stream.stats.llm_calls += 1
            obj = extract_json_object(raw)
            if obj:
                rebuttals.append(obj)
            stream.stats.total_rebuttals += 1
        return rebuttals

    def _derive_survivors(self, candidates, counterexamples, rebuttals, stream):
        rebuttal_map = {(r.get("candidateid",""), r.get("ceid","")): r for r in rebuttals}
        survivors, eliminated, scope_narrowings, elim_challenges = [], [], [], []

        for cand in candidates:
            cid = cand["id"]
            elim_reason = elim_source = None
            cand_narrowings = []
            surviving = True

            violations = [ce for ce in counterexamples
                          if ce.get("targetcandidate") == cid
                          and ce.get("assessment") == "violation_found"]

            for ce in violations:
                ce_id = ce.get("id","?")
                rebuttal = rebuttal_map.get((cid, ce_id))
                if rebuttal and rebuttal.get("valid"):
                    if rebuttal.get("kind") == "scopenarrowing":
                        cand_narrowings.append(
                            rebuttal.get("limitationdescription") or ce.get("witness","")
                        )
                else:
                    surviving = False
                    rb_note = rebuttal.get("argument","") if rebuttal else "no rebuttal"
                    elim_reason = (
                        f"counterexample_unrebutted ({ce_id} violates {ce.get('violates','?')}): "
                        f"{ce.get('witness','')} [rebuttal: {rb_note}]"
                    )
                    elim_source = ce_id
                    break

            if surviving:
                survivors.append({"candidateid": cid, "scopenarrowings": cand_narrowings})
                scope_narrowings.extend(cand_narrowings)
            else:
                eliminated.append({"candidateid": cid, "reason": elim_reason, "sourceid": elim_source})
                elim_challenges.append({
                    "candidateid": cid, "reason": elim_reason, "challenge_ce": elim_source,
                    "counterexamples": [ce for ce in counterexamples if ce.get("targetcandidate") == cid],
                })
                stream.stats.total_eliminated += 1

        return {"survivors": survivors, "eliminated": eliminated,
                "scope_narrowings": scope_narrowings, "counterexamples": counterexamples,
                "eliminated_with_challenges": elim_challenges}


class CFFPValidator:
    """Offline unit-test shim — no LLM."""
    def __init__(self, invariants: list[dict], canonical_constructs: list[str] | None = None):
        self.invariants = invariants
        self.canonical_constructs = canonical_constructs or []

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        claim = (candidate.get("claim","") + " " + candidate.get("proof_sketch","")).lower()
        violations = []
        keywords_map = {
            "termination": ["terminat","halt","finish","complet","loop","end"],
            "determinism":  ["determin","consistent","identical","reproducib","order"],
        }
        for inv in self.invariants:
            inv_class = inv.get("class","general").lower()
            inv_id = inv.get("id","?")
            required = keywords_map.get(inv_class, [])
            if required and not any(kw in claim for kw in required):
                violations.append(
                    f"invariant {inv_id} ({inv_class}): "
                    f"proof_sketch does not address '{inv.get('description','')[:60]}'"
                )
        if violations:
            return {"valid": False, "reason": violations[0], "violations": violations}
        return {"valid": True, "scope_narrowings": []}

    def make_phase3(self, model: str) -> CFFPPhase3:
        return CFFPPhase3(invariants=self.invariants, model=model,
                         canonical_constructs=self.canonical_constructs)