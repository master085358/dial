from __future__ import annotations

from dial.residual_stream import ResidualStream


def cue_phase(
    stream: ResidualStream,
    schema_validator,
    problem: dict,
) -> ResidualStream:
    """Phase B — Python CUE compiler (offline schema validation)."""
    new_survivors: list[dict] = []
    new_eliminated: list[dict] = []
    new_elim_challenges: list[dict] = []
    new_scope_narrowings: list[str] = []

    for candidate in stream.candidates:
        result = schema_validator.validate(candidate, problem, stream)

        if result["valid"]:
            survivor = {
                "candidateid": candidate["id"],
                "scopenarrowings": result.get("scope_narrowings", []),
            }
            new_survivors.append(survivor)
            new_scope_narrowings.extend(result.get("scope_narrowings", []))
        else:
            elimination = {
                "candidateid": candidate["id"],
                "reason": result["reason"],
                "sourceid": result.get("challenge_id", "auto"),
                "violations": result.get("violations", []),
            }
            new_eliminated.append(elimination)
            new_elim_challenges.append({                          # ← added
                "candidateid": candidate["id"],
                "reason": result["reason"],
                "violations": result.get("violations", []),
            })
            for violation in result.get("violations", []):
                stream.active_constraints.append(
                    f"ELIMINATED {candidate['id']}: {violation}. "
                    "New candidates MUST NOT repeat this claim."
                )

    stream.survivors = new_survivors
    stream.eliminated.extend(new_eliminated)
    stream.eliminated_with_challenges.extend(new_elim_challenges)  # ← added
    stream.scope_narrowings.extend(new_scope_narrowings)

    if new_survivors:
        stream.obligations = _build_obligations(new_survivors, problem)

    return stream


def _build_obligations(survivors: list[dict], problem: dict) -> list[dict]:
    """Placeholder obligations — replaced by live LLM gate in cycle_runner."""
    return [
        {
            "candidateid": s["candidateid"],
            "property": "candidate_is_non_empty",
            "argument": f"Survivor {s['candidateid']} has non-empty description",
            "satisfied": True,
        }
        for s in survivors
    ]