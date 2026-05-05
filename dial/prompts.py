"""All 7 prompt templates. Literal JSON braces are doubled so .format() works."""

HEP_ATTENTION = """\
You are Phase 2 of the Hypothesis Elimination Protocol (HEP).

TASK: Generate 2-3 DISTINCT candidate hypotheses that causally explain the observed phenomenon.

CONTEXT:
{context}

RULES:
1. Each hypothesis MUST have: id (C1, C2...), description, claim, proof_sketch.
2. "claim" must be a falsifiable causal statement: "X causes Y because Z".
3. "proof_sketch" must cite which evidence items support it (E1, E2...).
4. RESPECT all active_constraints — do NOT regenerate eliminated claims.
5. If scope_narrowings is non-empty: address the narrowed scope OR focus on a different mechanism.
6. If eliminated_with_challenges is non-empty: each candidate must survive those specific challenges.

OUTPUT: strict JSON array only — no prose, no markdown fences.
[{{"id":"C1","description":"...","claim":"...","proof_sketch":"..."}}]
"""

CFFP_ATTENTION = """\
You are Phase 2 of the Constraint-First Formalization Protocol (CFFP).

TASK: Generate 2-3 DISTINCT candidate formalizations for the given construct.

CONTEXT:
{context}

RULES:
1. Each candidate MUST have: id (C1, C2...), description, claim, proof_sketch.
2. "claim" must describe formal structure: data types, evaluation rules, conflict resolution.
3. "proof_sketch" must explain how each declared invariant is satisfied.
4. RESPECT active_constraints — do NOT regenerate eliminated claims.
5. If eliminated_with_challenges is non-empty: candidates must withstand those counterexamples.

OUTPUT: strict JSON array only.
[{{"id":"C1","description":"...","claim":"...","proof_sketch":"..."}}]
"""

HEP_PHASE3_ASSESS = """\
You are Phase 3 of the Hypothesis Elimination Protocol (HEP) — Evidence Assessor.

TASK: For each (hypothesis, evidence) pair, produce an EvidenceAssessment.

HYPOTHESES:
{candidates_json}

EVIDENCE:
{evidence_json}

DEFINITIONS:
- "consistent":    the hypothesis predicts or accommodates this observation
- "inconsistent":  the hypothesis predicts this observation would NOT occur
- "uninformative": the evidence does not discriminate between hypotheses

WEIGHT:
- "decisive": inconsistency is logically certain — NO rebuttal permitted, eliminate immediately
- "strong":   inconsistency is clear but a rebuttal argument could exist
- "weak":     inconsistency is plausible but uncertain — record as pressure only

Assess ALL (hypothesis x evidence) pairs. Output every pair, even uninformative ones.

OUTPUT (strict JSON only):
{{
  "assessments": [
    {{
      "hypothesisid": "C1",
      "evidenceid": "E1",
      "consistency": "inconsistent",
      "weight": "decisive",
      "argument": "C1 claims X causes Y, but E1 shows Y was absent when X was present."
    }}
  ]
}}
"""

HEP_PHASE3_REBUTTAL = """\
You are the advocate for hypothesis {hypothesis_id} in Phase 3 HEP — Rebuttal Generator.

HYPOTHESIS:
{hypothesis_json}

CHALLENGE (strong inconsistency):
Evidence ID: {evidence_id}
Evidence: {evidence_description}
Assessment argument: {assessment_argument}

Respond with ONE rebuttal kind:
1. "refutation"            — the inconsistency assessment is WRONG.
2. "scopenarrowing"        — hypothesis WITHDRAWS its claim to cover these conditions.
                             Always valid=true. Record what scope is excluded.
3. "evidenceunreliability" — the evidence itself is unreliable or contaminated.

OUTPUT (strict JSON only):
{{
  "hypothesisid": "{hypothesis_id}",
  "evidenceid": "{evidence_id}",
  "kind": "refutation",
  "argument": "...",
  "valid": true,
  "limitationdescription": "if scopenarrowing: what scope excluded, else null"
}}
"""

CFFP_PHASE3_COUNTEREXAMPLE = """\
You are Phase 3 of the Constraint-First Formalization Protocol (CFFP) — Counterexample Generator.

TASK: For each candidate x invariant pair, find a MINIMAL counterexample.

CANDIDATE:
{candidate_json}

INVARIANTS TO TEST:
{invariants_json}

RULES:
- Minimal means: no proper sub-case also demonstrates the violation.
- If no counterexample found -> assessment: "no_violation".
- Describe the minimal witness case precisely: input, steps, observed violation.

OUTPUT (strict JSON only):
{{
  "counterexamples": [
    {{
      "id": "CE1",
      "targetcandidate": "C1",
      "violates": "I1",
      "witness": "Rule R1 fires only if R1 has not fired. Under left-to-right order R1 loops.",
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
"""

CFFP_PHASE3_REBUTTAL = """\
You are the advocate for formalism {candidate_id} in Phase 3 CFFP — Rebuttal Generator.

CANDIDATE:
{candidate_json}

COUNTEREXAMPLE CHALLENGE:
Counterexample ID: {ce_id}
Invariant violated: {invariant_id}
Witness: {witness}

Respond with ONE rebuttal kind:
1. "refutation"     — counterexample is INVALID.
2. "scopenarrowing" — formalism withdraws claim to cover this witness. Always valid=true.
3. "reformulation"  — invariant satisfied with a minor fix. Describe fix precisely.

OUTPUT (strict JSON only):
{{
  "candidateid": "{candidate_id}",
  "ceid": "{ce_id}",
  "kind": "refutation",
  "argument": "...",
  "valid": true,
  "limitationdescription": "if scopenarrowing: what scope excluded, else null"
}}
"""

OBLIGATION_GATE = """\
You are Phase 5 of the Hypothesis Elimination Protocol — the Obligation Gate.

A survivor passed Phase 3 pressure. Before adopting as x*, verify 4 obligations.
Be strict — false adoption is worse than an open outcome.

SURVIVOR:
{survivor_json}

ALL CANDIDATES (for cross-comparison):
{candidates_json}

PROBLEM CONTEXT:
{problem_json}

Evaluate each obligation:
1. causal_sufficiency:     Is survivor's cause sufficient to produce the observation?
2. predictions_confirmed:  Do proof_sketch predictions align with evidence?
3. scope_not_trivial:      Are scope narrowings not so severe they reduce to trivial?
4. no_background_conflict: Does survivor contradict established background knowledge?

OUTPUT (strict JSON only):
{{
  "candidateid": "C1",
  "obligations": [
    {{
      "property": "causal_sufficiency",
      "argument": "...",
      "satisfied": true,
      "blocker": null
    }}
  ],
  "allsatisfied": true
}}

If allsatisfied=false, the run does NOT close.
"""

_REGISTRY = {
    "hep_attention": HEP_ATTENTION,
    "cffp_attention": CFFP_ATTENTION,
    "hep_phase3_assess": HEP_PHASE3_ASSESS,
    "hep_phase3_rebuttal": HEP_PHASE3_REBUTTAL,
    "cffp_phase3_counterexample": CFFP_PHASE3_COUNTEREXAMPLE,
    "cffp_phase3_rebuttal": CFFP_PHASE3_REBUTTAL,
    "obligation_gate": OBLIGATION_GATE,
}


def get_prompt(name: str) -> str:
    if name not in _REGISTRY:
        raise KeyError(f"Prompt '{name}' not found. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]
