from dial.residual_stream import ResidualStream
from dial.attention_phase import attention_phase
from dial.cue_phase import cue_phase

MAX_CYCLES = 5
MAX_REVISION_LOOPS = 2


def run_dialectic_cycle(
    problem: dict,
    protocol: str,
    schema_validator,
    model: str = "llama3.1:8b",
    verbose: bool = True,
) -> ResidualStream:
    """
    Main Attention <-> CUE loop.

    Phase 2  — candidate generation (Attention)
    Phase 3  — pressure / derivation  (CUE)
    Phase 3b — revision loop on zero survivors
    Phase 5  — obligation gate
    """
    stream = ResidualStream()
    revision_count = 0

    for cycle in range(MAX_CYCLES):
        stream.cycle = cycle
        if verbose:
            _banner(f"Cycle {cycle + 1}/{MAX_CYCLES}  "
                    f"| constraints accumulated: {len(stream.active_constraints)}")

        # ── Phase A: Attention ──────────────────────────────────────────────
        if verbose:
            print(f"  [A] Attention → {model} ...")
        stream = attention_phase(stream, problem, protocol, model)
        if verbose:
            print(f"  [A] Candidates generated: {len(stream.candidates)}")
            for c in stream.candidates:
                print(f"       • {c['id']}: {c.get('description', '')[:80]}")

        # ── Phase B: CUE ────────────────────────────────────────────────────
        if verbose:
            print(f"  [B] CUE  → schema: {protocol.upper()}")
        stream = cue_phase(stream, schema_validator, problem)
        if verbose:
            print(f"  [B] Survivors: {len(stream.survivors)}  "
                  f"| Eliminated this cycle: {len([e for e in stream.eliminated if True])}")
            for e in stream.eliminated[-3:]:
                print(f"       ⊥ {e['candidateid']}: {e['reason'][:70]}")
            for s in stream.survivors:
                print(f"       ✓ {s['candidateid']}  "
                      f"(scope_narrowings: {len(s.get('scopenarrowings', []))})")

        stream.snapshot()

        # ── Phase 3b: Revision Loop ─────────────────────────────────────────
        if stream.has_zero_survivors():
            revision_count += 1
            if revision_count > MAX_REVISION_LOOPS:
                if verbose:
                    print("  ⚠  Revision loop limit reached — open outcome.")
                break
            diagnosis = _diagnose_zero_survivors(stream)
            if verbose:
                _banner(f"Revision Loop #{revision_count}: {diagnosis}", char="·")
            stream.eliminated = []
            stream.candidates = []
            continue

        # ── Obligation Gate ─────────────────────────────────────────────────
        if stream.has_converged():
            best = stream.survivors[0]
            for c in stream.candidates:
                if c["id"] == best["candidateid"]:
                    stream.x_star = {
                        **c,
                        "scope_narrowings": best.get("scopenarrowings", []),
                        "cycles_to_convergence": cycle + 1,
                        "acknowledged_limitations": stream.scope_narrowings,
                    }
                    break
            if verbose:
                print(f"\n  ✓  x* found at cycle {cycle + 1}!")
            break

    return stream


def _diagnose_zero_survivors(stream: ResidualStream) -> str:
    if len(stream.eliminated) > 3:
        return "candidatestooweak — all candidates eliminated; generate stronger"
    if len(stream.active_constraints) > 10:
        return "invariantstoostrong — too many constraints; consider relaxing"
    return "constructincoherent — problem may need reformulation"


def _banner(msg: str, char: str = "─", width: int = 60) -> None:
    line = char * width
    print(f"\n{line}\n  {msg}\n{line}")
