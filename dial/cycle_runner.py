"""
Dialectics MVP — main Attention ↔ CUE loop.

Phase layout (from dialectics.cue):
  [2] Attention  — LLM generates candidates
  [3] CUE        — offline or live adversarial pressure
  [3b] Revision  — fired when zero survivors
  [5] Gate       — live LLM obligation check; sets x* on pass
"""
from __future__ import annotations

import json

from dial.residual_stream import ResidualStream
from dial.attention_phase import attention_phase, call_ollama, extract_json_object
from dial.cue_phase import cue_phase
from dial.prompts import get_prompt

MAX_CYCLES = 5
MAX_REVISION_LOOPS = 3


# ── Phase3 factory ─────────────────────────────────────────────────────────────

def _build_phase3(schema_validator, model: str):
    """
    Return a live Phase3 runner when available, else fall back to the offline
    offline schema_validator itself (which is always safe for unit tests).
    """
    try:
        return schema_validator.make_phase3(model)
    except (AttributeError, ImportError, Exception):
        return None   # signals: use offline cue_phase only


# ── Obligation Gate (live LLM) ──────────────────────────────────────────────────

def _obligation_gate(stream: ResidualStream, problem: dict, model: str) -> bool:
    """
    Ask the LLM whether every surviving candidate satisfies all obligations.
    Returns True only when ALL obligations are confirmed satisfied.
    On any failure or parse error → returns False (safe-fail).
    """
    if not stream.survivors:
        return False

    context = {
        "survivors": stream.survivors,
        "problem": problem,
        "scope_narrowings": stream.scope_narrowings,
        "instruction": (
            "For each surviving candidate, check ALL of these obligations:\n"
            "  - causal_sufficiency: the claim fully explains the phenomenon\n"
            "  - predictions_confirmed: the proof_sketch is consistent with ALL evidence\n"
            "  - scope_not_trivial: the claim is not a tautology or empty statement\n"
            "  - no_background_conflict: the claim does not contradict known background facts\n\n"
            "Return a JSON object with key 'obligations' (array). "
            "Each item: {candidateid, property, argument, satisfied (bool)}.\n"
            "Return ONLY the JSON, no commentary."
        ),
    }

    prompt_template = get_prompt("obligation_gate")
    prompt = prompt_template.format(context=json.dumps(context, ensure_ascii=False, indent=2))

    try:
        raw = call_ollama(prompt, model)
        obj = extract_json_object(raw)
        obligations = obj.get("obligations", [])
    except Exception:
        return False

    if not obligations:
        return False

    stream.obligations = obligations

    # Log obligations in verbose mode
    for ob in obligations:
        sat = ob.get("satisfied", False)
        sym = "✓" if sat else "✗"
        prop = ob.get("property", "?")
        arg = ob.get("argument", "")[:60]
        print(f"       {sym} ?: {prop} — {arg}")

    return all(ob.get("satisfied", False) for ob in obligations)


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_dialectic_cycle(
    problem: dict,
    protocol: str,
    schema_validator,
    model: str = "llama3.1:8b",
    verbose: bool = True,
) -> ResidualStream:
    stream = ResidualStream()
    revision_count = 0
    phase3 = _build_phase3(schema_validator, model)
    live = phase3 is not None

    for cycle in range(MAX_CYCLES):
        stream.cycle = cycle
        if verbose:
            _banner(
                f"Cycle {cycle + 1}/{MAX_CYCLES}"
                f"  | constraints: {len(stream.active_constraints)}"
                f"  llm_calls: {stream.stats.llm_calls}"
            )

        # ── [2] Attention ───────────────────────────────────────────────────
        if verbose:
            print(f"  [2] Attention → {model} (LLM call #{stream.stats.llm_calls + 1}) ...")
        stream = attention_phase(stream, problem, protocol, model)
        stream.stats.llm_calls += 1

        if not stream.candidates:
            # JSON parse totally failed — force revision
            if verbose:
                print("  [2] No parseable candidates — forcing revision loop")
            revision_count += 1
            if revision_count > MAX_REVISION_LOOPS:
                break
            stream.eliminated = []
            stream.candidates = []
            continue

        if verbose:
            print(f"  [2] Candidates: {len(stream.candidates)}")
            for c in stream.candidates:
                print(f"       • {c['id']}: {c.get('description','')[:80]}")

        # ── [3] CUE ─────────────────────────────────────────────────────────
        if live:
            if verbose:
                print(f"  [3] CUE → live LLM (assess→rebuttal→derive) ...")
            phase3_result = phase3.run(stream.candidates, stream)
            stream.stats.llm_calls += getattr(stream.stats, "_phase3_calls", 0)
            _apply_phase3_result(stream, stream.candidates, phase3_result)
        else:
            if verbose:
                print(f"  [3] CUE → offline schema ({protocol.upper()})")
            stream = cue_phase(stream, schema_validator, problem)

        if verbose:
            print(
                f"\n  [3] Survivors: {len(stream.survivors)}"
                f"  | Eliminated total: {len(stream.eliminated)}"
                f"  | Rebuttals: {stream.stats.total_rebuttals}"
            )
            for e in stream.eliminated:
                print(f"       ⊥ {e['candidateid']}: {e['reason'][:90]}")
            for s in stream.survivors:
                print(f"       ✓ {s['candidateid']}  (scope_narrowings: {len(s.get('scopenarrowings', []))})")

        stream.snapshot()

        # ── [3b] Revision Loop ──────────────────────────────────────────────
        if stream.has_zero_survivors():
            revision_count += 1
            if verbose:
                _banner(f"Revision Loop (cycle {cycle + 1}) — no survivors", char="·")
            if revision_count > MAX_REVISION_LOOPS:
                if verbose:
                    print("  ⚠  Revision loop limit reached — open outcome.")
                break
            stream.candidates = []
            continue

        # ── [5] Obligation Gate ─────────────────────────────────────────────
        if verbose:
            print()
        all_satisfied = _obligation_gate(stream, problem, model)
        stream.stats.llm_calls += 1

        if verbose:
            status = "allsatisfied=True ✓" if all_satisfied else "allsatisfied=False ✗ → looping"
            print(f"\n  [5] Obligation Gate → {status}")

        if all_satisfied:
            best = stream.survivors[0]
            for c in stream.candidates:
                if c["id"] == best["candidateid"]:
                    stream.x_star = {
                        **c,
                        "scope_narrowings": best.get("scopenarrowings", []),
                        "cycles_to_convergence": cycle + 1,
                        "llm_calls": stream.stats.llm_calls,
                        "eliminated_count": len(stream.eliminated),
                        "acknowledged_limitations": list(stream.scope_narrowings),
                    }
                    break
            if verbose:
                print(f"\n  ✓  x* found at cycle {cycle + 1}!"
                      f"  (total LLM calls: {stream.stats.llm_calls})")
            break
        else:
            # *** FIX: Gate failed → reset survivors so Revision Loop fires ***
            # Without this, has_zero_survivors() is never True on the next
            # iteration and the loop continues without generating new candidates.
            stream.survivors = []
            stream.obligations = []

    return stream


# ── Helpers ────────────────────────────────────────────────────────────────────

def _apply_phase3_result(stream: ResidualStream, candidates: list[dict], result: dict) -> None:
    """Merge live Phase3 derivation result into the stream."""
    new_survivors = []
    for s in result.get("survivors", []):
        new_survivors.append(s)
        for sn in s.get("scopenarrowings", []):
            stream.scope_narrowings.append(sn)

    for e in result.get("eliminated", []):
        already = any(x["candidateid"] == e["candidateid"] for x in stream.eliminated)
        if not already:
            stream.eliminated.append(e)
            stream.active_constraints.append(
                f"ELIMINATED {e['candidateid']}: {e['reason'][:120]}. "
                "New candidates MUST NOT repeat this claim."
            )

    stream.survivors = new_survivors
    stream.stats.total_eliminated = len(stream.eliminated)


def _banner(msg: str, char: str = "─", width: int = 60) -> None:
    line = char * width
    print(f"\n{line}\n  {msg}\n{line}")