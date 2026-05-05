from __future__ import annotations
import json, os, re
import requests
from dial.residual_stream import ResidualStream
from dial.prompts import get_prompt


def _ollama_url() -> str:
    base = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not base.startswith("http"):
        base = f"http://{base}"
    return f"{base}/api/generate"


def call_ollama(prompt: str, model: str, timeout: int = 180) -> str:
    url = _ollama_url()
    try:
        resp = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.3, "num_predict": 2048}},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Ollama request to {url} failed: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama HTTP {resp.status_code} for model '{model}': {resp.text[:400]}"
        )
    try:
        return resp.json()["response"]
    except Exception as exc:
        raise RuntimeError(f"Failed to parse Ollama response: {resp.text[:400]}") from exc


def extract_json_object(raw: str) -> dict:
    for pattern in [r"```(?:json)?\s*({.*?})\s*```", r"({.*})"]:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return {}


def extract_json_array(raw: str) -> list[dict]:
    for pattern in [r"```(?:json)?\s*(\[.*?\])\s*```", r"(\[.*\])"]:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return [{"id": "C1", "description": raw[:200], "claim": raw[:200],
             "proof_sketch": "raw fallback — JSON parsing failed"}]


def attention_phase(
    stream: ResidualStream,
    problem: dict,
    protocol: str,
    model: str = "llama3.1:8b",
) -> ResidualStream:
    context = {
        "problem": problem,
        "cycle": stream.cycle,
        "active_constraints": stream.active_constraints,
        "scope_narrowings": stream.scope_narrowings,
        "eliminated_with_challenges": stream.eliminated_with_challenges,
        "eliminated_so_far": [
            {"id": e["candidateid"], "reason": e["reason"]}
            for e in stream.eliminated
        ],
    }
    prompt = get_prompt(f"{protocol}_attention").format(
        context=json.dumps(context, ensure_ascii=False, indent=2)
    )
    raw = call_ollama(prompt, model)
    stream.candidates = extract_json_array(raw)
    stream.stats.llm_calls += 1
    stream.stats.total_candidates += len(stream.candidates)
    return stream