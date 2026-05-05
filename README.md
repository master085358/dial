# Dialectics MVP — Local Reasoning Engine on 8B Models

**Version:** 1.0 · **Status:** MVP · **Model:** Llama-3.1-8B-Instruct / Qwen2.5-7B-Instruct (Ollama)

Closes the **Attention ↔ CUE** cycle on a local 8B model using two protocols from the
[Riverline Dialectics](https://github.com/) repository:

- **HEP** — Hypothesis Elimination Protocol (causal reasoning)
- **CFFP** — Constraint-First Formalization Protocol (formal construct design)

```
User inputs problem
       ↓
[Attention-Orchestrator] → LLM generates candidates (JSON)
       ↓
[CUE-Compiler]          → Python constraint validation
       ↓
violations → back to LLM as new constraints
       ↓
convergence → x* returned to user
```

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai) with a pulled model
- 8 GB free RAM minimum (4-bit quantised 8B)

## Installation

```bash
# 1. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Pull model (choose one)
ollama pull llama3.1:8b          # recommended — 4.7 GB
# ollama pull qwen2.5:7b         # better reasoning
# ollama pull mistral:7b         # faster

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run first test
python main.py --case hep_01

# 5. Run all tests
python main.py --all-tests

# 6. Interactive mode
python main.py --interactive
```

## Usage

```bash
# Specific test case
python main.py --case hep_01 --verbose
python main.py --case cffp_01 --model qwen2.5:7b

# All three test cases
python main.py --all-tests

# Interactive (enter your own problem)
python main.py --interactive

# Quiet mode (no per-cycle output)
python main.py --case hep_01 --quiet
```

## Project Structure

```
dialectics-mvp/
├── README.md
├── requirements.txt
├── config.yaml                  ← model, cycle parameters
├── main.py                      ← CLI entry point
│
├── core/
│   ├── residual_stream.py       ← state between cycles
│   ├── attention_phase.py       ← LLM call (Phase A)
│   ├── cue_phase.py             ← Python CUE compiler (Phase B)
│   └── cycle_runner.py          ← main Attention ↔ CUE loop
│
├── protocols/
│   ├── hep.py                   ← HEP protocol metadata
│   └── cffp.py                  ← CFFP protocol metadata
│
├── schemas/
│   ├── hep_schema.py            ← HEP validator (DirectContradiction, EvidenceGap, PriorElimination)
│   └── cffp_schema.py           ← CFFP validator (invariants, composition, static obligations)
│
├── prompts/
│   ├── hep_attention.txt        ← Phase A prompt (HEP)
│   ├── cffp_attention.txt       ← Phase A prompt (CFFP)
│   └── rebuttal.txt             ← rebuttal generation prompt
│
└── tests/
    ├── test_cases.yaml          ← 3 test scenarios
    ├── test_hep.py              ← HEP unit tests (no Ollama)
    └── test_cffp.py             ← CFFP unit tests (no Ollama)
```

## Running Unit Tests (no Ollama needed)

```bash
cd dialectics-mvp
python tests/test_hep.py
python tests/test_cffp.py
```

## Acceptance Criteria

| ID | Test | Criterion |
|----|------|-----------|
| T1 | `hep_01` runs without errors | exit code 0 |
| T2 | HEP returns ≥1 survivor | `stream.survivors` non-empty |
| T3 | CFFP formalizes `evaluation_order` | `stream.x_star` not None |
| T4 | Eliminations accumulate in stream | `stream.eliminated` grows |
| T5 | `active_constraints` fed to next Attention | constraints grow across cycles |
| T6 | Revision Loop fires on 0 survivors | `revision_count` increments |
| T7 | `x*` contains `acknowledged_limitations` | field non-empty after scope narrowing |

## Architecture Mapping (MVP ↔ dialectics.cue)

| dialectics.cue component | MVP implementation |
|--------------------------|-------------------|
| Rebuttal | `HEPValidator.validate()` → `valid=False` + reason |
| Derivation | `cue_phase.py` — survivors/eliminated loop |
| ObligationGate | `ResidualStream.has_converged()` |
| RevisionLoop | `cycle_runner.py` — `if has_zero_survivors()` block |
| ScopeNarrowing | `scope_narrowings` in `ResidualStream` |
| hep.cue Phase 2 | `attention_phase.py` — LLM generates candidates |
| hep.cue Phase 3 | `HEPValidator` — DirectContradiction, EvidenceGap |
| cffp.cue Phase 1 | `CFFPValidator.__init__(invariants=...)` |
| cffp.cue Phase 3 | `_check_invariant()`, `_check_composition()` |
| recording.cue | `ResidualStream.history` (simplified) |
| routing.cue | `--protocol` CLI argument (manual) |

## Roadmap to v2

```
MVP (this repo)
  + SQLite for recording.cue Records
  + cue binary for real .cue file validation
  + embeddings for _semantically_similar()
  + structured output / grammar sampling for JSON parsing
  + Temporal workflow for fault tolerance
  → Full Production System
```
# dial
