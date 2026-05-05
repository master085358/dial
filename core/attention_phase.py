import json
import re
import requests
from pathlib import Path

from .residual_stream import ResidualStream

OLLAMA_URL = "http://localhost:11434/api/generate"


def load_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    return path.read_text()


def attention_phase(
    stream: ResidualStream,
    problem: dict,
    protocol: str,
    model: str = "llama3.1:8b",
) -> ResidualStream:
    """Phase A — LLM as Attention mechanism."""
    prompt_template = load_prompt(f"{protocol}_attention")

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

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 2048},
        },
        timeout=120,
    )
    response.raise_for_status()
    raw = response.json()["response"]
    stream.candidates = _extract_json_candidates(raw)
    return stream


def _extract_json_candidates(raw: str) -> list[dict]:
    """Robustly extract a JSON array of candidates from raw LLM output."""
    # Strategy 1: markdown code fence
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Strategy 2: bare JSON array
    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback
    return [{
        "id": "C1",
        "description": raw[:200],
        "claim": raw[:200],
        "proof_sketch": "extracted from raw LLM output — parsing failed",
    }]
