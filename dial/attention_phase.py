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


def call_ollama(
    prompt: str,
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> str:
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