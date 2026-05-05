"""Prompt templates — v3: calibrated weight definitions + rebuttal pipeline."""

# ── Phase A: Attention ─────────────────────────────────────────────────────────

HEP_ATTENTION = """\
You are running Phase 2 of the Hypothesis Elimination Protocol (HEP).
Generate candidate hypotheses that causally explain the observed phenomenon.

CONTEXT:
{context}

RULES:
1. Generate EXACTLY 3 DISTINCT hypotheses as a JSON array.
2. Each hypothesis MUST have: id (C1/C2/C3), description, claim, proof_sketch.
3. proof_sketch must reference specific evidence items from context.problem.evidence.
4. Do NOT repeat hypotheses from context.eliminated_so_far.
5. Respect ALL strings in context.active_constraints — hard constraints from CUE.
6. If context.cycle > 0: previous candidates FAILED — generate stronger, more specific ones.
7. claim format: "X causes Y because Z"

OUTPUT FORMAT — STRICT JSON ARRAY ONLY, no text before or after:
```json
[
  {{
    "id": "C1",
    "description": "Short hypothesis name",
    "claim": "X causes Y because Z",
    "proof_sketch": "References to specific evidence items: ..."
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
Generate candidate formalisms for the construct under design.

CONTEXT:
{context}

RULES:
1. Generate EXACTLY 3 DISTINCT candidate formalisms as a JSON array.
2. Each formalism MUST have: id, description, claim, proof_sketch.
3. claim must be a formal statement with: structure, evaluation_rule, resolution_rule.
4. proof_sketch MUST explicitly address EVERY invariant in context.problem.invariants:
   - For class "termination": use the word "terminates" or "finite"
   - For class "determinism": use "deterministic" or "reproducible" — NEVER use "random"
5. Do NOT repeat approaches from context.eliminated_so_far.
6. Respect ALL strings in context.active_constraints.

OUTPUT FORMAT — STRICT JSON ARRAY ONLY, no text before or after:
```json
[
  {{
    "id": "C1",
    "description": "Formalism name",
    "claim": "structure: ... | evaluation_rule: ... | resolution_rule: ...",
    "proof_sketch": "I1: [termination argument]. I2: [determinism argument]."
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

# ── Phase 3 HEP: Evidence Assessment (CALIBRATED v3) ─────────────────────────

HEP_PHASE3_ASSESS = """\
You are Phase 3 of the Hypothesis Elimination Protocol (HEP) — Evidence Assessment.
Evaluate how each piece of evidence relates to each hypothesis.

PHENOMENON:
{phenomenon}

HYPOTHESES:
{candidates_json}

EVIDENCE:
{evidence_json}

═══════════════════════════════════════════════════════
WEIGHT DEFINITIONS — READ CAREFULLY BEFORE SCORING
═══════════════════════════════════════════════════════

"decisive" — USE ONLY when the evidence makes the hypothesis LOGICALLY IMPOSSIBLE.
  The hypothesis predicts this observation would NOT occur, yet it did occur.
  No argument could save the hypothesis — elimination is immediate, no rebuttal permitted.

  DECISIVE examples (these qualify):
  ✓ Evidence "Database query time unchanged" + Hypothesis "DB slowdown caused latency"
    → decisive: if DB did not slow, it cannot be the latency cause.
  ✓ Evidence "Regression reproduced on isolated benchmark (no network/external deps)"
    + Hypothesis "Network packet loss caused latency"
    → decisive: isolated benchmark physically eliminates network as explanation.
  ✓ Evidence "Metric X was zero throughout" + Hypothesis "X spike caused Y"
    → decisive: X cannot cause Y if X never changed.

  NOT decisive (do NOT use decisive here):
  ✗ Evidence "Network changed Feb 19" + Hypothesis "Network caused latency"
    → NOT decisive. Chronological sequence is COMPATIBLE: the change could have
       taken effect with the deployment on Feb 20. Use "strong" or "uninformative".
  ✗ Evidence "Memory increased 15%" + Hypothesis "Network caused latency"
    → NOT decisive. Memory and network causes are independent; one doesn't rule out the other.
       Use "weak" or "uninformative".
  ✗ Evidence "Event X happened" + Hypothesis "Y caused Z" where X is unrelated to Y or Z
    → NOT decisive. Merely uninformative.
  ✗ Any case where a valid rebuttal MIGHT exist → use "strong", not "decisive".

"strong" — USE when evidence creates real pressure against the hypothesis,
  but a rebuttal argument could plausibly exist.
  The hypothesis is implausible given this evidence, but not logically impossible.

  STRONG examples:
  ✓ Evidence "Memory increased 15%" + Hypothesis "Network topology caused latency"
    → strong: memory increase is unexpected if only network changed, but not impossible.
  ✓ Evidence "Isolated benchmark reproduces regression" + Hypothesis "Memory leak caused latency"
    → strong: isolated benchmark suggests environment-independent cause, consistent with
       memory but adds pressure. A rebuttal is possible.

"weak" — USE when evidence is marginally inconsistent or ambiguous.
  Inconsistency is noted but not eliminatory on its own.

  WEAK examples:
  ✓ Evidence "Deployment happened Feb 20" + Hypothesis "Memory leak caused latency"
    → weak: deployment timing is consistent with many causes.

"uninformative" — USE when evidence does not discriminate between hypotheses.
  It is consistent with the hypothesis OR equally consistent with all hypotheses.

═══════════════════════════════════════════════════════
DEFAULT RULES when uncertain:
  - Uncertain between decisive and strong → use "strong"
  - Uncertain between weak and uninformative → use "uninformative"
  - Chronological sequences are NEVER decisive unless the timeline is logically impossible
═══════════════════════════════════════════════════════

OUTPUT (strict JSON, no other text):
```json
{{
  "assessments": [
    {{
      "hypothesisid": "C1",
      "evidenceid": "E1",
      "consistency": "consistent",
      "weight": "weak",
      "argument": "one sentence: WHY this assessment holds"
    }}
  ],
  "cross_support": [
    {{
      "supported": "C2",
      "pressured": "C1",
      "evidenceid": "E3",
      "argument": "why E3 relatively supports C2 over C1"
    }}
  ]
}}
```

RULES:
- Produce exactly one assessment per (hypothesisid, evidenceid) pair
- If consistency=inconsistent: weight MUST be decisive/strong/weak — choose carefully per definitions above
- If consistency=consistent or uninformative: set weight="weak" (ignored)
- DEFAULT TO "strong" when unsure between decisive and strong
- DEFAULT TO "uninformative" when unsure between weak and uninformative
"""

# ── Phase 3 HEP: Rebuttal (v3 — three-option rebuttal) ───────────────────────

HEP_PHASE3_REBUTTAL = """\
You are the advocate for hypothesis {hypothesis_id} in Phase 3 of HEP.
A "strong" (NOT decisive) inconsistency has been raised against you.
You have the right to rebut it.

HYPOTHESIS:
{hypothesis_json}

CHALLENGE:
  Evidence ID: {evidence_id}
  Evidence:    {evidence_description}
  Assessment:  {assessment_argument}

═══════════════════════════════════════
REBUTTAL OPTIONS — choose exactly one:
═══════════════════════════════════════

1. "refutation" — The inconsistency assessment is WRONG.
   The hypothesis IS consistent with this evidence under correct analysis.
   You must explain why the assessor made an error.
   If valid: the assessment is dismissed, the hypothesis survives without limitation.

2. "scopenarrowing" — The hypothesis CONCEDES the point.
   It withdraws its claim to cover the CONDITIONS under which this evidence was gathered.
   The hypothesis SURVIVES, but with a recorded limitation.
   scopenarrowing is ALWAYS valid=true by definition — you are conceding, not disputing.
   The limitation_description becomes an acknowledged_limitation in the final x*.
   Example: "This hypothesis applies only to deployments without concurrent
             infrastructure changes. Concurrent changes are out of scope."

3. "evidenceunreliability" — The EVIDENCE ITSELF is unreliable.
   The assessment is voided because the evidence is contaminated or methodologically flawed.
   If valid: the evidence is removed from pressure consideration.

CHOOSING:
- Prefer "refutation" if the assessment was logically wrong
- Prefer "scopenarrowing" if the evidence reveals a genuine boundary of your hypothesis
- Prefer "evidenceunreliability" only if evidence is clearly flawed

OUTPUT (strict JSON):
```json
{{
  "hypothesisid": "{hypothesis_id}",
  "evidenceid": "{evidence_id}",
  "kind": "refutation",
  "argument": "your rebuttal argument",
  "valid": true,
  "limitationdescription": ""
}}
```

NOTE: If kind="scopenarrowing" → valid MUST be true. The hypothesis survives with the limitation recorded.
"""

# ── Phase 3 CFFP: Counterexample (v3) ─────────────────────────────────────────

CFFP_PHASE3_COUNTEREXAMPLE = """\
You are Phase 3 of the Constraint-First Formalization Protocol (CFFP).
Find MINIMAL counterexamples against each candidate formalism.

CANDIDATE FORMALISMS:
{candidates_json}

INVARIANTS TO TEST:
{invariants_json}

For each (candidate, invariant) pair, find a MINIMAL counterexample —
a concrete case where the candidate's formalism VIOLATES the invariant.

MINIMALITY RULE: A counterexample must be minimal — no proper sub-case also demonstrates
the violation. A non-minimal counterexample is inadmissible.

TERMINATION (class: termination):
Look for: cases where evaluation does not halt.
Examples: self-referential rules, circular dependencies, infinite loops.
If the candidate explicitly handles these → assessment="no_violation".

DETERMINISM (class: determinism):
Look for: cases where same inputs produce different orders.
Examples: non-deterministic tie-breaking, parallel evaluation paths,
hash-based ordering without stable sort.

IMPORTANT: If the candidate's proof_sketch explicitly addresses the invariant class
using the required keywords (terminates/finite for termination; deterministic/reproducible
for determinism) → prefer assessment="no_violation" over "violation_found".

OUTPUT (strict JSON):
```json
{{
  "counterexamples": [
    {{
      "id": "CE1",
      "targetcandidate": "C1",
      "violates": "I1",
      "witness": "Minimal concrete case: ...",
      "minimal": true,
      "assessment": "violation_found"
    }},
    {{
      "id": "CE2",
      "targetcandidate": "C1",
      "violates": "I2",
      "witness": null,
      "minimal": false,
      "assessment": "no_violation"
    }}
  ]
}}
```

assessment values: "violation_found" | "no_violation" | "uncertain"
Prefer "no_violation" over "uncertain" when the candidate explicitly addresses the invariant.
"""

# ── Phase 3 CFFP: Rebuttal (v3) ───────────────────────────────────────────────

CFFP_PHASE3_REBUTTAL = """\
You are the formalism advocate in Phase 3 of CFFP.
A counterexample has been raised against your candidate formalism.

YOUR CANDIDATE:
{candidate_json}

COUNTEREXAMPLE RAISED:
{counterexample_json}

INVARIANT BEING TESTED:
{invariant_json}

═══════════════════════════════════════
REBUTTAL OPTIONS — choose exactly one:
═══════════════════════════════════════

1. "refutation" — The counterexample is WRONG.
   The candidate's formalism DOES satisfy the invariant in the claimed case.
   Show why the witness is not a valid counterexample.
   If valid: counterexample dismissed, candidate fully survives.

2. "scopenarrowing" — The formalism CONCEDES the case.
   The counterexample IS valid, but the formalism explicitly excludes
   this case from its claimed scope.
   The formalism survives with a recorded limitation.
   limitation_description becomes an acknowledged_limitation in Phase 6.
   scopenarrowing is ALWAYS valid=true by definition.
   Example: "This formalism applies only to acyclic rule sets.
             Self-referential rules are out of scope."

CHOOSING:
- Prefer "refutation" if the proof_sketch already handles the witness case
- Prefer "scopenarrowing" if the witness is a genuine boundary condition

OUTPUT (strict JSON):
```json
{{
  "candidateid": "C1",
  "counterexampleid": "CE1",
  "kind": "refutation",
  "argument": "your rebuttal argument",
  "valid": true,
  "limitationdescription": ""
}}
```

NOTE: kind="scopenarrowing" → valid MUST be true.
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

# ── Generic rebuttal (fallback) ────────────────────────────────────────────────

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