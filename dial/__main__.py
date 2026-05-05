#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

from dial.cycle_runner import run_dialectic_cycle
from dial.hep_schema import HEPValidator
from dial.cffp_schema import CFFPValidator


OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not OLLAMA_BASE_URL.startswith("http://") and not OLLAMA_BASE_URL.startswith("https://"):
    OLLAMA_BASE_URL = f"http://{OLLAMA_BASE_URL}"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"


def _in_kaggle() -> bool:
    return os.path.exists("/kaggle") or "KAGGLE_KERNEL_RUN_TYPE" in os.environ


def _fetch_available_models() -> list[str]:
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _ensure_ollama(model: str, quiet: bool = False, allow_fallback: bool = False) -> str:
    """
    Returns the model name that should actually be used.
    If allow_fallback=True and requested model is absent but at least one model exists,
    fallback to the first available one.
    """
    models = _fetch_available_models()

    if not models:
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║  Ollama not detected or no models are available             ║\n"
            "║                                                              ║\n"
            "║  Kaggle setup:                                               ║\n"
            "║    !apt-get install -y -q zstd                               ║\n"
            "║    !curl -fsSL https://ollama.ai/install.sh | sh             ║\n"
            "║    import subprocess, time                                   ║\n"
            "║    subprocess.Popen(['/usr/local/bin/ollama', 'serve'])      ║\n"
            "║    time.sleep(3)                                             ║\n"
            "║    !/usr/local/bin/ollama pull llama3.1:8b                   ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n"
        )
        sys.exit(1)

    if not quiet:
        print(f"  ✓ Ollama live. Models available: {models}")

    if model in models:
        return model

    if allow_fallback and models:
        fallback = models[0]
        print(
            f"\n  ⚠  Model '{model}' not found locally.\n"
            f"     Falling back to '{fallback}'.\n"
            f"     To use the requested model, run: ollama pull {model}\n"
        )
        return fallback

    print(
        f"\n  ⚠  Model '{model}' not found locally.\n"
        f"     Run: ollama pull {model}\n"
        f"     Available now: {models}\n"
    )
    sys.exit(1)


def load_validator(protocol: str, problem: dict):
    if protocol == "hep":
        return HEPValidator(evidence=problem.get("evidence", []))
    if protocol == "cffp":
        return CFFPValidator(
            invariants=problem.get("invariants", []),
            canonical_constructs=problem.get("dependson", []),
        )
    raise ValueError(f"Unknown protocol: {protocol!r}. Choose 'hep' or 'cffp'.")


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


def run_unit_tests() -> None:
    try:
        import pytest
    except ImportError:
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
            ("HEP valid_candidate_survives", test_valid_candidate_survives),
            ("HEP missing_proof_sketch", test_missing_proof_sketch_eliminated),
            ("HEP prior_elimination", test_prior_elimination_detected),
            ("CFFP valid_formalism_survives", test_valid_formalism_survives),
            ("CFFP missing_termination", test_missing_termination_eliminated),
            ("CFFP missing_determinism", test_missing_determinism_eliminated),
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

    import dial.tests as tests_pkg
    tests_dir = str(Path(tests_pkg.__file__).parent)
    sys.exit(pytest.main([tests_dir, "-v"]))


def _resolve_test_file(override: str | None) -> Path:
    if override and Path(override).exists():
        return Path(override)
    bundled = Path(__file__).parent / "tests" / "test_cases.yaml"
    if bundled.exists():
        return bundled
    raise FileNotFoundError("test_cases.yaml not found. Pass --test-file <path> explicitly.")


def _build_problem_from_args(args) -> tuple[str, dict]:
    if not args.protocol:
        raise SystemExit("For direct problem runs, pass --protocol hep|cffp")

    if args.protocol == "hep":
        if not args.phenomenon:
            raise SystemExit("--phenomenon is required for --protocol hep")
        evidence = args.evidence or []
        problem = {
            "phenomenon": args.phenomenon,
            "evidence": evidence,
            "mode": "bounded",
            "exhaustive": False,
        }
        return "hep", problem

    if args.protocol == "cffp":
        if not args.construct:
            raise SystemExit("--construct is required for --protocol cffp")
        invariants = []
        for inv in args.invariant or []:
            parts = inv.split(":", 2)
            invariants.append({
                "id": parts[0] if len(parts) > 0 else f"I{len(invariants)+1}",
                "class": parts[1] if len(parts) > 1 else "general",
                "description": parts[2] if len(parts) > 2 else inv,
            })
        problem = {
            "construct": args.construct,
            "description": args.description or "",
            "invariants": invariants,
            "dependson": [],
        }
        return "cffp", problem

    raise SystemExit(f"Unsupported protocol: {args.protocol}")


def _run_direct_problem(args, model: str, verbose: bool) -> None:
    protocol, problem = _build_problem_from_args(args)
    validator = load_validator(protocol, problem)
    stream = run_dialectic_cycle(
        problem=problem,
        protocol=protocol,
        schema_validator=validator,
        model=model,
        verbose=verbose,
    )

    print("\n=== RESULT ===")
    if stream.x_star:
        print(json.dumps(stream.x_star, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({
            "survivors": stream.survivors,
            "eliminated": stream.eliminated,
            "constraints": stream.active_constraints,
            "history": stream.history,
        }, indent=2, ensure_ascii=False))


def interactive_mode_local_terminal(model: str) -> None:
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
        print("Enter invariants as id:class:description (blank to finish):")
        invariants: list[dict] = []
        while True:
            inv_str = input(f"  [I{len(invariants) + 1}] ").strip()
            if not inv_str:
                break
            parts = inv_str.split(":", 2)
            invariants.append({
                "id": parts[0] if len(parts) > 0 else f"I{len(invariants)+1}",
                "class": parts[1] if len(parts) > 1 else "general",
                "description": parts[2] if len(parts) > 2 else inv_str,
            })
        problem = {"construct": construct, "description": description, "invariants": invariants}
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
        print(json.dumps(stream.history, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dial",
        description="Dialectics MVP — Local Reasoning Engine on 8B models",
    )
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--case", metavar="CASE_ID")
    parser.add_argument("--test-file", default=None, metavar="FILE")
    parser.add_argument("--all-tests", action="store_true")
    parser.add_argument("--unit-tests", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--allow-model-fallback", action="store_true")

    # Kaggle-safe direct mode
    parser.add_argument("--protocol", choices=["hep", "cffp"])
    parser.add_argument("--phenomenon")
    parser.add_argument("--evidence", action="append")
    parser.add_argument("--construct")
    parser.add_argument("--description")
    parser.add_argument("--invariant", action="append")

    args = parser.parse_args()
    verbose = not args.quiet

    if args.unit_tests:
        run_unit_tests()
        return

    resolved_model = _ensure_ollama(
        args.model,
        quiet=not verbose,
        allow_fallback=args.allow_model_fallback,
    )

    # Direct notebook-safe mode: no stdin needed
    if args.protocol:
        _run_direct_problem(args, resolved_model, verbose)
        return

    if args.interactive:
        if _in_kaggle():
            print(
                "\nKaggle does not reliably support stdin/input()-driven CLI interaction.\n"
                "Use notebook-safe flags instead, for example:\n\n"
                "  !dial --protocol hep "
                "--phenomenon \"API latency increased 40% after deployment\" "
                "--evidence \"Deployment happened on 2026-02-20\" "
                "--evidence \"Network topology changed on 2026-02-19\"\n\n"
                "  !dial --protocol cffp "
                "--construct evaluation_order "
                "--description \"The order in which rules are evaluated\" "
                "--invariant I1:termination:Evaluation_always_terminates "
                "--invariant I2:determinism:Identical_inputs_produce_identical_orders\n"
            )
            sys.exit(2)
        interactive_mode_local_terminal(resolved_model)
        return

    if args.all_tests or args.case:
        test_path = _resolve_test_file(args.test_file)
        with open(test_path) as f:
            test_data = yaml.safe_load(f)

        cases = test_data.get("test_cases", [])
        if args.case:
            cases = [c for c in cases if c["id"] == args.case]
            if not cases:
                ids = [c["id"] for c in test_data.get("test_cases", [])]
                print(f"Test case '{args.case}' not found. Available: {ids}", file=sys.stderr)
                sys.exit(1)

        results = []
        for case in cases:
            r = run_test_case(case, resolved_model, verbose)
            results.append(r)

        if len(results) > 1:
            print(f"\n\n{'═' * 62}")
            print("  SUMMARY")
            print(f"{'═' * 62}")
            for r in results:
                sym = "✓" if r["converged"] else "○"
                print(
                    f"  {sym} {r['case']:12s}  cycles={r['cycles']}  "
                    f"survivors={r['survivors']}  {r['status']}"
                )
        return

    parser.print_help()


if __name__ == "__main__":
    main()