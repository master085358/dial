#!/usr/bin/env python3
"""
Dialectics MVP — CLI entry point

Kaggle usage (no GPU needed, runs Ollama on CPU):
  !uvx --from git+https://github.com/<user>/dial dial --all-tests
  !uvx --from git+https://github.com/<user>/dial dial --interactive
  !uvx --from git+https://github.com/<user>/dial dial --case hep_01

Local usage:
  dial --all-tests
  dial --case cffp_01 --model qwen2.5:7b
  dial --interactive
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from dial.cycle_runner import run_dialectic_cycle
from dial.hep_schema import HEPValidator
from dial.cffp_schema import CFFPValidator


# ── Kaggle / Ollama bootstrap ──────────────────────────────────────────────────

def _ensure_ollama(model: str, quiet: bool = False) -> bool:
    """
    On Kaggle (or any fresh machine) Ollama may not be running.
    Try to ping it; print a friendly setup guide if it's not reachable.
    Returns True if Ollama is live.
    """
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            tags = [m["name"] for m in r.json().get("models", [])]
            if not quiet:
                print(f"  ✓ Ollama live. Models available: {tags or '(none pulled yet)'}")
            if not any(model.split(":")[0] in t for t in tags):
                print(f"\n  ⚠  Model '{model}' not found locally.")
                print(f"     Run:  ollama pull {model}\n")
            return True
    except Exception:
        pass

    print("""
╔══════════════════════════════════════════════════════════════╗
║  Ollama not detected at http://localhost:11434               ║
║                                                              ║
║  Kaggle setup (run in a notebook cell):                      ║
║                                                              ║
║    import subprocess, time                                   ║
║    subprocess.Popen(["ollama", "serve"])                     ║
║    time.sleep(3)                                             ║
║    subprocess.run(["ollama", "pull", "llama3.1:8b"])         ║
║                                                              ║
║  Or install Ollama first:                                    ║
║    !curl -fsSL https://ollama.ai/install.sh | sh             ║
║    !ollama pull llama3.1:8b                                  ║
╚══════════════════════════════════════════════════════════════╝
""")
    return False


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
    print(f"  TEST : {case['name']}")
    print(f"  Proto: {case['protocol'].upper()}  |  Model: {model}")
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
        x = stream.x_star
        print(f"  ✓ x* found in {x['cycles_to_convergence']} cycle(s)")
        print(f"  ID          : {x['id']}")
        print(f"  Description : {x['description']}")
        print(f"  Claim       : {x['claim'][:220]}")
        if x.get("acknowledged_limitations"):
            print("  Acknowledged limitations:")
            for lim in x["acknowledged_limitations"]:
                print(f"    • {lim}")
    elif stream.survivors:
        print("  ✓ Survivors (Obligation Gate not triggered):")
        for s in stream.survivors:
            print(f"    • {s['candidateid']}")
    else:
        print("  ⚠  Open outcome — revision loop did not converge.")
        print(f"  Eliminated  : {len(stream.eliminated)}")
        print(f"  Constraints : {len(stream.active_constraints)}")

    expected = case.get("expected_outcome")
    actual_ok = stream.x_star is not None or len(stream.survivors) > 0
    status = "PASS ✓" if (expected in ("survivor", "canonical") and actual_ok) else (
        "FAIL ✗" if expected in ("survivor", "canonical") else "UNKNOWN"
    )
    print(f"\n  Status: {status}")

    return {
        "case": case["id"],
        "converged": stream.x_star is not None,
        "survivors": len(stream.survivors),
        "cycles": stream.cycle + 1,
        "status": status,
    }


# ── Pytest runner (--unit-tests) ───────────────────────────────────────────────

def run_unit_tests() -> None:
    """Run offline unit tests (no Ollama required)."""
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("pytest not installed. Running tests manually...")
        from dial.tests.test_hep import (
            test_valid_candidate_survives,
            test_missing_proof_sketch_eliminated,
            test_prior_elimination_detected,
        )
        from dial.tests.test_cffp import (
            test_valid_formalism_survives,
            test_missing_termination_eliminated,
            test_missing_determinism_eliminated,
        )
        tests = [
            ("HEP: valid_candidate_survives", test_valid_candidate_survives),
            ("HEP: missing_proof_sketch_eliminated", test_missing_proof_sketch_eliminated),
            ("HEP: prior_elimination_detected", test_prior_elimination_detected),
            ("CFFP: valid_formalism_survives", test_valid_formalism_survives),
            ("CFFP: missing_termination_eliminated", test_missing_termination_eliminated),
            ("CFFP: missing_determinism_eliminated", test_missing_determinism_eliminated),
        ]
        passed = failed = 0
        for name, fn in tests:
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
                failed += 1
        print(f"\n  {passed} passed, {failed} failed")
        return

    # pytest is available
    import dial.tests as tests_pkg
    tests_dir = str(Path(tests_pkg.__file__).parent)
    sys.exit(pytest.main([tests_dir, "-v"]))


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
                "id": parts[0],
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


# ── Resolve bundled test_cases.yaml ───────────────────────────────────────────

def _resolve_test_file(override: str | None) -> Path:
    if override and Path(override).exists():
        return Path(override)
    # Bundled copy inside the package
    bundled = Path(__file__).parent / "tests" / "test_cases.yaml"
    if bundled.exists():
        return bundled
    raise FileNotFoundError(
        "test_cases.yaml not found. Pass --test-file <path> explicitly."
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dial",
        description="Dialectics MVP — Local Reasoning Engine on 8B models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Kaggle examples (in a notebook cell):
  !dial --all-tests
  !dial --case hep_01
  !dial --case cffp_01 --model qwen2.5:7b
  !dial --interactive
  !dial --unit-tests          # offline, no Ollama needed
        """,
    )
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Ollama model name (default: llama3.1:8b)")
    parser.add_argument("--case", metavar="CASE_ID",
                        help="Run a specific test case (hep_01 / cffp_01 / hep_02)")
    parser.add_argument("--test-file", default=None, metavar="FILE",
                        help="Path to test_cases.yaml (default: bundled)")
    parser.add_argument("--all-tests", action="store_true",
                        help="Run all test cases in test_cases.yaml")
    parser.add_argument("--unit-tests", action="store_true",
                        help="Run offline unit tests (no Ollama required)")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive problem input mode")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-cycle verbose output")

    args = parser.parse_args()
    verbose = not args.quiet

    # ── Offline unit tests — no Ollama ────────────────────────────────────────
    if args.unit_tests:
        run_unit_tests()
        return

    # ── Interactive ───────────────────────────────────────────────────────────
    if args.interactive:
        _ensure_ollama(args.model)
        interactive_mode(args.model)
        return

    # ── Test case(s) ──────────────────────────────────────────────────────────
    if args.all_tests or args.case:
        _ensure_ollama(args.model, quiet=not verbose)
        test_path = _resolve_test_file(args.test_file)

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
            r = run_test_case(case, args.model, verbose)
            results.append(r)

        if len(results) > 1:
            print(f"\n\n{'═' * 62}")
            print("  SUMMARY")
            print(f"{'═' * 62}")
            for r in results:
                sym = "✓" if r["converged"] else "○"
                print(f"  {sym} {r['case']:12s}  cycles={r['cycles']}  "
                      f"survivors={r['survivors']}  {r['status']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
