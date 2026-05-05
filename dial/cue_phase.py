"""CUE Phase — delegates Phase 3 to HEPPhase3/CFFPPhase3, runs Obligation Gate."""
from __future__ import annotations
import json
from dial.residual_stream import ResidualStream
from dial.attention_phase import call_ollama, extract_json_object
from dial.prompts import get_prompt


def cue_phase(
    stream: ResidualStream,
    schema_phase3,
    problem: dict,
    use_live_phase3: bool = True,
) -> ResidualStream:
    if use_live_phase3 and hasattr(schema_phase3, "run"):
        result = schema_phase3.run(stream.candidates, stream)
    else:
        result = _offline_validate(stream.candidates, schema_phase3, problem, stream)

    stream.survivors = result["survivors"]
    stream.eliminated.extend(result["eliminated"])
    stream.scope_narrowings.extend(result.get("scope_narrowings", []))
    stream.eliminated_with_challenges.extend(result.get("eliminated_with_challenges", []))

    for e in result["eliminated"]:
        stream.active_constraints.append(
            f"ELIMINATED {e['candidateid']}: {e['reason']}. "
            f"Source challenge: {e.get('sourceid','unknown')}. "
            "Do NOT generate candidates with similar claims."
        )

    if stream.survivors and use_live_phase3 and hasattr(schema_phase3, "model"):
        ob_result = _run_obligation_gate(
            stream.survivors, stream.candidates, problem, schema_phase3.model
        )
        stream.obligations = ob_result.get("obligations", [])
        stream.stats.llm_calls += 1
        if not ob_result.get("allsatisfied", True):
            stream.survivors = []
            for ob in stream.obligations:
                if not ob.get("satisfied", True):
                    stream.active_constraints.append(
                        f"OBLIGATION_FAILED {ob.get('candidateid','?')}: "
                        f"{ob.get('property','?')} — {ob.get('blocker','')}. "
                        "Next candidate must satisfy this obligation."
                    )
    elif stream.survivors:
        stream.obligations = [
            {"candidateid": s["candidateid"], "property": "non_empty",
             "argument": "offline mode", "satisfied": True}
            for s in stream.survivors
        ]

    return stream


def _run_obligation_gate(survivors, candidates, problem, model) -> dict:
    results: dict = {"obligations": [], "allsatisfied": True}
    for survivor in survivors:
        cid = survivor["candidateid"]
        cand = next((c for c in candidates if c["id"] == cid), {})
        merged = {**cand, **survivor}
        prompt = get_prompt("obligation_gate").format(
            survivor_json=json.dumps(merged, ensure_ascii=False, indent=2),
            candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
            problem_json=json.dumps(problem, ensure_ascii=False, indent=2),
        )
        raw = call_ollama(prompt, model)
        obj = extract_json_object(raw)
        obligations = obj.get("obligations", [])
        all_sat = obj.get("allsatisfied",
                          all(o.get("satisfied", True) for o in obligations))
        results["obligations"].extend(obligations)
        if not all_sat:
            results["allsatisfied"] = False
    return results


def _offline_validate(candidates, schema_validator, problem, stream) -> dict:
    survivors, eliminated, scope_narrowings = [], [], []
    for cand in candidates:
        res = schema_validator.validate(cand, problem, stream)
        if res["valid"]:
            survivors.append({"candidateid": cand["id"],
                               "scopenarrowings": res.get("scope_narrowings", [])})
            scope_narrowings.extend(res.get("scope_narrowings", []))
        else:
            eliminated.append({"candidateid": cand["id"], "reason": res["reason"],
                                "sourceid": "auto", "violations": res.get("violations", [])})
            for v in res.get("violations", []):
                stream.active_constraints.append(
                    f"ELIMINATED {cand['id']}: {v}. New candidates MUST NOT repeat this."
                )
    return {"survivors": survivors, "eliminated": eliminated,
            "scope_narrowings": scope_narrowings, "eliminated_with_challenges": []}