"""Suggestion service supporting heuristic + optional OpenAI model.

Environment toggle:
  - If OPENAI_API_KEY is set and mode == "llm" (or SUGGEST_MODE env var == llm),
    attempt OpenAI JSON span extraction (model default: gpt-4o-mini or gpt-3.5-turbo fallback).
  - On any failure (timeout, bad JSON, API error) gracefully fallback to heuristics.

Return shape for each suggestion:
  {start:int, end:int, text:str, type:str, confidence:float, source:str, model?:str}
"""
from __future__ import annotations
import os
import json
import time
import re
from typing import List, Dict, Any, Callable

try:  # soft import; absence keeps heuristics functional
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - openai not installed path
    OpenAI = None  # type: ignore

MED_KEYWORDS = {"amlodipine", "lisinopril", "budesonide", "montelukast", "prednisone", "metformin", "insulin"}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def heuristic_suggest(text: str, existing_spans: List[tuple[int, int]]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    occupied = set()
    for s, e in existing_spans:
        occupied.update(range(s, e))

    lowered = text.lower()
    for kw in MED_KEYWORDS:
        start = 0
        while True:
            idx = lowered.find(kw, start)
            if idx == -1:
                break
            end = idx + len(kw)
            if not _overlaps(idx, end, occupied):
                suggestions.append({
                    "start": idx,
                    "end": end,
                    "text": text[idx:end],
                    "type": "Medication",
                    "confidence": 0.9,
                    "source": "heuristic-med"
                })
            start = end

    for m in WORD_RE.finditer(text):
        token = m.group(0)
        if not token[0].isupper():
            continue
        s, e = m.span()
        if _overlaps(s, e, occupied):
            continue
        if any(sug["start"] == s and sug["end"] == e for sug in suggestions):
            continue
        suggestions.append({
            "start": s,
            "end": e,
            "text": token,
            "type": "Disease",
            "confidence": 0.5,
            "source": "heuristic-cap"
        })

    uniq = {}
    for s in suggestions:
        uniq[(s["start"], s["end"], s["type"])] = s
    return sorted(uniq.values(), key=lambda x: (x["start"], -(x.get("confidence", 0))))


def openai_suggest(text: str, existing_spans: List[tuple[int, int]]) -> List[Dict[str, Any]]:
    if OpenAI is None:
        raise RuntimeError("openai library not available")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    # Build instruction prompt asking for JSON list of spans
    instruction = (
        "Extract medically relevant entity spans from the TEXT. Return a JSON list where each item has: start, end, text, type (Disease|Medication|Symptom|Procedure), confidence (0-1). "
        "Do not include entities that overlap these existing spans: " + 
        ",".join(f"{s}-{e}" for s, e in existing_spans) + ". "
        "Respond ONLY with JSON (array)."
    )
    model = os.getenv("OPENAI_SUGGEST_MODEL", "gpt-4o-mini")
    start_ts = time.time()
    try:
        # Use responses API (new client) or fallback to chat.completions if needed
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": "You are an assistant that outputs only JSON."},
                    {"role": "user", "content": instruction + "\nTEXT:\n" + text}
                ],
                max_output_tokens=800,
            )
            raw = resp.output_text  # type: ignore[attr-defined]
        except Exception:  # fallback older API
            chat = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an assistant that outputs only JSON."},
                    {"role": "user", "content": instruction + "\nTEXT:\n" + text}
                ],
                temperature=0.1,
            )
            raw = chat.choices[0].message.content  # type: ignore
        parsed = json.loads(raw)
        out: List[Dict[str, Any]] = []
        occupied = set()
        for s, e in existing_spans:
            occupied.update(range(s, e))
        for item in parsed:
            try:
                s = int(item["start"])  # type: ignore
                e = int(item["end"])    # type: ignore
                if s < 0 or e <= s or e > len(text):
                    continue
                if _overlaps(s, e, occupied):
                    continue
                snippet = text[s:e]
                if snippet != item.get("text", snippet):
                    # enforce text integrity
                    continue
                etype = item.get("type", "Disease")
                conf = float(item.get("confidence", 0.7))
                out.append({
                    "start": s,
                    "end": e,
                    "text": snippet,
                    "type": etype,
                    "confidence": max(0.0, min(conf, 1.0)),
                    "source": "openai",
                    "model": model
                })
            except Exception:
                continue
        # If model returns nothing, raise to trigger fallback.
        if not out:
            raise RuntimeError("empty llm output")
        return out
    finally:
        duration = (time.time() - start_ts) * 1000
        print(f"[llm] model={model} ms={duration:.1f}")


def suggest_entities_with_mode(text: str, existing_spans: List[tuple[int, int]], mode: str | None = None) -> List[Dict[str, Any]]:
    mode = (mode or os.getenv("SUGGEST_MODE") or "heuristic").lower()
    if mode == "llm":
        try:
            llm_sugs = openai_suggest(text, existing_spans)
            heuristic = heuristic_suggest(text, existing_spans)
            return _merge(heuristic, llm_sugs)
        except Exception as e:  # graceful fallback
            print(f"[llm-fallback] reason={e}")
            return heuristic_suggest(text, existing_spans)
    return heuristic_suggest(text, existing_spans)

# Backwards compatible signature (tests import this) defaults to heuristic only.
def suggest_entities(text: str, existing_spans: List[tuple[int, int]]) -> List[Dict[str, Any]]:  # pragma: no cover
    return heuristic_suggest(text, existing_spans)


def _merge(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key = {(s["start"], s["end"], s["type"]): s for s in primary}
    for s in secondary:
        key = (s["start"], s["end"], s["type"])
        if key not in by_key:
            by_key[key] = s
    return sorted(by_key.values(), key=lambda x: (x["start"], -(x.get("confidence", 0))))


def _overlaps(s: int, e: int, occupied: set[int]) -> bool:
    for i in range(s, e):
        if i in occupied:
            return True
    return False
