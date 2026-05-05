#!/usr/bin/env python3
"""
Dialectics MVP — CLI entry point

Usage:
  python main.py --case hep_01 --verbose
  python main.py --case cffp_01
  python main.py --all-tests
  python main.py --interactive
  python main.py --model qwen2.5:7b --case hep_02
"""
import argparse
import json
import sys
import yaml
from pathlib import Path

from core.cycle_runner import run_dialectic_cycle
from schemas.hep_schema import HEPValidator
from schemas.cffp_schema import CFFPValidator


# ── Validator factory ──────────────────────────────────────────────────────────

def load_validator(protocol: str, problem: dict):
    if protocol == "hep":
        return HEPValidator(evidence=problem.get("evidence", []))
    if protocol == "cffp":
        return CFFPValidator(
            invariants=problem.get("invariants", []),
            canonical_constructs=problem.get("dependson", []),
        )
    raise ValueError(f"Unknown protocol: {protocol!r}. Choose 'hep' or 'cffp'.")


# ── Test runner ────────────────────────────────────────────────────────────────

def run_test_case(case: dict, model: str, verbose: bool) -> dict:
    sep = "═" * 62
    print(f"\n{sep}")
    print(f"  TEST: {case['name']}")
    print(f"  Protocol: {case['protocol'].upper()}  |  Model: {model}")
    print(sep)

    validator = load_validator(case["protocol"], case["problem"])

    stream = run_dialectic_cycle(
        problem=case["problem"],
        protocol=case["protocol"],
        schema_validator=validator,
        model=model,
        verbose=verbose,
    )

    print(f"\n{'─' * 62}")
    print("  RESULT:")

    if stream.x_star:
        xstar = stream.x_star
        print(f"  ✓ x* found in {xstar['cycles_to_convergence']} cycle(s)")
        print(f"  ID          : {xstar['id']}")
        print(f"  Description : {xstar['description']}")
        print(f"  Claim       : {xstar['claim'][:220]}")
        if xstar.get("acknowledged_limitations"):
            print("  Acknowledged limitations:")
            for lim in xstar["acknowledged_limitations"]:
                print(f"    • {lim}")
    elif stream.survivors:
        print("  ✓ Survivors (Obligation Gate not triggered):")
        for s in stream.survivors:
            print(f"    • {s['candidateid']}")
    else:
        print("  ⚠  Open outcome — revision loop did not converge.")
        print(f"  Eliminated candidates : {len(stream.eliminated)}")
        print(f"  Active constraints    : {len(stream.active_constraints)}")

    expected = case.get("expected_outcome")
    actual_ok = stream.x_star is not None or len(stream.survivors) > 0
    if expected in ("survivor", "canonical"):
        status = "PASS ✓" if actual_ok else "FAIL ✗"
    else:
        status = "UNKNOWN"

    print(f"\n  Test status: {status}")

    return {
        "case": case["id"],
        "converged": stream.x_star is not None,
        "survivors": len(stream.survivors),
        "cycles": stream.cycle + 1,
        "status": status,
    }


# ── Interactive mode ───────────────────────────────────────────────────────────

def interactive_mode(model: str) -> None:
    print("\n=== Dialectics MVP — Interactive Mode ===")
    print("Choose protocol:")
    print("  1. HEP  — explain an observed phenomenon")
    print("  2. CFFP — formalize a construct")

    choice = input("\nChoice (1/2): ").strip()

    if choice == "1":
        protocol = "hep"
        phenomenon = input("Describe the phenomenon: ")
        print("Enter evidence (one per line, blank to finish):")
        evidence: list[str] = []
        while True:
            ev = input(f"  [{len(evidence) + 1}] ").strip()
            if not ev:
                break
            evidence.append(ev)
        problem = {"phenomenon": phenomenon, "evidence": evidence}
        validator = HEPValidator(evidence=evidence)
    else:
        protocol = "cffp"
        construct = input("Construct name: ")
        description = input("Description: ")
        print("Enter invariants as  id:class:description  (blank to finish):")
        invariants: list[dict] = []
        while True:
            inv_str = input(f"  [I{len(invariants) + 1}] ").strip()
            if not inv_str:
                break
            parts = inv_str.split(":", 2)
            invariants.append({
                "id": parts[0] if len(parts) > 0 else f"I{len(invariants) + 1}",
                "class": parts[1] if len(parts) > 1 else "general",
                "description": parts[2] if len(parts) > 2 else inv_str,
            })
        problem = {"construct": construct, "description": description,
                   "invariants": invariants}
        validator = CFFPValidator(invariants=invariants)

    stream = run_dialectic_cycle(
        problem=problem,
        protocol=protocol,
        schema_validator=validator,
        model=model,
        verbose=True,
    )

    if stream.x_star:
        print("\n=== x* (Final Answer) ===")
        print(json.dumps(stream.x_star, indent=2, ensure_ascii=False))
    else:
        print("\n=== No x* — Open Outcome ===")
        print(f"Survivors: {[s['candidateid'] for s in stream.survivors]}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dialectics MVP — Local Reasoning Engine on 8B models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --case hep_01
  python main.py --case cffp_01 --model qwen2.5:7b
  python main.py --all-tests
  python main.py --interactive
        """,
    )
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Ollama model name (default: llama3.1:8b)")
    parser.add_argument("--protocol", choices=["hep", "cffp"],
                        help="Protocol to run")
    parser.add_argument("--case", metavar="CASE_ID",
                        help="Test case id from test_cases.yaml")
    parser.add_argument("--test-file", default="tests/test_cases.yaml",
                        metavar="FILE")
    parser.add_argument("--all-tests", action="store_true",
                        help="Run all test cases in test_cases.yaml")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive problem input mode")
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-cycle output")

    args = parser.parse_args()

    if args.quiet:
        args.verbose = False

    if args.interactive:
        interactive_mode(args.model)
        return

    if args.all_tests or args.case:
        test_path = Path(args.test_file)
        if not test_path.exists():
            print(f"Error: test file not found: {test_path}", file=sys.stderr)
            sys.exit(1)

        with open(test_path) as f:
            test_data = yaml.safe_load(f)

        cases = test_data.get("test_cases", [])

        if args.case:
            cases = [c for c in cases if c["id"] == args.case]
            if not cases:
                ids = [c["id"] for c in test_data.get("test_cases", [])]
                print(f"Test case '{args.case}' not found. Available: {ids}",
                      file=sys.stderr)
                sys.exit(1)

        results = []
        for case in cases:
            r = run_test_case(case, args.model, args.verbose)
            results.append(r)

        if len(results) > 1:
            print(f"\n\n{'═' * 62}")
            print("  TEST SUMMARY")
            print(f"{'═' * 62}")
            for r in results:
                symbol = "✓" if r["converged"] else "○"
                print(f"  {symbol} {r['case']:12s}  "
                      f"cycles={r['cycles']}  "
                      f"survivors={r['survivors']}  "
                      f"{r['status']}")
        return

    # If no action specified, print help
    parser.print_help()


if __name__ == "__main__":
    main()
