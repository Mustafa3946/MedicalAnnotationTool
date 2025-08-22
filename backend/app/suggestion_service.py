"""Lightweight heuristic suggestion service (stub for future LLM integration).

Strategy (intentionally simple to avoid overkill):
- Tokenize on whitespace / punctuation.
- Capture:
  * Capitalized multi-letter words (possible Diseases / Procedures)
  * Known medication keywords list occurrences (exact, case-insensitive)
- Avoid duplicating existing annotated spans.
- Return candidate spans with a guessed type.

Future extension points:
- Replace heuristics with call to local LLM or remote API.
- Add scoring / confidence.
- Provide relation suggestions.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any

MED_KEYWORDS = {"amlodipine", "lisinopril", "budesonide", "montelukast", "prednisone", "metformin", "insulin"}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def suggest_entities(text: str, existing_spans: List[tuple[int,int]]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    occupied = set()
    for s,e in existing_spans:
        occupied.update(range(s,e))

    # Medication keyword matches (case-insensitive exact token match)
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

    # Capitalized words (simple heuristic for Disease / Procedure / Symptom candidates)
    for m in WORD_RE.finditer(text):
        token = m.group(0)
        if not token[0].isupper():
            continue
        s,e = m.span()
        if _overlaps(s,e,occupied):
            continue
        # Skip if already suggested exact span
        if any(sug["start"]==s and sug["end"]==e for sug in suggestions):
            continue
        suggestions.append({
            "start": s,
            "end": e,
            "text": token,
            "type": "Disease",  # default guess
            "confidence": 0.5,
            "source": "heuristic-cap"
        })

    # Deduplicate by (start,end,type)
    uniq = {}
    for s in suggestions:
        uniq[(s["start"], s["end"], s["type"])] = s
    return sorted(uniq.values(), key=lambda x: (x["start"], -(x.get("confidence",0))))


def _overlaps(s: int, e: int, occupied: set[int]) -> bool:
    for i in range(s,e):
        if i in occupied:
            return True
    return False
