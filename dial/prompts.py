"""Prompt templates embedded as module constants."""

# ── Phase A: Attention ─────────────────────────────────────────────────────────

HEP_ATTENTION = """\
You are running Phase 2 of the Hypothesis Elimination Protocol (HEP).

Your task: generate candidate hypotheses that causally explain the observed phenomenon.

CONTEXT:
{context}

RULES:
1. Generate EXACTLY 3 DISTINCT hypotheses as a JSON array.
2. Each hypothesis MUST have exactly these keys: id (C1, C2, C3), description, claim, proof_sketch.
3. proof_sketch must explain WHY the hypothesis is plausible given the evidence in context.problem.evidence.
4. Do NOT repeat hypotheses from context.eliminated_so_far.
5. Respect ALL strings in context.active_constraints — they are hard constraints from CUE.
6. If context.cycle > 0: previous candidates FAILED — generate stronger, more specific ones.
7. claim format: "X causes Y because Z"

OUTPUT FORMAT — STRICT JSON ARRAY ONLY. No text before or after the array:
```json
[
  {{
    "id": "C1",
    "description": "Short hypothesis name",
    "claim": "Full causal claim: X causes Y because Z",
    "proof_sketch": "Evidence references: ..."
  }},
  {{
    "id": "C2",
    "description": "...",
    "claim": "...",
    "proof_sketch": "..."
  }},
  {{
    "id": "C3",
    "description": "...",
    "claim": "...",
    "proof_sketch": "..."
  }}
]
```
"""

CFFP_ATTENTION = """\
You are running Phase 2 of the Constraint-First Formalization Protocol (CFFP).

Your task: generate candidate formalisms for the construct under design.

CONTEXT:
{context}

RULES:
1. Generate EXACTLY 3 DISTINCT candidate formalisms as a JSON array.
2. Each formalism MUST have exactly: id, description, claim, proof_sketch.
3. claim must be a formal statement with: structure, evaluation_rule, resolution_rule.
4. proof_sketch MUST explicitly address EVERY invariant in context.problem.invariants:
   - For class "termination": use the word "terminates" or "finite"
   - For class "determinism": use "deterministic" or "reproducible" — NEVER use "random"
5. Do NOT repeat approaches from context.eliminated_so_far.
6. Respect ALL strings in context.active_constraints.

OUTPUT FORMAT — STRICT JSON ARRAY ONLY. No text before or after the array:
```json
[
  {{
    "id": "C1",
    "description": "Formalism name",
    "claim": "structure: ... | evaluation_rule: ... | resolution_rule: ...",
    "proof_sketch": "I1: [termination argument — uses word terminates or finite]. I2: [determinism argument — uses word deterministic or reproducible]."
  }},
  {{
    "id": "C2",
    "description": "...",
    "claim": "...",
    "proof_sketch": "..."
  }},
  {{
    "id": "C3",
    "description": "...",
    "claim": "...",
    "proof_sketch": "..."
  }}
]
```
"""

# ── Phase 3: HEP adversarial pressure ─────────────────────────────────────────

HEP_PHASE3_ASSESS = """\
You are running Phase 3 of the Hypothesis Elimination Protocol (HEP) — Evidence Assessment.

For each candidate hypothesis, assess its consistency against each piece of evidence.

Candidates:
{candidates_json}

Evidence:
{evidence_json}

For every (hypothesis, evidence) pair, determine:
  - consistency: "consistent" | "inconsistent"
  - weight: "decisive" | "strong" | "weak"
    * decisive — the evidence directly falsifies the hypothesis (irrebuttable)
    * strong   — creates substantial pressure that requires rebuttal
    * weak     — minor tension only
  - argument: one sentence explaining why

Return ONLY this JSON object, no commentary:
```json
{{
  "assessments": [
    {{
      "hypothesisid": "C1",
      "evidenceid": "E1",
      "consistency": "consistent",
      "weight": "weak",
      "argument": "..."
    }}
  ]
}}
```
"""

HEP_PHASE3_REBUTTAL = """\
You are evaluating a rebuttal attempt in the Hypothesis Elimination Protocol (HEP).

A "strong" inconsistency was found between a hypothesis and a piece of evidence.
The hypothesis must either refute the challenge or scope-narrow.

Hypothesis {hypothesis_id}:
{hypothesis_json}

Challenging evidence {evidence_id}: {evidence_description}

Assessor's argument: {assessment_argument}

Can the hypothesis survive this challenge?
  - "refutation"      — demonstrate the inconsistency assessment is incorrect
  - "scope_narrowing" — concede the point and explicitly narrow the scope of the claim

Return ONLY this JSON object:
```json
{{
  "hypothesisid": "{hypothesis_id}",
  "evidenceid": "{evidence_id}",
  "kind": "refutation",
  "argument": "one-sentence rebuttal",
  "valid": true,
  "limitationdescription": ""
}}
```
"""

# ── Phase 3: CFFP adversarial pressure ────────────────────────────────────────

CFFP_PHASE3_COUNTEREXAMPLE = """\
You are running Phase 3 of the Constraint-First Formalization Protocol (CFFP) — Counterexample Generation.

For each invariant, try to construct a counterexample that violates it for the given candidate.

Candidate:
{candidate_json}

Invariants to check:
{invariants_json}

For each invariant, determine whether the candidate's proof_sketch adequately addresses it.
If not, provide a concrete witness (counterexample input) that would violate the invariant.

Return ONLY this JSON object:
```json
{{
  "counterexamples": [
    {{
      "id": "CE1",
      "targetcandidate": "C1",
      "violates": "I1",
      "assessment": "no_violation_found",
      "witness": ""
    }},
    {{
      "id": "CE2",
      "targetcandidate": "C1",
      "violates": "I2",
      "assessment": "violation_found",
      "witness": "Concrete counterexample: ..."
    }}
  ]
}}
```
assessment values: "violation_found" | "no_violation_found"
"""

CFFP_PHASE3_REBUTTAL = """\
You are evaluating a rebuttal in the Constraint-First Formalization Protocol (CFFP).

A counterexample was constructed against candidate {candidate_id} for invariant {invariant_id}.

Candidate:
{candidate_json}

Counterexample {ce_id}: {witness}

Can the candidate refute this counterexample, or must it scope-narrow?

Return ONLY this JSON object:
```json
{{
  "candidateid": "{candidate_id}",
  "ceid": "{ce_id}",
  "kind": "refutation",
  "argument": "one-sentence rebuttal",
  "valid": true,
  "limitationdescription": ""
}}
```
"""

# ── Phase 5: Obligation Gate ───────────────────────────────────────────────────

OBLIGATION_GATE = """\
You are running the Obligation Gate (Phase 5) of a dialectic reasoning cycle.

For each surviving candidate, verify ALL four properties:
  - causal_sufficiency:     the claim fully explains the observed phenomenon
  - predictions_confirmed:  the proof_sketch is consistent with ALL listed evidence
  - scope_not_trivial:      the claim is specific, not a tautology or empty statement
  - no_background_conflict: the claim does not contradict known background facts

CONTEXT:
{context}

Return ONLY this JSON object, no commentary before or after:
```json
{{
  "obligations": [
    {{"candidateid": "C1", "property": "causal_sufficiency",     "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "predictions_confirmed",  "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "scope_not_trivial",      "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "no_background_conflict", "argument": "...", "satisfied": true}}
  ]
}}
```
"""

# ── Generic rebuttal ───────────────────────────────────────────────────────────

REBUTTAL = """\
You are evaluating a rebuttal for a dialectic challenge.

A challenge was raised against a candidate. The candidate must either:
  - REFUTE the challenge (show the pressure is incorrect)
  - SCOPE NARROW (concede the point and retreat from that scope)

CONTEXT:
{context}

Return ONLY this JSON object:
{{
  "kind": "refutation",
  "argument": "your rebuttal argument",
  "valid": true,
  "limitation_description": ""
}}
"""

# ── Registry ───────────────────────────────────────────────────────────────────

PROMPT_MAP = {
    "hep_attention":              HEP_ATTENTION,
    "cffp_attention":             CFFP_ATTENTION,
    "hep_phase3_assess":          HEP_PHASE3_ASSESS,
    "hep_phase3_rebuttal":        HEP_PHASE3_REBUTTAL,
    "cffp_phase3_counterexample": CFFP_PHASE3_COUNTEREXAMPLE,
    "cffp_phase3_rebuttal":       CFFP_PHASE3_REBUTTAL,
    "obligation_gate":            OBLIGATION_GATE,
    "rebuttal":                   REBUTTAL,
}


def get_prompt(name: str) -> str:
    if name not in PROMPT_MAP:
        raise KeyError(
            f"Unknown prompt: {name!r}. Available: {sorted(PROMPT_MAP)}"
        )
    return PROMPT_MAP[name]