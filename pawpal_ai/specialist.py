"""Prompt builders for the two model modes.

* ``specialized`` — the PawPal Care Coach: a role prompt with hard style/safety rules,
  plus few-shot examples loaded from data/fewshot_examples.json.
* ``baseline`` — the same model with only a bare instruction and the JSON keys.
  It exists so eval/run_eval.py can show that specialization measurably changes behavior.
"""
from __future__ import annotations

import json
from functools import lru_cache

from pawpal_ai.config import ROOT

FEWSHOT_FILE = ROOT / "data" / "fewshot_examples.json"
MODES = ("specialized", "baseline")

PARSE_KEYS = ("is_task, pet_name, description, time (HH:MM 24h), day_offset, duration_minutes, "
              "priority, frequency, confidence, reason")
COACH_KEYS = "in_scope, summary, tips, vet_flag, confidence"

PARSE_SYSTEM = f"""You are PawPal's task parser. Turn one pet-care request into ONE scheduled task as a JSON object.
Rules:
- Only use pet names from the household list. If the request names an unknown pet or species, or is not a pet-care task, return {{"is_task": false, "reason": "...", "confidence": x}}.
- If the request says "the dog"/"the cat" and exactly one pet of that species exists, use that pet.
- time is 24h "HH:MM". Vague times: morning=08:00, noon=12:00, afternoon=15:00, evening=18:00, night=21:00.
- day_offset: 0 = today, 1 = tomorrow (max 6).
- duration_minutes: integer 1-240. Defaults if unstated: walk 30, feeding 10, medication 5, grooming 15, play 20.
- priority: "high" for medication, feeding and anything the user calls important/must; "low" for optional enrichment/grooming; otherwise "medium".
- frequency: "daily", "weekly" or "once" (default "once" unless the request implies repetition; daily medication is "daily").
- description: 2-4 words, Title case, no pet name.
- confidence: 0-1, lower it when you had to guess the time, pet or duration.
Keys: {PARSE_KEYS}. Return JSON only."""

COACH_SYSTEM = f"""You are the PawPal Care Coach, a warm, concise assistant for busy pet owners.
You receive the owner's real schedule (from the PawPal scheduler) and an optional question.
Rules:
- Ground everything in the given schedule; name the pets; never invent tasks or pets.
- summary: at most 2 sentences, addressed to the owner by name.
- tips: at most 3 items, each under 25 words, specific and actionable, species- and age-aware.
- If a conflict or skipped task is listed, at least one tip must address it.
- SAFETY: never give medication names with doses (no mg/ml amounts) - say "ask your vet for the exact dose".
- The scheduler never moves tasks by itself. Phrase changes as suggestions ("consider moving..."), never as facts ("feeding moved to 08:30").
- Respect the owner's minutes available; do not suggest adding time beyond that budget.
- Set vet_flag true when the question mentions ANY change in health or behavior (appetite, thirst, urination, vomiting, limping, lethargy, bleeding, weight, breathing, toxin ingestion) OR asks how much of any medication to give; then the summary must tell the owner to contact a vet.
- If the question is not about pet care, set in_scope false, explain briefly, and return an empty tips list.
- confidence: 0-1, how sure you are the advice is correct and safe.
Keys: {COACH_KEYS}. Return JSON only."""

BASELINE_PARSE = f"You are a helpful assistant. Convert the request into a task. Respond in JSON with keys: {PARSE_KEYS}."
BASELINE_COACH = f"You are a helpful assistant. Give advice about this pet schedule. Respond in JSON with keys: {COACH_KEYS}."


@lru_cache(maxsize=1)
def load_fewshot() -> dict:
    """Load the synthetic specialization dataset."""
    return json.loads(FEWSHOT_FILE.read_text())


def _household(pets: list[dict]) -> str:
    return ", ".join(f"{p['name']} ({p['species']}, {p['age']})" for p in pets) or "none"


def parse_messages(text: str, pets: list[dict], today: str, mode: str = "specialized") -> list[dict]:
    """Chat messages asking the model to turn `text` into a task."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    user = lambda t, household: f"Today is {today}. Household pets: {household}.\nRequest: {t}"
    if mode == "baseline":
        return [{"role": "system", "content": BASELINE_PARSE},
                {"role": "user", "content": user(text, _household(pets))}]

    shots = load_fewshot()
    msgs = [{"role": "system", "content": PARSE_SYSTEM}]
    for ex in shots["parse"]:
        msgs.append({"role": "user", "content": user(ex["input"], _household(shots["pets"]))})
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"])})
    msgs.append({"role": "user", "content": user(text, _household(pets))})
    return msgs


def coach_messages(context: str, question: str = "", mode: str = "specialized") -> list[dict]:
    """Chat messages asking the model to review a day's plan (and answer an optional question)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    user = lambda ctx, q: f"{ctx}\nQuestion: {q or '(none - just review my day)'}"
    if mode == "baseline":
        return [{"role": "system", "content": BASELINE_COACH},
                {"role": "user", "content": user(context, question)}]

    msgs = [{"role": "system", "content": COACH_SYSTEM}]
    for ex in load_fewshot()["coach"]:
        msgs.append({"role": "user", "content": user(ex["context"], ex["question"])})
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"])})
    msgs.append({"role": "user", "content": user(context, question)})
    return msgs
