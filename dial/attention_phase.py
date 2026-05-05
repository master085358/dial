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

    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=180,
        )
    except requests.RequestException as e:
        raise RuntimeError(
            f"Ollama request failed for model '{model}' at {OLLAMA_GENERATE_URL}: {e}"
        ) from e

    if response.status_code != 200:
        body = response.text.strip()
        raise RuntimeError(
            f"Ollama generate failed with HTTP {response.status_code} "
            f"for model '{model}'. Response body: {body}"
        )

    try:
        raw = response.json()["response"]
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse Ollama JSON response for model '{model}': {response.text[:500]}"
        ) from e

    stream.candidates = _extract_json_candidates(raw)
    return stream


def _extract_json_candidates(raw: str) -> list[dict]:
    """Robustly extract a JSON array of candidates from raw LLM output."""
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return [{
        "id": "C1",
        "description": raw[:200],
        "claim": raw[:200],
        "proof_sketch": "extracted from raw LLM output — parsing failed",
    }]