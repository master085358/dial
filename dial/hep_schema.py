"""
HEP Phase 3 — Evidence-driven adversarial pressure.
  Step 1: _generate_assessments()  LLM → EvidenceAssessment per (H × E)
  Step 2: _generate_rebuttals()    LLM → rebuttal per strong inconsistency
  Step 3: _derive_survivors()      pure Python derivation
"""
from __future__ import annotations
import json
from dial.attention_phase import call_ollama, extract_json_object
from dial.prompts import get_prompt


class HEPPhase3:
    def __init__(self, evidence: list[str], model: str, ollama_url: str = ""):
        self.evidence = evidence
        self.model = model

    def run(self, candidates: list[dict], stream) -> dict:
        ev_labeled = [{"id": f"E{i+1}", "text": e} for i, e in enumerate(self.evidence)]
        assessments = self._generate_assessments(candidates, ev_labeled)
        stream.evidence_assessments.extend(assessments)
        stream.stats.llm_calls += 1
        rebuttals = self._generate_rebuttals(candidates, assessments, ev_labeled, stream)
        return self._derive_survivors(candidates, assessments, rebuttals, stream)

    def _generate_assessments(self, candidates, ev_labeled):
        if not ev_labeled:
            return []
        prompt = get_prompt("hep_phase3_assess").format(
            candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
            evidence_json=json.dumps(ev_labeled, ensure_ascii=False, indent=2),
        )
        raw = call_ollama(prompt, self.model)
        return extract_json_object(raw).get("assessments", [])

    def _generate_rebuttals(self, candidates, assessments, ev_labeled, stream):
        rebuttals = []
        ev_map = {e["id"]: e["text"] for e in ev_labeled}
        cand_map = {c["id"]: c for c in candidates}
        for a in assessments:
            if a.get("consistency") == "inconsistent" and a.get("weight") == "strong":
                cid, eid = a["hypothesisid"], a["evidenceid"]
                prompt = get_prompt("hep_phase3_rebuttal").format(
                    hypothesis_id=cid,
                    hypothesis_json=json.dumps(cand_map.get(cid, {}), ensure_ascii=False, indent=2),
                    evidence_id=eid,
                    evidence_description=ev_map.get(eid, eid),
                    assessment_argument=a.get("argument", ""),
                )
                raw = call_ollama(prompt, self.model)
                stream.stats.llm_calls += 1
                obj = extract_json_object(raw)
                if obj:
                    rebuttals.append(obj)
                stream.stats.total_rebuttals += 1
        stream.stats.total_challenges += len(rebuttals)
        return rebuttals

    def _derive_survivors(self, candidates, assessments, rebuttals, stream):
        rebuttal_map = {(r.get("hypothesisid",""), r.get("evidenceid","")): r for r in rebuttals}
        weak_pressure = {}
        for a in assessments:
            if a.get("consistency") == "inconsistent" and a.get("weight") == "weak":
                cid = a["hypothesisid"]
                weak_pressure[cid] = weak_pressure.get(cid, 0) + 1

        survivors, eliminated, scope_narrowings, elim_challenges = [], [], [], []

        for cand in candidates:
            cid = cand["id"]
            elim_reason = elim_source = None
            cand_narrowings = []
            surviving = True

            for a in assessments:
                if a.get("hypothesisid") != cid or a.get("consistency") != "inconsistent":
                    continue
                eid, weight, arg = a.get("evidenceid","?"), a.get("weight","weak"), a.get("argument","")

                if weight == "decisive":
                    surviving = False
                    elim_reason = f"decisive_inconsistency ({eid}): {arg}"
                    elim_source = eid
                    break
                if weight == "strong":
                    rebuttal = rebuttal_map.get((cid, eid))
                    if rebuttal and rebuttal.get("valid"):
                        if rebuttal.get("kind") == "scopenarrowing":
                            cand_narrowings.append(
                                rebuttal.get("limitationdescription") or arg
                            )
                    else:
                        surviving = False
                        rb_note = rebuttal.get("argument","") if rebuttal else "no rebuttal"
                        elim_reason = (
                            f"strong_inconsistency_unrebutted ({eid}): {arg} "
                            f"[rebuttal: {rb_note}]"
                        )
                        elim_source = eid
                        break

            if surviving and weak_pressure.get(cid, 0) >= 3:
                surviving = False
                elim_reason = f"accumulated_weak_pressure: {weak_pressure[cid]} weak inconsistencies"
                elim_source = "accumulated"

            if surviving:
                survivors.append({"candidateid": cid, "scopenarrowings": cand_narrowings})
                scope_narrowings.extend(cand_narrowings)
            else:
                eliminated.append({"candidateid": cid, "reason": elim_reason, "sourceid": elim_source})
                elim_challenges.append({
                    "candidateid": cid, "reason": elim_reason, "challenge_evidence": elim_source,
                    "assessments": [a for a in assessments if a.get("hypothesisid") == cid],
                })
                stream.stats.total_eliminated += 1

        return {"survivors": survivors, "eliminated": eliminated,
                "scope_narrowings": scope_narrowings, "assessments": assessments,
                "eliminated_with_challenges": elim_challenges}


class HEPValidator:
    """Offline unit-test shim — no LLM."""
    def __init__(self, evidence: list[str]):
        self.evidence = evidence

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        claim = (candidate.get("claim","") + " " + candidate.get("description","")).lower()
        eliminated = stream.eliminated if stream else []

        for prev in eliminated:
            prev_words = set(prev.get("reason","").lower().split())
            if len(prev_words & set(claim.split())) > 4:
                return {"valid": False,
                        "reason": f"prior_elimination: similar to {prev['candidateid']}",
                        "violations": [f"similar to eliminated {prev['candidateid']}"]}

        if self.evidence:
            ev_text = " ".join(self.evidence).lower()
            claim_tokens = {w for w in claim.split() if len(w) > 4}
            ev_tokens = {w for w in ev_text.split() if len(w) > 4}
            if claim_tokens and not claim_tokens & ev_tokens:
                return {"valid": False, "reason": "evidence_gap",
                        "violations": ["claim does not reference any evidence tokens"]}

        for ev in self.evidence:
            ev_l = ev.lower()
            for neg in ["not ", "no ", "never ", "unchanged ", "unaffected "]:
                if neg in ev_l:
                    topic = ev_l.replace(neg,"").strip()[:30]
                    if topic in claim:
                        return {"valid": False,
                                "reason": f"direct_contradiction: contradicts '{ev[:60]}'",
                                "violations": [f"contradicts: {ev[:80]}"]}

        return {"valid": True, "scope_narrowings": []}

    def make_phase3(self, model: str) -> HEPPhase3:
        return HEPPhase3(evidence=self.evidence, model=model)