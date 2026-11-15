"""Fix-my-day agent: plan -> act with scheduler tools -> verify -> human approval.

The model works in a loop. Each turn it returns JSON {"thought", "action", "args"}; we run
the named tool against a *sandbox copy* of the owner's schedule and send back the
observation. When it calls `finish`, the agent independently re-checks the sandbox
(no remaining conflicts it introduced, tasks inside the day, budget respected). Changes reach the
real schedule only through `apply()`, after the owner approves. Every step is
logged and written to a markdown trace in assets/agent_traces/.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from pawpal_ai.config import ROOT
from pawpal_ai.llm import JSONClient, LLMError
from pawpal_ai.retriever import Retriever
from pawpal_system import Owner, Scheduler, Task

log = logging.getLogger("pawpal_ai.agent")
TRACE_DIR = ROOT / "assets" / "agent_traces"
MAX_STEPS = 8
DAY_START, DAY_END = 6, 22

AGENT_SYSTEM = f"""You are PawPal's scheduling agent. Goal: make today's pet-care schedule work for the owner.
Fix every time conflict, and try to fit skipped high/medium-priority tasks, by MOVING tasks to new times.
You can only act through these tools (one per turn):
- list_tasks {{}}: today's pending tasks with ids, times, durations, priorities.
- find_conflicts {{}}: overlapping task pairs.
- find_next_slot {{"task_id": int, "after": "HH:MM"}}: earliest free start for that task's duration.
- move_task {{"task_id": int, "new_time": "HH:MM"}}: move a task (between {DAY_START:02d}:00 and {DAY_END}:00).
- search_care_notes {{"query": str}}: pet-care guidance (e.g. whether to walk before or after meals).
- finish {{"summary": str}}: stop. Summarize what you changed and why in at most 3 sentences.
Rules: Plan first (look before you move). Prefer moving low-priority tasks; keep medication times unchanged.
Use find_next_slot rather than guessing. Call find_conflicts before finish to check your work.
Never invent task ids. At most {MAX_STEPS} steps.
Reply with JSON only: {{"thought": "short reasoning", "action": "tool name", "args": {{...}}}}"""


@dataclass
class Move:
    task_id: int
    pet_name: str
    description: str
    old_time: datetime
    new_time: datetime

    def describe(self) -> str:
        return f"{self.pet_name} - {self.description}: {self.old_time:%H:%M} -> {self.new_time:%H:%M}"


@dataclass
class AgentRun:
    """Outcome of one agent run (nothing is applied until `FixMyDayAgent.apply`)."""

    summary: str
    moves: list[Move]
    verified: bool
    problems: list[str]
    steps: list[dict] = field(default_factory=list)
    trace_path: str | None = None


class FixMyDayAgent:
    def __init__(self, owner: Owner, client: JSONClient, now: datetime | None = None,
                 retriever: Retriever | None = None, save_trace: bool = True):
        self.owner = owner
        self.client = client
        self.now = now or datetime.now().replace(second=0, microsecond=0)
        self.retriever = retriever or Retriever()
        self.save_trace = save_trace

    # -- sandbox helpers ----------------------------------------------------------------
    def _today(self, owner: Owner) -> list[tuple[int, Task]]:
        """(id, task) for today's pending tasks. ids index owner.get_all_tasks(), which a deepcopy preserves."""
        return [(i, t) for i, t in enumerate(owner.get_all_tasks())
                if not t.completed and t.due_time.date() == self.now.date()]

    def _parse_time(self, value) -> datetime | None:
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(value).strip())
        return self.now.replace(hour=int(m.group(1)), minute=int(m.group(2))) if m else None

    # -- tools --------------------------------------------------------------------------
    def _run_tool(self, sandbox: Owner, action: str, args: dict) -> str:
        sched = Scheduler(sandbox)
        tasks = dict(self._today(sandbox))
        if action == "list_tasks":
            plan = sched.build_daily_plan(self.now)
            rows = [f"id={i} {t.due_time:%H:%M}-{t.end_time:%H:%M} {t.pet_name} '{t.description}' "
                    f"{t.duration_minutes}min {t.priority} {t.frequency}{'' if t in plan else ' (SKIPPED: over budget)'}"
                    for i, t in sorted(tasks.items(), key=lambda kv: kv[1].due_time)]
            return f"Budget {sandbox.available_minutes_per_day} min. " + ("; ".join(rows) or "no tasks today")
        if action == "find_conflicts":
            return "; ".join(sched.conflict_warnings()) or "no conflicts"
        if action == "search_care_notes":
            hits = self.retriever.search(str(args.get("query", "")), k=2)
            return " | ".join(c.cite() for c, _ in hits) or "no matching notes"
        if action in ("find_next_slot", "move_task"):
            try:
                task = tasks[int(args.get("task_id"))]
            except (TypeError, ValueError, KeyError):
                return f"ERROR: unknown task_id {args.get('task_id')!r}. Use list_tasks."
            key = "after" if action == "find_next_slot" else "new_time"
            when = self._parse_time(args.get(key))
            if when is None:
                return f"ERROR: {key} must be HH:MM"
            if action == "find_next_slot":
                slot = sched.find_next_slot(task.duration_minutes, when, DAY_END, ignore=task)
                return f"next free slot for id={args['task_id']}: {slot:%H:%M}" if slot else "no free slot before 22:00"
            if not (DAY_START <= when.hour and when + (task.end_time - task.due_time) <= when.replace(hour=DAY_END, minute=0)):
                return f"ERROR: tasks must stay between {DAY_START:02d}:00 and {DAY_END}:00"
            old = task.due_time
            task.due_time = when
            return f"moved id={args['task_id']} {task.pet_name} '{task.description}' {old:%H:%M} -> {when:%H:%M}"
        return f"ERROR: unknown action {action!r}"

    # -- loop ---------------------------------------------------------------------------
    def run(self, goal: str = "Fix my day.") -> AgentRun:
        sandbox = copy.deepcopy(self.owner)
        before = {i: t.due_time for i, t in self._today(self.owner)}
        conflicts_before = len(Scheduler(self.owner).detect_conflicts())
        messages = [{"role": "system", "content": AGENT_SYSTEM},
                    {"role": "user", "content": f"Today is {self.now:%A %Y-%m-%d}. Owner request: {goal}"}]
        steps, summary = [], ""
        log.info("agent start goal=%r conflicts_before=%d", goal, conflicts_before)

        for n in range(1, MAX_STEPS + 1):
            try:
                reply = self.client.complete_json(messages)
            except LLMError as exc:
                steps.append({"step": n, "thought": "", "action": "(model error)", "args": {}, "observation": str(exc)})
                summary = f"Stopped: the model was unavailable ({exc})."
                break
            action = str(reply.get("action", ""))
            args = reply.get("args") if isinstance(reply.get("args"), dict) else {}
            if action == "finish":
                summary = str(args.get("summary") or reply.get("thought") or "Done.")
                steps.append({"step": n, "thought": reply.get("thought", ""), "action": action, "args": args,
                              "observation": "(finished)"})
                break
            observation = self._run_tool(sandbox, action, args)
            steps.append({"step": n, "thought": reply.get("thought", ""), "action": action, "args": args,
                          "observation": observation})
            log.info("agent step %d %s %s -> %s", n, action, args, observation)
            messages += [{"role": "assistant", "content": json.dumps(reply)},
                         {"role": "user", "content": f"Observation: {observation}"}]
        else:
            summary = f"Stopped after the {MAX_STEPS}-step limit."

        run = self._verify(sandbox, before, conflicts_before, summary, steps)
        if self.save_trace:
            run.trace_path = self._write_trace(goal, run)
        log.info("agent done verified=%s moves=%s problems=%s", run.verified,
                 [m.describe() for m in run.moves], run.problems)
        return run

    def _verify(self, sandbox: Owner, before: dict, conflicts_before: int, summary: str, steps: list) -> AgentRun:
        """Independent check of the agent's work (does not trust its summary)."""
        after = dict(self._today(sandbox))
        moves = [Move(i, t.pet_name, t.description, before[i], t.due_time)
                 for i, t in after.items() if i in before and t.due_time != before[i]]
        sched = Scheduler(sandbox)
        problems = []
        conflicts_after = len(sched.detect_conflicts())
        if conflicts_after > conflicts_before:
            problems.append(f"Conflicts increased from {conflicts_before} to {conflicts_after}.")
        elif conflicts_after:
            problems.append(f"{conflicts_after} conflict(s) remain.")
        for m in moves:
            task = after[m.task_id]
            if "med" in task.description.lower():
                problems.append(f"Medication task '{task.description}' was moved; confirm with your vet's timing.")
        if not moves and conflicts_before:
            problems.append("No tasks were moved, so the conflicts are unchanged.")
        verified = conflicts_after < conflicts_before or (conflicts_before == 0 and conflicts_after == 0)
        verified = verified and not any("increased" in p for p in problems)
        return AgentRun(summary, moves, verified, problems, steps)

    def apply(self, run: AgentRun) -> list[str]:
        """Copy approved moves onto the real schedule; return the new conflict warnings."""
        tasks = self.owner.get_all_tasks()
        for m in run.moves:
            tasks[m.task_id].due_time = m.new_time
        log.info("agent moves applied: %s", [m.describe() for m in run.moves])
        return Scheduler(self.owner).conflict_warnings()

    def _write_trace(self, goal: str, run: AgentRun) -> str:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        path = TRACE_DIR / f"trace_{datetime.now():%Y%m%d_%H%M%S}.md"
        lines = [f"# Agent trace: {goal}", "", f"Model: `{getattr(self.client, 'model', '?')}`  ",
                 f"Run at: {datetime.now():%Y-%m-%d %H:%M:%S}", "", "| Step | Thought | Action | Args | Observation |",
                 "|---|---|---|---|---|"]
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
        for s in run.steps:
            lines.append(f"| {s['step']} | {esc(s['thought'])} | `{s['action']}` | `{esc(json.dumps(s['args']))}` | "
                         f"{esc(s['observation'])} |")
        lines += ["", "## Verification (independent of the model)", "",
                  f"- Verified: **{run.verified}**",
                  f"- Moves: {', '.join(m.describe() for m in run.moves) or 'none'}",
                  f"- Problems: {'; '.join(run.problems) or 'none'}", "", f"## Agent summary", "", run.summary, ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path.relative_to(ROOT))
