import json
import os
import re

import requests

from dial.prompts import get_prompt
from dial.residual_stream import ResidualStream


OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not OLLAMA_URL.startswith("http://") and not OLLAMA_URL.startswith("https://"):
    OLLAMA_URL = f"http://{OLLAMA_URL}"
OLLAMA_GENERATE_URL = f"{OLLAMA_URL}/api/generate"


def call_ollama(prompt: str, model: str, temperature: float = 0.3) -> str:
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 2048},
            },
            timeout=180,
        )
    except requests.RequestException as e:
        raise RuntimeError(
            f"Ollama request failed for model '{model}' at {OLLAMA_GENERATE_URL}: {e}"
        ) from e

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama HTTP {response.status_code} for model '{model}': {response.text[:300]}"
        )
    try:
        return response.json()["response"]
    except Exception as e:
        raise RuntimeError(f"Failed to parse Ollama response: {response.text[:300]}") from e


def extract_json_object(raw: str) -> dict:
    """Extract the first JSON object or array from raw LLM output."""
    # Try code-fenced object/array
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare object
    match = re.search(r"(\{.*\})", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare array → wrap
    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group(1))
            return {"items": arr} if isinstance(arr, list) else arr
        except json.JSONDecodeError:
            pass
    return {}


def attention_phase(
    stream: ResidualStream,
    problem: dict,
    protocol: str,
    model: str = "llama3.1:8b",
) -> ResidualStream:
    """Phase A — LLM as Attention mechanism."""
    prompt_template = get_prompt(f"{protocol}_attention")

    context = {
        "problem": problem,
        "cycle": stream.cycle,
        "active_constraints": stream.active_constraints,
        "scope_narrowings": stream.scope_narrowings,
        "eliminated_so_far": [
            {"id": e["candidateid"], "reason": e["reason"]}
            for e in stream.eliminated
        ],
        "instruction": (
            "Generate hypothesis candidates as a JSON array. "
            "Each candidate MUST have: id, description, claim, proof_sketch. "
            "Avoid claims already eliminated. Respect all active_constraints."
        ),
    }

    full_prompt = prompt_template.format(
        context=json.dumps(context, ensure_ascii=False, indent=2)
    )

    raw = call_ollama(full_prompt, model)
    stream.candidates = _extract_json_candidates(raw)
    return stream


def _extract_json_candidates(raw: str) -> list[dict]:
    """
    Robustly extract a JSON array of candidates from raw LLM output.
    Three strategies, in order of preference:
      1. Code-fenced ```json [...] ```
      2. Bare JSON array [...] anywhere in text
      3. Return [] — signals parse failure to caller (triggers revision loop)
         *** NEVER return a degenerate single candidate ***
         A degenerate candidate would be re-eliminated forever, preventing convergence.
    """
    # Strategy 1: code fence
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if match:
        try:
            candidates = json.loads(match.group(1))
            if isinstance(candidates, list) and candidates:
                return candidates
        except json.JSONDecodeError:
            pass

    # Strategy 2: bare array (greedy — handles nested objects)
    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        try:
            candidates = json.loads(match.group(1))
            if isinstance(candidates, list) and candidates:
                # Validate each item has required keys
                required = {"id", "description", "claim", "proof_sketch"}
                valid = [c for c in candidates if required.issubset(c.keys())]
                if valid:
                    return valid
        except json.JSONDecodeError:
            pass

    # Strategy 3: parse failure → return empty list
    # cycle_runner detects [] and fires the Revision Loop with better constraints
    return []