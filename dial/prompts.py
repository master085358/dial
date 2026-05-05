"""Prompt templates embedded as module constants."""

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
    "proof_sketch": "I1: [termination argument uses word terminates/finite]. I2: [determinism argument uses word deterministic/reproducible]."
  }}
]
```
"""

OBLIGATION_GATE = """\
You are running the Obligation Gate (Phase 5) of a dialectic reasoning cycle.

For each surviving candidate, verify ALL four properties hold:
  - causal_sufficiency: the claim fully explains the observed phenomenon
  - predictions_confirmed: the proof_sketch is consistent with ALL listed evidence items
  - scope_not_trivial: the claim is specific and not a tautology
  - no_background_conflict: the claim does not contradict known background facts

CONTEXT:
{context}

OUTPUT FORMAT — strict JSON only, no commentary before or after:
```json
{{
  "obligations": [
    {{"candidateid": "C1", "property": "causal_sufficiency",    "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "predictions_confirmed", "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "scope_not_trivial",     "argument": "...", "satisfied": true}},
    {{"candidateid": "C1", "property": "no_background_conflict","argument": "...", "satisfied": true}}
  ]
}}
```
"""

REBUTTAL = """\
You are evaluating a rebuttal for a dialectic challenge.

A challenge was raised against a candidate. The candidate must either:
  - REFUTE the challenge (show the pressure is incorrect)
  - SCOPE NARROW (concede the point and retreat from that scope)

CONTEXT:
{context}

Respond with JSON:
{{
  "kind": "refutation" | "scope_narrowing",
  "argument": "your rebuttal argument",
  "valid": true | false,
  "limitation_description": "what scope was excluded (only if scope_narrowing)"
}}
"""

PROMPT_MAP = {
    "hep_attention":   HEP_ATTENTION,
    "cffp_attention":  CFFP_ATTENTION,
    "obligation_gate": OBLIGATION_GATE,
    "rebuttal":        REBUTTAL,
}


def get_prompt(name: str) -> str:
    if name not in PROMPT_MAP:
        raise KeyError(f"Unknown prompt: {name!r}. Available: {list(PROMPT_MAP)}")
    return PROMPT_MAP[name]