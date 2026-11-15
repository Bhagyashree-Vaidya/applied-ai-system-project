"""Deterministic checks that run before and after every model call."""
from __future__ import annotations

import re

MAX_INPUT_CHARS = 500
CONFIRM_BELOW = 0.7  # proposals under this confidence need a human "yes" before being scheduled

PRIORITIES = {"high", "medium", "low"}
FREQUENCIES = {"once", "daily", "weekly"}

_INJECTION = re.compile(
    r"ignore (all |any |the )?(previous|prior|above) (instructions|rules)|system prompt|"
    r"you are now|disregard (the|your|all)|developer mode|jailbreak",
    re.IGNORECASE,
)
_EMERGENCY = re.compile(
    r"\b(ate|eaten|swallowed|ingested|licked)\b.*\b(chocolate|grapes?|raisins?|xylitol|antifreeze|"
    r"rat poison|lilies|lily|onions?|ibuprofen|advil|tylenol|acetaminophen)\b|"
    r"\b(seizure|seizing|not breathing|can'?t breathe|collapsed|unconscious|hit by a car|"
    r"bleeding heavily|vomiting blood|bloated|bloat)\b",
    re.IGNORECASE,
)
_DOSAGE = re.compile(r"\b\d+(\.\d+)?\s?(mg|milligrams?|ml|millilit(er|re)s?|cc|tablets?)\b", re.IGNORECASE)

EMERGENCY_MESSAGE = (
    "This sounds like a possible emergency. Contact your veterinarian or the nearest emergency "
    "animal hospital right now, or call a pet poison hotline if a toxin may be involved. "
    "PawPal will not give treatment advice for emergencies."
)


def check_input(text: str) -> str | None:
    """Return a rejection reason, or None if the text is safe to send to the model."""
    if not text or not text.strip():
        return "Please type a request."
    if len(text) > MAX_INPUT_CHARS:
        return f"Request is too long ({len(text)} chars, max {MAX_INPUT_CHARS})."
    if _INJECTION.search(text):
        return "That request looks like an attempt to change PawPal's instructions, so it was blocked."
    return None


def is_emergency(text: str) -> bool:
    """True when the text describes a likely medical emergency (handled without the model)."""
    return bool(text and _EMERGENCY.search(text))


def has_dosage(text: str) -> bool:
    """True when text contains a medication amount such as '5 mg'."""
    return bool(_DOSAGE.search(text or ""))


def _confidence(raw: dict) -> float:
    try:
        return max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        return 0.5


def validate_task(raw: dict, pet_names: list[str]) -> tuple[dict | None, list[str]]:
    """Check a parsed task against the schema and the real household. Returns (clean, errors)."""
    if not raw.get("is_task", False):
        return None, [str(raw.get("reason") or "The model did not find a pet-care task.")]

    errors = []
    by_lower = {n.lower(): n for n in pet_names}
    pet = by_lower.get(str(raw.get("pet_name", "")).strip().lower())
    if pet is None:
        errors.append(f"Unknown pet '{raw.get('pet_name')}'. Known pets: {', '.join(pet_names) or 'none'}.")

    time_str = str(raw.get("time", ""))
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", time_str)
    if not m:
        errors.append(f"Invalid time '{time_str}'.")

    try:
        duration = int(raw.get("duration_minutes", 0))
    except (TypeError, ValueError):
        duration = 0
    if not 1 <= duration <= 240:
        errors.append(f"Duration must be 1-240 minutes (got {raw.get('duration_minutes')}).")

    try:
        day_offset = int(raw.get("day_offset", 0))
    except (TypeError, ValueError):
        day_offset = -1
    if not 0 <= day_offset <= 6:
        errors.append(f"day_offset must be 0-6 (got {raw.get('day_offset')}).")

    description = str(raw.get("description", "")).strip()[:60]
    if not description:
        errors.append("Missing task description.")

    priority = str(raw.get("priority", "medium")).lower()
    frequency = str(raw.get("frequency", "once")).lower()
    if priority not in PRIORITIES:
        errors.append(f"Invalid priority '{priority}'.")
    if frequency not in FREQUENCIES:
        errors.append(f"Invalid frequency '{frequency}'.")

    if errors:
        return None, errors
    return {
        "pet_name": pet, "description": description, "hour": int(m.group(1)), "minute": int(m.group(2)),
        "day_offset": day_offset, "duration_minutes": duration, "priority": priority,
        "frequency": frequency, "confidence": _confidence(raw),
    }, []


def validate_advice(raw: dict, valid_sources: set[str] | None = None) -> tuple[dict | None, list[str]]:
    """Check coach output; drop unsafe tips and invented citations. Returns (clean, notes)."""
    notes = []
    summary = str(raw.get("summary", "")).strip()
    if not summary:
        return None, ["Model returned no summary."]
    tips = raw.get("tips", [])
    if not isinstance(tips, list):
        return None, ["'tips' was not a list."]

    safe_tips = []
    for tip in tips:
        tip = str(tip).strip()
        if not tip:
            continue
        if has_dosage(tip):
            notes.append("Removed a tip containing a medication dose.")
            continue
        safe_tips.append(tip)
    if len(safe_tips) > 3:
        notes.append(f"Trimmed {len(safe_tips)} tips to 3.")
        safe_tips = safe_tips[:3]
    if has_dosage(summary):
        notes.append("Summary contained a medication dose; replaced with a vet referral.")
        summary = "Please ask your vet for the exact medication dose."

    sources = raw.get("sources", [])
    sources = [str(x) for x in sources] if isinstance(sources, list) else []
    if valid_sources is not None:
        invented = [x for x in sources if x not in valid_sources]
        if invented:
            notes.append(f"Dropped citation(s) to notes that were not retrieved: {', '.join(invented)}")
        sources = [x for x in sources if x in valid_sources]

    return {
        "in_scope": bool(raw.get("in_scope", True)),
        "sources": sources,
        "summary": summary,
        "tips": safe_tips,
        "vet_flag": bool(raw.get("vet_flag", False)),
        "confidence": _confidence(raw),
    }, notes
