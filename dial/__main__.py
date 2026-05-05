#!/usr/bin/env python3
"""
Dialectics MVP v3 — CLI entry point.

Usage:
  dial --unit-tests                         # offline unit tests (no Ollama)
  dial --case hep_01
  dial --case cffp_01 --model qwen2.5:7b
  dial --all-tests
  dial --interactive
  dial --case hep_03 --model llama3.1:8b    # v3 scope_narrowing test
  dial --case cffp_02 --model qwen2.5:7b    # v3 live CFFPPhase3

  # Direct HEP run (no test-case YAML needed)
  dial --protocol hep \\
       --phenomenon "API latency doubled after deployment" \\
       --evidence "Deployment on 2026-02-20" \\
       --evidence "Network topology changed on 2026-02-19" \\
       --evidence "DB query time unchanged"

  # Direct CFFP run
  dial --protocol cffp \\
       --construct evaluation_order \\
       --description "Order in which rules are evaluated" \\
       --invariant "I1:termination:Evaluation always terminates for finite rule sets" \\
       --invariant "I2:determinism:Identical inputs produce identical evaluation orders"
"""
from __future__ import annotations

import argparse
import json
import sys
import yaml

from pathlib import Path

from dial.residual_stream import ResidualStream
from dial.cycle_runner import run_dialectic_cycle
from dial.schemas.hep_schema import HEPValidator, HEPPhase3
from dial.schemas.cffp_schema import CFFPValidator, CFFPPhase3
from dial.attention_phase import check_model


OLLAMA_URL = "http://localhost:11434"


# ── Schema builders ────────────────────────────────────────────────────────────


def _build_schema(test_case: dict, model: str):
    """Build the appropriate schema validator for a test case."""
    protocol = test_case["protocol"]
    problem  = test_case["problem"]

    if protocol == "hep":
        evidence = problem.get("evidence", [])
        return HEPPhase3(
            evidence=evidence,
            model=model,
            ollama_url=OLLAMA_URL,
        )

    elif protocol == "cffp":
        invariants = problem.get("invariants", [])
        use_live   = test_case.get("use_llm_phase3", False)

        if use_live:
            return CFFPPhase3(
                invariants=invariants,
                canonical_constructs=[],
                model=model,
                ollama_url=OLLAMA_URL,
            )
        else:
            return CFFPValidator(invariants=invariants)

    else:
        raise ValueError(f"Unknown protocol: {protocol!r}")


def _build_schema_direct(protocol: str, args, model: str):
    """Build a schema from direct CLI flags (--protocol / --phenomenon etc.)."""
    if protocol == "hep":
        evidence = args.evidence or []
        return HEPPhase3(evidence=evidence, model=model, ollama_url=OLLAMA_URL), {
            "phenomenon": args.phenomenon or "",
            "evidence": evidence,
        }

    elif protocol == "cffp":
        invariants = []
        for raw in (args.invariant or []):
            # Expected format: "ID:class:description"
            parts = raw.split(":", 2)
            if len(parts) == 3:
                inv_id, inv_class, inv_desc = parts
            elif len(parts) == 2:
                inv_id, inv_class, inv_desc = parts[0], parts[1], parts[1]
            else:
                inv_id, inv_class, inv_desc = raw, "unknown", raw
            invariants.append({"id": inv_id.strip(), "class": inv_class.strip(),
                                "description": inv_desc.strip()})

        use_live = bool(invariants)  # use live Phase3 when invariants are provided
        schema = (
            CFFPPhase3(invariants=invariants, canonical_constructs=[], model=model,
                       ollama_url=OLLAMA_URL)
            if use_live
            else CFFPValidator(invariants=invariants)
        )
        problem = {
            "construct":   args.construct or "unnamed_construct",
            "description": args.description or "",
            "invariants":  invariants,
            "dependson":   [],
        }
        return schema, problem

    else:
        raise ValueError(f"Unknown protocol: {protocol!r}")


# ── Case runners ───────────────────────────────────────────────────────────────


def _run_case(test_case: dict, model: str, verbose: bool = True) -> ResidualStream:
    problem  = test_case["problem"]
    protocol = test_case["protocol"]
    schema   = _build_schema(test_case, model)

    # FIX: print [schema] message *inside* the case banner, not before it
    _print_case_header(test_case, model, schema)

    stream = run_dialectic_cycle(
        problem=problem,
        protocol=protocol,
        schema_validator=schema,
        model=model,
        verbose=verbose,
    )

    _print_summary(test_case, stream)
    return stream


def _print_case_header(test_case: dict, model: str, schema) -> None:
    print(f"\n{'='*60}")
    print(f"  Case: {test_case['id']} — {test_case['name']}")
    print(f"  Protocol: {test_case['protocol'].upper()}  |  Model: {model}")
    # FIX: schema type note printed here, after the banner, not before it
    if isinstance(schema, CFFPPhase3):
        print(f"  Schema: CFFPPhase3 — live LLM counterexample generation")
    elif isinstance(schema, HEPPhase3):
        print(f"  Schema: HEPPhase3  — live LLM assess → rebuttal → derive")
    elif isinstance(schema, CFFPValidator):
        print(f"  Schema: CFFPValidator — offline Python")
    elif isinstance(schema, HEPValidator):
        print(f"  Schema: HEPValidator  — offline Python")
    print(f"{'='*60}")


def _print_summary(test_case: dict, stream: ResidualStream) -> None:
    print(f"\n{'─'*60}")
    print(f"  SUMMARY — {test_case['id']}")
    print(f"{'─'*60}")

    if stream.x_star:
        x = stream.x_star
        print(f"  ✓  x* converged: {x.get('id','?')} — {x.get('description','')}")
        print(f"     cycles: {x.get('cycles_to_convergence','?')}"
              f"  | LLM calls: {x.get('llm_calls','?')}"
              f"  | eliminated: {x.get('eliminated_count','?')}")
        lims = x.get("acknowledged_limitations", [])
        if lims:
            print(f"  Acknowledged limitations ({len(lims)}):")
            for lim in lims:
                print(f"    · {lim[:120]}")
        else:
            print("  Acknowledged limitations: []")
    else:
        print(f"  ○  Open outcome — no x* found")
        print(f"     cycles_run: {stream.stats.cycles_run}"
              f"  | LLM calls: {stream.stats.llm_calls}"
              f"  | eliminated: {len(stream.eliminated)}")

    expected = test_case.get("expected_outcome")
    min_sn   = test_case.get("expected_scope_narrowings_min", 0)

    if expected == "survivor":
        ok = stream.x_star is not None
        print(f"\n  [T] expected_outcome=survivor → {'PASS ✓' if ok else 'FAIL ✗'}")

    if expected == "canonical":
        ok = stream.x_star is not None
        print(f"\n  [T] expected_outcome=canonical → {'PASS ✓' if ok else 'FAIL ✗'}")

    if min_sn > 0:
        actual_sn = len(stream.scope_narrowings)
        ok_sn = actual_sn >= min_sn
        print(f"  [T] scope_narrowings ≥ {min_sn} → "
              f"got {actual_sn} → {'PASS ✓' if ok_sn else 'FAIL ✗'}")


# ── Batch runner ───────────────────────────────────────────────────────────────


def _run_all(model: str, verbose: bool = True) -> None:
    # FIX: thread verbose through so --quiet is respected
    cases_path = Path(__file__).parent / "tests" / "test_cases.yaml"
    data = yaml.safe_load(cases_path.read_text())
    results = {}
    for tc in data["test_cases"]:
        try:
            stream = _run_case(tc, model, verbose=verbose)
        except Exception as exc:
            print(f"\n  ✗ CRASH in {tc['id']}: {exc}", file=sys.stderr)
            # Record a blank result so the summary table still prints
            results[tc["id"]] = {
                "x_star": False, "scope_narrowings": 0,
                "rebuttals": 0, "llm_calls": 0, "eliminated": 0,
                "error": str(exc),
            }
            continue
        results[tc["id"]] = {
            "x_star":           stream.x_star is not None,
            "scope_narrowings": len(stream.scope_narrowings),
            "rebuttals":        stream.stats.total_rebuttals,
            "llm_calls":        stream.stats.llm_calls,
            "eliminated":       len(stream.eliminated),
        }

    print(f"\n{'='*60}  ALL TESTS  {'='*10}")
    for cid, r in results.items():
        x_sym = "✓" if r["x_star"] else "○"
        err   = f"  ERROR: {r['error']}" if r.get("error") else ""
        print(f"  {x_sym} {cid}: rebuttals={r['rebuttals']}"
              f"  scope_narrowings={r['scope_narrowings']}"
              f"  eliminated={r['eliminated']}"
              f"  llm_calls={r['llm_calls']}{err}")


# ── Direct CLI run (--protocol flag) ──────────────────────────────────────────


def _run_direct(args, model: str, verbose: bool = True) -> None:
    """Run a single HEP or CFFP problem specified entirely via CLI flags."""
    protocol = args.protocol

    try:
        schema, problem = _build_schema_direct(protocol, args, model)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Synthetic test_case dict for _print_summary
    name = args.phenomenon or args.construct or "CLI problem"
    test_case = {
        "id":       "cli",
        "name":     name[:60],
        "protocol": protocol,
        "problem":  problem,
    }

    print(f"\n{'='*60}")
    print(f"  Direct run — protocol: {protocol.upper()}  |  model: {model}")
    if protocol == "hep":
        print(f"  Phenomenon: {args.phenomenon or '(none)'}")
        for i, ev in enumerate(args.evidence or [], 1):
            print(f"  E{i}: {ev}")
    else:
        print(f"  Construct: {args.construct or '(none)'}")
        for inv in problem.get("invariants", []):
            print(f"  {inv['id']} [{inv['class']}]: {inv['description']}")
    print(f"{'='*60}")

    stream = run_dialectic_cycle(
        problem=problem,
        protocol=protocol,
        schema_validator=schema,
        model=model,
        verbose=verbose,
    )

    _print_summary(test_case, stream)
    print(f"\n  x* = {json.dumps(stream.x_star, ensure_ascii=False, indent=2)}\n")


# ── Unit tests ─────────────────────────────────────────────────────────────────


def _run_unit_tests() -> None:
    """Run offline unit tests without Ollama."""
    import unittest
    loader = unittest.TestLoader()
    tests_dir = Path(__file__).parent / "tests"
    suite = loader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


# ── Interactive mode ───────────────────────────────────────────────────────────


def _interactive(model: str) -> None:
    print("\nDialectics MVP v3 — Interactive Mode")
    print("Type 'quit' to exit.\n")
    while True:
        phenomenon = input("Phenomenon: ").strip()
        if phenomenon.lower() == "quit":
            break
        evidence_raw = input("Evidence (comma-separated): ").strip()
        evidence = [e.strip() for e in evidence_raw.split(",") if e.strip()]
        problem  = {"phenomenon": phenomenon, "evidence": evidence}
        schema   = HEPPhase3(evidence=evidence, model=model, ollama_url=OLLAMA_URL)
        stream   = run_dialectic_cycle(
            problem=problem, protocol="hep",
            schema_validator=schema, model=model, verbose=True,
        )
        print(f"\n  x* = {json.dumps(stream.x_star, ensure_ascii=False, indent=2)}\n")


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Dialectics MVP v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Modes ──────────────────────────────────────────────────────────────
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--case",        help="Run specific test case id")
    mode.add_argument("--all-tests",   action="store_true",
                      help="Run all test cases (needs Ollama)")
    mode.add_argument("--unit-tests",  action="store_true",
                      help="Run offline unit tests (no Ollama)")
    mode.add_argument("--interactive", action="store_true",
                      help="Interactive HEP mode")

    # ── Direct run flags (used with --protocol) ────────────────────────────
    parser.add_argument("--protocol", choices=["hep", "cffp"],
                        help="Protocol for a direct run (no --case needed)")

    # HEP direct args
    parser.add_argument("--phenomenon",
                        help="Phenomenon to explain (HEP direct run)")
    parser.add_argument("--evidence", action="append", default=[],
                        metavar="ITEM",
                        help="Evidence item (HEP direct run, repeat flag for multiple)")

    # CFFP direct args
    parser.add_argument("--construct",
                        help="Construct name to formalize (CFFP direct run)")
    parser.add_argument("--description",
                        help="Construct description (CFFP direct run)")
    parser.add_argument("--invariant", action="append", default=[],
                        metavar="ID:class:description",
                        help="Invariant spec (CFFP direct run, repeat for multiple). "
                             "Format: ID:class:description  "
                             "e.g. I1:termination:Evaluation always terminates")

    # ── Global options ─────────────────────────────────────────────────────
    parser.add_argument("--model",  default="llama3.1:8b", help="Ollama model tag")
    parser.add_argument("--quiet",  action="store_true",   help="Suppress verbose output")

    args    = parser.parse_args()
    verbose = not args.quiet

    # ── --unit-tests never needs Ollama ────────────────────────────────────
    if args.unit_tests:
        _run_unit_tests()
        return

    # ── Decide mode ─────────────────────────────────────────────────────────
    # --protocol triggers a direct run even without --case / --all-tests
    direct_run = bool(args.protocol and not args.case and not args.all_tests
                      and not args.interactive)

    needs_ollama = args.case or args.all_tests or args.interactive or direct_run
    if needs_ollama:
        try:
            check_model(args.model, OLLAMA_URL)
        except RuntimeError as exc:
            print(f"\nError: {exc}", file=sys.stderr)
            sys.exit(1)

    if args.case:
        cases_path = Path(__file__).parent / "tests" / "test_cases.yaml"
        data = yaml.safe_load(cases_path.read_text())
        tc = next((t for t in data["test_cases"] if t["id"] == args.case), None)
        if not tc:
            print(f"Case not found: {args.case!r}")
            sys.exit(1)
        _run_case(tc, args.model, verbose=verbose)

    elif args.all_tests:
        _run_all(args.model, verbose=verbose)  # FIX: pass verbose

    elif args.interactive:
        _interactive(args.model)

    elif direct_run:
        _run_direct(args, args.model, verbose=verbose)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()