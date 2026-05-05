#!/usr/bin/env python3
"""
Dialectics MVP v3 — CLI entry point.

Usage:
  dial --unit-tests                   # offline unit tests (no Ollama)
  dial --case hep_01
  dial --case cffp_01 --model qwen2.5:7b
  dial --all-tests
  dial --interactive
  dial --case hep_03 --model llama3.1:8b  # v3 scope_narrowing test
  dial --case cffp_02 --model qwen2.5:7b  # v3 live CFFPPhase3
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
            print("  [schema] CFFPPhase3 → live LLM counterexample generation")
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


def _run_case(test_case: dict, model: str, verbose: bool = True) -> ResidualStream:
    problem  = test_case["problem"]
    protocol = test_case["protocol"]
    schema   = _build_schema(test_case, model)

    print(f"\n{'='*60}")
    print(f"  Case: {test_case['id']} — {test_case['name']}")
    print(f"  Protocol: {protocol.upper()}  |  Model: {model}")
    print(f"{'='*60}")

    stream = run_dialectic_cycle(
        problem=problem,
        protocol=protocol,
        schema_validator=schema,
        model=model,
        verbose=verbose,
    )

    _print_summary(test_case, stream)
    return stream


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

    if min_sn > 0:
        actual_sn = len(stream.scope_narrowings)
        ok_sn = actual_sn >= min_sn
        print(f"  [T] scope_narrowings ≥ {min_sn} → "
              f"got {actual_sn} → {'PASS ✓' if ok_sn else 'FAIL ✗'}")


def _run_all(model: str) -> None:
    cases_path = Path(__file__).parent / "tests" / "test_cases.yaml"
    data = yaml.safe_load(cases_path.read_text())
    results = {}
    for tc in data["test_cases"]:
        stream = _run_case(tc, model)
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
        print(f"  {x_sym} {cid}: rebuttals={r['rebuttals']}"
              f"  scope_narrowings={r['scope_narrowings']}"
              f"  eliminated={r['eliminated']}"
              f"  llm_calls={r['llm_calls']}")


def _run_unit_tests() -> None:
    """Run offline unit tests without Ollama."""
    import unittest
    loader = unittest.TestLoader()
    tests_dir = Path(__file__).parent / "tests"
    suite = loader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


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


def main():
    parser = argparse.ArgumentParser(description="Dialectics MVP v3")
    parser.add_argument("--case",        help="Run specific test case id")
    parser.add_argument("--all-tests",   action="store_true", help="Run all test cases (needs Ollama)")
    parser.add_argument("--unit-tests",  action="store_true", help="Run offline unit tests (no Ollama)")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--model",       default="llama3.1:8b", help="Ollama model tag")
    parser.add_argument("--quiet",       action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    verbose = not args.quiet

    # --unit-tests never needs Ollama — skip model check
    if args.unit_tests:
        _run_unit_tests()
        return

    # Every other mode talks to Ollama — verify the model is available first
    needs_ollama = args.case or args.all_tests or args.interactive
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
        _run_all(args.model)
    elif args.interactive:
        _interactive(args.model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()