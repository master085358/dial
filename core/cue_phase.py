from .residual_stream import ResidualStream


def cue_phase(
    stream: ResidualStream,
    schema_validator,
    problem: dict,
) -> ResidualStream:
    """Phase B — Python CUE compiler."""
    new_survivors = []
    new_eliminated = []
    new_scope_narrowings = []

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
            # Violations become forward constraints for Attention
            for violation in result.get("violations", []):
                stream.active_constraints.append(
                    f"ELIMINATED {candidate['id']}: {violation}. "
                    "New candidates MUST NOT repeat this claim."
                )

    stream.survivors = new_survivors
    stream.eliminated.extend(new_eliminated)
    stream.scope_narrowings.extend(new_scope_narrowings)

    if new_survivors:
        stream.obligations = _build_obligations(new_survivors, problem)

    return stream


def _build_obligations(survivors: list[dict], problem: dict) -> list[dict]:
    """Simplified Obligation Gate for MVP (v2 = full Phase 5 CFFP)."""
    return [
        {
            "candidateid": s["candidateid"],
            "property": "candidate_is_non_empty",
            "argument": f"Survivor {s['candidateid']} has non-empty description",
            "satisfied": True,
        }
        for s in survivors
    ]
