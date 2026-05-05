"""
Dialectics MVP — main Attention ↔ CUE loop.

Phase layout (from dialectics.cue):
  [2] Attention  — LLM generates candidates
  [3] CUE        — offline or live adversarial pressure
                   v3: assess breakdown + rebuttal logging
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
    """Return a live Phase3 runner when available, else None (→ offline cue_phase)."""
    try:
        return schema_validator.make_phase3(model)
    except (AttributeError, ImportError, Exception):
        return None


# ── Obligation Gate ────────────────────────────────────────────────────────────


def _obligation_gate(stream: ResidualStream, problem: dict, model: str) -> bool:
    if not stream.survivors:
        return False

    context = {
        "survivors": stream.survivors,
        "problem": problem,
        "scope_narrowings": stream.scope_narrowings,
        "instruction": (
            "For each surviving candidate, check ALL four obligations: "
            "causal_sufficiency, predictions_confirmed, scope_not_trivial, "
            "no_background_conflict. Return JSON {obligations: [...]}."
        ),
    }

    prompt = get_prompt("obligation_gate").format(
        context=json.dumps(context, ensure_ascii=False, indent=2)
    )

    try:
        raw = call_ollama(prompt, model)
        obj = extract_json_object(raw)
        obligations = obj.get("obligations", [])
    except Exception:
        return False

    if not obligations:
        return False

    stream.obligations = obligations

    for ob in obligations:
        sat = ob.get("satisfied", False)
        sym = "✓" if sat else "✗"
        prop = ob.get("property", "?")
        arg = ob.get("argument", "")[:60]
        print(f"       {sym} {ob.get('candidateid','?')}: {prop} — {arg}")

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

    stream.problem = problem
    stream.cross_support = []
    stream.assessment_breakdown = {}
    stream.rebuttals_log = []

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
            if verbose:
                print("  [2] No parseable candidates — forcing revision loop")
            revision_count += 1
            if revision_count > MAX_REVISION_LOOPS:
                break
            stream.candidates = []
            continue

        if verbose:
            print(f"  [2] Candidates: {len(stream.candidates)}")
            for c in stream.candidates:
                print(f"       • {c['id']}: {c.get('description', '')[:80]}")

        # ── [3] CUE ─────────────────────────────────────────────────────────
        if live:
            if verbose:
                print(f"  [3] CUE → live LLM (assess→rebuttal→derive) ...")
            phase3_result = phase3.run(stream.candidates, stream)
            stream.stats.llm_calls += 2  # assess + rebuttal(s)
            _apply_phase3_result(stream, stream.candidates, phase3_result)

            # ── v3 verbose: assessment breakdown ──────────────────────────
            if verbose:
                bd = phase3_result.get("assessment_breakdown", {})
                total = bd.get("total", 0)
                if total:
                    print(f"\n  [3] EvidenceAssessments: {total} pairs evaluated")
                    if bd.get("decisive"):
                        print(f"       decisive:      {', '.join(bd['decisive'])}"
                              "  → immediate elimination")
                    if bd.get("strong"):
                        print(f"       strong:        {', '.join(bd['strong'])}"
                              "  → rebuttal triggered")
                    if bd.get("weak"):
                        print(f"       weak:          {', '.join(bd['weak'])}"
                              "  → pressure recorded")
                    uninf = bd.get("uninformative", [])
                    if uninf:
                        print(f"       uninformative: {', '.join(uninf)}")

            # ── v3 verbose: rebuttals ─────────────────────────────────────
            rebuttals = phase3_result.get("rebuttals", [])
            if verbose and rebuttals:
                print(f"\n  [3] Rebuttals: {len(rebuttals)}")
                for r in rebuttals:
                    lim = r.get("limitationdescription", "")
                    lim_str = f' → "{lim[:60]}"' if lim else ""
                    print(f"       {r['hypothesisid']} vs {r['evidenceid']}: {r['kind']}{lim_str}")
            elif verbose:
                print(f"\n  [3] Rebuttals: 0")

            # ── v3 verbose: cross_support ─────────────────────────────────
            cs = phase3_result.get("cross_support", [])
            if verbose and cs:
                print(f"\n  [CrossSupport]")
                for x in cs:
                    print(
                        f"       {x.get('evidenceid', '?')} supports "
                        f"{x.get('supported', '?')} over {x.get('pressured', '?')}: "
                        f"{x.get('argument', '')[:60]}"
                    )

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
                ns = len(s.get("scopenarrowings", []))
                print(f"       ✓ {s['candidateid']}  (scope_narrowings: {ns})")
                for sn in s.get("scopenarrowings", []):
                    print(f'            → "{sn[:80]}"')

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
            stream.survivors = []
            stream.obligations = []
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
                print(
                    f"\n  ✓  x* found at cycle {cycle + 1}!"
                    f"  (total LLM calls: {stream.stats.llm_calls})"
                )
                if stream.x_star and stream.x_star.get("acknowledged_limitations"):
                    print("  Acknowledged limitations:")
                    for lim in stream.x_star["acknowledged_limitations"]:
                        print(f"    · {lim[:100]}")
            break
        else:
            stream.survivors = []
            stream.obligations = []

    return stream


# ── Helpers ────────────────────────────────────────────────────────────────────


def _apply_phase3_result(
    stream: ResidualStream,
    candidates: list[dict],
    result: dict,
) -> None:
    """Merge live Phase3 result into the stream."""
    new_survivors: list[dict] = []
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

    stream.eliminated_with_challenges.extend(result.get("eliminated_with_challenges", []))

    rebuttals = result.get("rebuttals", [])
    stream.stats.total_rebuttals += len(rebuttals)
    stream.survivors = new_survivors
    stream.stats.total_eliminated = len(stream.eliminated)


def _banner(msg: str, char: str = "─", width: int = 60) -> None:
    line = char * width
    print(f"\n{line}\n  {msg}\n{line}")