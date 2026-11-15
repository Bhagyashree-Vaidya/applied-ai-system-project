"""Orchestrates guardrails -> specialized model -> validation -> PawPal scheduler.

Every public method returns an AssistantResult and never raises on model/network
problems: it logs the failure and falls back to PawPal's rule-based behavior.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pawpal_ai import guardrails as g
from pawpal_ai.config import setup_logging
from pawpal_ai.llm import GroqJSONClient, JSONClient, LLMError
from pawpal_ai.specialist import coach_messages, parse_messages
from pawpal_system import Owner, Scheduler, Task

log = setup_logging()


@dataclass
class TaskProposal:
    """A task the model extracted, validated against the household, awaiting acceptance."""

    pet_name: str
    task: Task
    confidence: float

    @property
    def needs_confirmation(self) -> bool:
        """Human-in-the-loop: low-confidence parses must be confirmed by the owner."""
        return self.confidence < g.CONFIRM_BELOW

    def describe(self) -> str:
        t = self.task
        return (f"{self.pet_name}: {t.description} at {t.due_time:%a %H:%M} for {t.duration_minutes} min "
                f"(priority {t.priority}, repeats {t.frequency}, confidence {self.confidence:.2f})")


@dataclass
class AssistantResult:
    """Outcome of one assistant call."""

    kind: str  # task | advice | emergency | rejected | fallback
    message: str
    proposal: TaskProposal | None = None
    advice: dict | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind in {"task", "advice"}


class PawPalAssistant:
    """AI layer for PawPal+. `client` is any JSONClient (Groq by default, a fake in tests)."""

    def __init__(self, owner: Owner, client: JSONClient | None = None, mode: str = "specialized",
                 now: datetime | None = None):
        self.owner = owner
        self.scheduler = Scheduler(owner)
        self.mode = mode
        self.now = now or datetime.now().replace(second=0, microsecond=0)
        self._client = client
        self._client_error: str | None = None

    # -- model access -----------------------------------------------------------------
    @property
    def client(self) -> JSONClient | None:
        if self._client is None and self._client_error is None:
            try:
                self._client = GroqJSONClient()
            except LLMError as exc:
                self._client_error = str(exc)
                log.warning("AI disabled: %s", exc)
        return self._client

    def _ask(self, messages: list[dict], validate, label: str, retry_if=lambda raw: True):
        """Call the model, validate, and retry once with the validation errors as feedback."""
        if self.client is None:
            raise LLMError(self._client_error or "No model client")
        for attempt in (1, 2):
            raw = self.client.complete_json(messages)
            log.info("%s attempt %d raw=%s", label, attempt, raw)
            clean, problems = validate(raw)
            if clean is not None or attempt == 2 or not retry_if(raw):
                return raw, clean, problems
            log.warning("%s failed validation: %s; retrying", label, problems)
            messages = messages + [
                {"role": "assistant", "content": json.dumps(raw)},
                {"role": "user", "content": "Fix these problems and return corrected JSON only: "
                                            + "; ".join(problems)},
            ]

    def _pets(self) -> list[dict]:
        return [{"name": p.name, "species": p.species, "age": p.age} for p in self.owner.pets]

    # -- feature 1: natural-language task entry -----------------------------------------
    def propose_task(self, text: str) -> AssistantResult:
        """Turn free text like 'walk Biscuit at 7am daily' into a validated TaskProposal."""
        log.info("propose_task input=%r", text)
        if reason := g.check_input(text):
            log.warning("input rejected: %s", reason)
            return AssistantResult("rejected", reason)
        if g.is_emergency(text):
            log.warning("emergency detected; model skipped")
            return AssistantResult("emergency", g.EMERGENCY_MESSAGE)
        if not self.owner.pets:
            return AssistantResult("rejected", "Add a pet first so PawPal knows who the task is for.")

        names = [p.name for p in self.owner.pets]
        msgs = parse_messages(text, self._pets(), f"{self.now:%A %Y-%m-%d}", self.mode)
        try:
            raw, clean, problems = self._ask(msgs, lambda r: g.validate_task(r, names), "parse",
                                             retry_if=lambda r: bool(r.get("is_task")))
        except LLMError as exc:
            return AssistantResult("fallback", f"AI is unavailable ({exc}). Please add the task with the form.")

        if clean is None:
            not_task = not raw.get("is_task", False)
            return AssistantResult("rejected", " ".join(problems),
                                   notes=[] if not_task else ["Model output failed validation twice."])

        due = (self.now + timedelta(days=clean["day_offset"])).replace(
            hour=clean["hour"], minute=clean["minute"])
        task = Task(clean["description"], due, clean["duration_minutes"], clean["priority"], clean["frequency"])
        proposal = TaskProposal(clean["pet_name"], task, clean["confidence"])
        notes = ["Low confidence - please confirm before scheduling."] if proposal.needs_confirmation else []
        log.info("proposal %s", proposal.describe())
        return AssistantResult("task", proposal.describe(), proposal=proposal, notes=notes)

    def accept(self, proposal: TaskProposal) -> list[str]:
        """Add an accepted proposal to its pet; return any new conflict warnings."""
        pet = next(p for p in self.owner.pets if p.name == proposal.pet_name)
        pet.add_task(proposal.task)
        warnings = [w for w in self.scheduler.conflict_warnings() if proposal.task.description in w]
        log.info("accepted task %s; conflicts=%s", proposal.describe(), warnings)
        return warnings

    # -- feature 2: plan review / care coaching -----------------------------------------
    def schedule_context(self, day: datetime | None = None) -> str:
        """Plain-text facts from the scheduler that ground the coach's answer."""
        day = day or self.now
        plan = self.scheduler.build_daily_plan(day)
        todays = [t for t in self.scheduler.filter_tasks(completed=False) if t.due_time.date() == day.date()]
        skipped = [t for t in self.scheduler.sort_by_time(todays) if t not in plan]
        fmt = lambda ts: "; ".join(
            f"{t.due_time:%H:%M} {t.pet_name} - {t.description} ({t.duration_minutes} min, {t.priority})"
            for t in ts) or "none"
        pets = ", ".join(f"{p.name} ({p.species}, {p.age})" for p in self.owner.pets) or "none"
        return (f"Owner: {self.owner.name} ({self.owner.available_minutes_per_day} min available). Pets: {pets}.\n"
                f"Planned today: {fmt(plan)}.\nSkipped (no time left): {fmt(skipped)}.\n"
                f"Conflicts: {'; '.join(self.scheduler.conflict_warnings()) or 'none'}.")

    def review_day(self, question: str = "", day: datetime | None = None) -> AssistantResult:
        """Explain today's plan with tailored tips, or answer a pet-care question about it."""
        log.info("review_day question=%r", question)
        if question:
            if reason := g.check_input(question):
                return AssistantResult("rejected", reason)
            if g.is_emergency(question):
                log.warning("emergency detected; model skipped")
                return AssistantResult("emergency", g.EMERGENCY_MESSAGE,
                                       advice={"vet_flag": True, "summary": g.EMERGENCY_MESSAGE, "tips": []})

        context = self.schedule_context(day)
        try:
            _, clean, notes = self._ask(coach_messages(context, question, self.mode), g.validate_advice, "coach")
        except LLMError as exc:
            plan = self.scheduler.build_daily_plan(day or self.now)
            return AssistantResult("fallback", self.scheduler.explain_plan(plan) + f" (AI unavailable: {exc})")
        if clean is None:
            plan = self.scheduler.build_daily_plan(day or self.now)
            return AssistantResult("fallback", self.scheduler.explain_plan(plan), notes=notes)
        if clean["vet_flag"]:
            notes.append("Vet flag raised - PawPal recommends contacting your veterinarian.")
        return AssistantResult("advice", clean["summary"], advice=clean, notes=notes)
