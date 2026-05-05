"""
Attention Phase — LLM candidate generation.

Strategies for robust JSON extraction:
  1. Code-fenced JSON array
  2. Bare JSON array
  3. Degenerate single-object fallback
"""
from __future__ import annotations

import json
import re
import requests

from dial.residual_stream import ResidualStream
from dial.prompts import get_prompt


def attention_phase(
    stream: ResidualStream,
    problem: dict,
    protocol: str,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> ResidualStream:
    context = _build_context(stream, problem)
    prompt_key = "hep_attention" if protocol == "hep" else "cffp_attention"
    prompt = get_prompt(prompt_key).format(context=json.dumps(context, ensure_ascii=False, indent=2))

    raw = call_ollama(prompt, model, ollama_url)
    candidates = extract_json_array(raw)

    if not candidates:
        obj = extract_json_object(raw)
        if obj and "id" in obj:
            candidates = [obj]

    for i, c in enumerate(candidates[:3]):
        c.setdefault("id", f"C{i + 1}")

    stream.candidates = candidates[:3]
    return stream


def check_model(model: str, ollama_url: str = "http://localhost:11434") -> None:
    """
    Verify that *model* is available in the local Ollama instance.
    Raises RuntimeError with a helpful pull command if it is not.
    """
    try:
        resp = requests.get(ollama_url + "/api/tags", timeout=10)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach Ollama at {ollama_url}.\n"
            "Start it with:  ollama serve"
        )
    except Exception as exc:
        raise RuntimeError(f"Ollama /api/tags check failed: {exc}") from exc

    # Ollama stores tags like "qwen2.5:7b" or "llama3.1:8b"
    # Accept an exact match or a prefix match (e.g. "llama3.1:8b" matches "llama3.1:8b-instruct-q4_K_M")
    if not any(a == model or a.startswith(model.split(":")[0]) for a in available):
        pull_tag = model if ":" in model else f"{model}:latest"
        raise RuntimeError(
            f"Model '{model}' is not available in Ollama.\n"
            f"Pull it first:\n\n    ollama pull {pull_tag}\n\n"
            f"Models currently available: {available or '(none)'}"
        )


def call_ollama(
    prompt: str,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> str:
    try:
        resp = requests.post(
            ollama_url + "/api/generate",
            json={
                "model":   model,
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=180,
        )
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach Ollama at {ollama_url}.\n"
            "Start it with:  ollama serve"
        )

    if resp.status_code == 404:
        pull_tag = model if ":" in model else f"{model}:latest"
        raise RuntimeError(
            f"Ollama returned 404 for model '{model}'.\n"
            f"Pull it first:\n\n    ollama pull {pull_tag}\n"
        )

    resp.raise_for_status()
    return resp.json()["response"]


def extract_json_array(raw: str) -> list[dict]:
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
    return []


def extract_json_object(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"(\{.*\})", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {}


def _build_context(stream: ResidualStream, problem: dict) -> dict:
    return {
        "cycle":               stream.cycle,
        "problem":             problem,
        "eliminated_so_far":   stream.eliminated,
        "active_constraints":  stream.active_constraints,
        "scope_narrowings":    stream.scope_narrowings,
    }