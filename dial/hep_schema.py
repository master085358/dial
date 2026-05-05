"""
HEP Validator — Hypothesis Elimination Protocol (offline shim for unit tests).

Three pressure types (from hep.cue Phase 3):
  DirectContradiction   — hypothesis directly contradicts documented evidence
  MissingCausalAccount  — empty/blank proof_sketch (structural requirement)
  EvidenceGap           — hypothesis explains none of the provided evidence
  PriorElimination      — semantically similar to an already-eliminated candidate
"""
from __future__ import annotations


class HEPValidator:
    def __init__(self, evidence: list[str]):
        self.evidence = evidence

    def validate(self, candidate: dict, problem: dict, stream) -> dict:
        violations: list[str] = []
        scope_narrowings: list[str] = []

        claim = candidate.get("claim", "").lower()
        description = candidate.get("description", "").lower()
        proof = candidate.get("proof_sketch", "")
        text = claim + " " + description

        # 1. MissingCausalAccount — checked FIRST so it overrides everything else
        if not proof or not proof.strip():
            return {
                "valid": False,
                "reason": "MissingCausalAccount: candidate lacks proof_sketch (required by HEP Phase 2)",
                "violations": ["MissingCausalAccount: proof_sketch is empty"],
                "challenge_id": f"CE-{candidate['id']}-structural",
            }

        # 2. DirectContradiction
        for ev in self.evidence:
            if _contradicts(claim, ev.lower()):
                violations.append(
                    f"DirectContradiction: '{candidate['id']}' "
                    f"contradicts evidence: '{ev[:60]}'"
                )

        # 3. PriorElimination
        for eliminated in (stream.eliminated if stream else []):
            if _semantically_similar(
                candidate.get("description", ""),
                eliminated.get("reason", ""),
            ):
                violations.append(
                    f"PriorElimination: semantically similar to already-eliminated "
                    f"'{eliminated['candidateid']}'"
                )
                break

        # 4. EvidenceGap — scope narrowing only (not hard violation), only when no other violation
        if not violations and self.evidence:
            explains_any = any(_explains(text, ev.lower()) for ev in self.evidence)
            if not explains_any:
                scope_narrowings.append(
                    f"Hypothesis {candidate['id']} explains none of the provided "
                    "evidence — scope limited to unexplored explanations"
                )

        if violations:
            return {
                "valid": False,
                "reason": violations[0],
                "violations": violations,
                "challenge_id": f"CE-{candidate['id']}-{getattr(stream, 'cycle', 0)}",
            }

        return {"valid": True, "scope_narrowings": scope_narrowings}

    def make_phase3(self, model: str):
        from dial.hep_schema import HEPPhase3
        return HEPPhase3(evidence=self.evidence, model=model)


# ── Lexical helpers ─────────────────────────────────────────────────────────────

def _contradicts(claim: str, evidence: str) -> bool:
    negations = ["not ", "never ", "no ", "cannot ", "doesn't ", "isn't ", "нет "]
    for neg in negations:
        if neg in claim:
            base = evidence.replace(neg, "").strip()
            if base and base in claim:
                return True
    return False


def _explains(text: str, evidence: str) -> bool:
    stop = {"the", "a", "is", "was", "in", "of", "and", "to", "for", "that", "it"}
    ev_words = set(evidence.split()) - stop
    text_words = set(text.split())
    return len(ev_words & text_words) >= 2


def _semantically_similar(text1: str, text2: str) -> bool:
    w1 = set(text1.lower().split())
    w2 = set(text2.lower().split())
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) > 0.6


# ── Live Phase 3 (requires Ollama) ──────────────────────────────────────────────

class HEPPhase3:
    def __init__(self, evidence: list[str], model: str, ollama_url: str = ""):
        self.evidence = evidence
        self.model = model

    def run(self, candidates: list[dict], stream) -> dict:
        import json
        from dial.attention_phase import call_ollama, extract_json_object
        from dial.prompts import get_prompt

        ev_labeled = [{"id": f"E{i+1}", "text": e} for i, e in enumerate(self.evidence)]
        assessments = self._generate_assessments(candidates, ev_labeled, stream)
        stream.evidence_assessments.extend(assessments)
        stream.stats.llm_calls += 1
        rebuttals = self._generate_rebuttals(candidates, assessments, ev_labeled, stream)
        return self._derive_survivors(candidates, assessments, rebuttals, stream)

    def _generate_assessments(self, candidates, ev_labeled, stream):
        import json
        from dial.attention_phase import call_ollama, extract_json_object
        from dial.prompts import get_prompt

        if not ev_labeled:
            return []
        prompt = get_prompt("hep_phase3_assess").format(
            candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
            evidence_json=json.dumps(ev_labeled, ensure_ascii=False, indent=2),
        )
        raw = call_ollama(prompt, self.model)
        return extract_json_object(raw).get("assessments", [])

    def _generate_rebuttals(self, candidates, assessments, ev_labeled, stream):
        import json
        from dial.attention_phase import call_ollama, extract_json_object
        from dial.prompts import get_prompt

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
        weak_pressure: dict[str, int] = {}
        for a in assessments:
            if a.get("consistency") == "inconsistent" and a.get("weight") == "weak":
                cid = a["hypothesisid"]
                weak_pressure[cid] = weak_pressure.get(cid, 0) + 1

        survivors, eliminated, scope_narrowings, elim_challenges = [], [], [], []
        for cand in candidates:
            cid = cand["id"]
            elim_reason = elim_source = None
            cand_narrowings: list[str] = []
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
                            cand_narrowings.append(rebuttal.get("limitationdescription") or arg)
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
                    "candidateid": cid, "reason": elim_reason,
                    "challenge_evidence": elim_source,
                    "assessments": [a for a in assessments if a.get("hypothesisid") == cid],
                })
                stream.stats.total_eliminated += 1

        return {
            "survivors": survivors, "eliminated": eliminated,
            "scope_narrowings": scope_narrowings, "assessments": assessments,
            "eliminated_with_challenges": elim_challenges,
        }