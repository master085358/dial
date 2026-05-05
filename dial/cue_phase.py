"""
CUE Phase (offline fallback).

v3: live Phase3 is invoked directly from cycle_runner.py via phase3.run().
    cue_phase() remains here as the offline fallback for schemas that do NOT
    implement make_phase3() — or when Ollama is unavailable.
"""
from __future__ import annotations

from dial.residual_stream import ResidualStream


def cue_phase(
    stream: ResidualStream,
    schema_validator,
    problem: dict,
) -> ResidualStream:
    """
    Offline CUE phase.

    For each candidate, runs schema_validator.validate() which implements the
    CUE Operator in pure Python (direct contradiction, evidence gap,
    prior elimination, structural requirements).

    Updates stream.survivors, stream.eliminated, stream.active_constraints.
    """
    survivors:  list[dict] = []
    eliminated: list[dict] = []

    for candidate in stream.candidates:
        try:
            result = schema_validator.validate(candidate, problem, stream)
        except Exception as exc:
            # Validation error → treat as non-fatal; candidate survives with pressure
            stream.active_constraints.append(
                f"VALIDATION_ERROR {candidate.get('id','?')}: {exc}"
            )
            survivors.append({"candidateid": candidate["id"], "scopenarrowings": []})
            continue

        if result.get("valid", False):
            narrowings = result.get("scope_narrowings", [])
            stream.scope_narrowings.extend(narrowings)
            survivors.append({
                "candidateid":     candidate["id"],
                "scopenarrowings": narrowings,
            })
        else:
            reason = result.get("reason", "unknown_violation")
            eliminated.append({
                "candidateid": candidate["id"],
                "reason":      reason,
                "sourceid":    result.get("challenge_id", "?"),
                "violations":  result.get("violations", [reason]),
            })
            stream.active_constraints.append(
                f"ELIMINATED {candidate['id']}: {reason[:120]}. "
                "New candidates MUST NOT repeat this claim."
            )

    stream.survivors  = survivors
    stream.eliminated = list({e["candidateid"]: e for e in (stream.eliminated + eliminated)}.values())
    stream.stats.total_eliminated = len(stream.eliminated)

    return stream