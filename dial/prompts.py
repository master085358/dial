"""
Prompt templates embedded as module constants.
Using importlib.resources is overkill for MVP — strings are simpler and always work.
"""

HEP_ATTENTION = """\
You are running Phase 2 of the Hypothesis Elimination Protocol (HEP).

Your task: generate candidate hypotheses that causally explain the observed phenomenon.

CONTEXT:
{context}

RULES:
1. Generate 2-3 DISTINCT hypotheses as a JSON array.
2. Each hypothesis MUST have exactly these keys: id (C1, C2...), description, claim, proof_sketch.
3. proof_sketch must explain WHY the hypothesis is plausible given the evidence listed in context.problem.evidence.
4. Do NOT repeat hypotheses from context.eliminated_so_far.
5. Respect all strings in context.active_constraints — they are hard constraints from the CUE phase.
6. If context.cycle > 0: your previous candidates failed CUE validation — generate stronger, more evidence-grounded ones.
7. claim must be a full causal statement: "X causes Y because Z".

OUTPUT FORMAT — strict JSON only, no commentary before or after:
```json
[
  {{
    "id": "C1",
    "description": "Short hypothesis name",
    "claim": "Full causal claim: X causes Y because Z",
    "proof_sketch": "Evidence that supports this hypothesis: ..."
  }}
]
```

PHENOMENON TO EXPLAIN: see context.problem.phenomenon
EVIDENCE: see context.problem.evidence
"""

CFFP_ATTENTION = """\
You are running Phase 2 of the Constraint-First Formalization Protocol (CFFP).

Your task: generate candidate formalisms for the construct under design.

CONTEXT:
{context}

RULES:
1. Generate 2-3 DISTINCT candidate formalisms as a JSON array.
2. Each formalism MUST have exactly: id, description, claim, proof_sketch.
3. claim must be a formal statement including: structure, evaluation_rule, resolution_rule.
4. proof_sketch MUST explicitly address EVERY invariant in context.problem.invariants.
   - Address "termination" with the word "terminates" or "finite".
   - Address "determinism" with the word "deterministic" or "reproducible".
5. Do NOT repeat approaches from context.eliminated_so_far.
6. Respect all strings in context.active_constraints.
7. If context.cycle > 0: previous candidates failed invariant checks — strengthen the proof_sketch.

OUTPUT FORMAT — strict JSON only:
```json
[
  {{
    "id": "C1",
    "description": "Formalism name",
    "claim": "structure: ... | evaluation_rule: ... | resolution_rule: ...",
    "proof_sketch": "I1: [termination argument]. I2: [determinism argument]."
  }}
]
```

CONSTRUCT TO FORMALIZE: see context.problem.construct
INVARIANTS: see context.problem.invariants
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
    "hep_attention": HEP_ATTENTION,
    "cffp_attention": CFFP_ATTENTION,
    "rebuttal": REBUTTAL,
}


def get_prompt(name: str) -> str:
    if name not in PROMPT_MAP:
        raise KeyError(f"Unknown prompt: {name!r}. Available: {list(PROMPT_MAP)}")
    return PROMPT_MAP[name]
