"""Main Attention ↔ CUE loop with adversarial Phase 3 + Obligation Gate."""
from __future__ import annotations
import os
from dial.residual_stream import ResidualStream, CycleStats
from dial.attention_phase import attention_phase
from dial.cue_phase import cue_phase

MAX_CYCLES = 5
MAX_REVISION_LOOPS = 2


def _is_live_mode(model: str) -> bool:
    try:
        import requests
        base = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not base.startswith("http"):
            base = f"http://{base}"
        r = requests.get(f"{base}/api/tags", timeout=3)
        if r.status_code == 200:
            tags = [m["name"] for m in r.json().get("models", [])]
            return any(model.split(":")[0] in t for t in tags)
    except Exception:
        pass
    return False


def _build_phase3(schema_validator, model: str):
    if hasattr(schema_validator, "make_phase3"):
        return schema_validator.make_phase3(model)
    from dial.hep_schema import HEPValidator, HEPPhase3
    from dial.cffp_schema import CFFPValidator, CFFPPhase3
    if isinstance(schema_validator, HEPValidator):
        return HEPPhase3(evidence=schema_validator.evidence, model=model)
    if isinstance(schema_validator, CFFPValidator):
        return CFFPPhase3(invariants=schema_validator.invariants, model=model,
                         canonical_constructs=schema_validator.canonical_constructs)
    return schema_validator


def run_dialectic_cycle(
    problem: dict,
    protocol: str,
    schema_validator,
    model: str = "llama3.1:8b",
    verbose: bool = True,
    force_offline: bool = False,
) -> ResidualStream:
    stream = ResidualStream()
    stream.stats = CycleStats()

    live = (not force_offline) and _is_live_mode(model)
    phase3 = _build_phase3(schema_validator, model) if live else schema_validator
    use_live = live

    for cycle in range(MAX_CYCLES):
        stream.cycle = cycle
        stream.stats.cycles_run += 1

        if verbose:
            sep = "─" * 60
            print(f"\n{sep}")
            print(f"  Cycle {cycle+1}/{MAX_CYCLES}  | "
                  f"constraints: {len(stream.active_constraints)}  "
                  f"llm_calls: {stream.stats.llm_calls}")
            print(sep)

        # Phase 2: Attention
        if verbose:
            print(f"  [2] Attention → {model} (LLM call #{stream.stats.llm_calls+1}) ...")
        stream = attention_phase(stream, problem, protocol, model)
        if verbose:
            print(f"  [2] Candidates: {len(stream.candidates)}")
            for c in stream.candidates:
                print(f"       • {c.get('id','?')}: {c.get('description','')[:70]}")

        # Phase 3: CUE + adversarial pressure
        if verbose:
            mode = "live LLM (assess→rebuttal→derive)" if use_live else "offline heuristic"
            print(f"\n  [3] CUE → {mode} ...")
        stream = cue_phase(stream, phase3, problem, use_live_phase3=use_live)

        if verbose:
            _print_phase3(stream)
            if stream.obligations:
                _print_obligations(stream)

        # No survivors → Revision Loop
        if not stream.survivors:
            if verbose:
                print(f"\n  ⟳  Revision Loop (cycle {cycle+1}) — no survivors")
            stream.candidates = []
            continue

        # x* selection
        best = _select_x_star(stream, cycle)
        if best is not None:
            stream.x_star = best
            if verbose:
                print(f"\n  ✓  x* found at cycle {cycle+1}!  "
                      f"(total LLM calls: {stream.stats.llm_calls})")
            break

        stream.history.append({
            "cycle": cycle, "survived": len(stream.survivors),
            "eliminated": len(stream.eliminated),
            "llm_calls": stream.stats.llm_calls,
        })

    return stream


def _select_x_star(stream: ResidualStream, cycle: int) -> dict | None:
    if not stream.survivors:
        return None
    if stream.obligations:
        if any(not o.get("satisfied", True) for o in stream.obligations):
            return None
    best = stream.survivors[0]
    cid = best["candidateid"]
    cand = next((c for c in stream.candidates if c.get("id") == cid), {})
    acknowledged = list(dict.fromkeys(
        best.get("scopenarrowings", []) + stream.scope_narrowings
    ))
    return {
        "id": cid,
        "description": cand.get("description", ""),
        "claim": cand.get("claim", ""),
        "proof_sketch": cand.get("proof_sketch", ""),
        "acknowledged_limitations": acknowledged,
        "cycles_to_convergence": cycle + 1,
        "llm_calls": stream.stats.llm_calls,
        "eliminated_count": len(stream.eliminated),
    }


def _print_phase3(stream: ResidualStream) -> None:
    print(f"\n  [3] Survivors: {len(stream.survivors)}  | "
          f"Eliminated total: {stream.stats.total_eliminated}  | "
          f"Rebuttals: {stream.stats.total_rebuttals}")
    for e in stream.eliminated[-10:]:
        print(f"       ⊥ {e.get('candidateid','?')}: {e.get('reason','')[:90]}")
    for s in stream.survivors:
        sn = s.get("scopenarrowings", [])
        print(f"       ✓ {s.get('candidateid','?')}  (scope_narrowings: {len(sn)})")
        for n in sn:
            print(f"            → \"{n[:80]}\"")


def _print_obligations(stream: ResidualStream) -> None:
    all_sat = all(o.get("satisfied", True) for o in stream.obligations)
    print(f"\n  [5] Obligation Gate → "
          f"{'allsatisfied=True ✓' if all_sat else 'allsatisfied=False ✗ → looping'}")
    for ob in stream.obligations:
        sym = "✓" if ob.get("satisfied", True) else "✗"
        print(f"       {sym} {ob.get('candidateid','?')}: "
              f"{ob.get('property','?')} — {ob.get('argument','')[:60]}")