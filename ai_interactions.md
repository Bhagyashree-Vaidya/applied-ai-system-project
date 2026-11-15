# AI Interactions Log

## Agent Workflow (SF7)

**What task did you give the agent?**

Build PawPal+ end to end from the starter: UML, `pawpal_system.py`, `main.py`, tests, the Streamlit UI, docs, then stretch features (next-slot search, JSON persistence, formatted output) and UI screenshots.

**What did the agent do?**

- Files modified/created: `pawpal_system.py`, `main.py`, `app.py`, `tests/test_pawpal.py`, `diagrams/uml.mmd`, `diagrams/uml_final.mmd`, `README.md`, `reflection.md`, `requirements.txt`, `.gitignore`, `docs/screenshots/*`.
- Wrote the dataclasses, `Scheduler` (sort, filter, conflicts, recurrence, daily plan, next slot), and `Owner.save`/`load`.
- Ran `main.py` and pytest after changes (16 tests passing), ran the Streamlit app headlessly, and captured screenshots with Playwright driving Chrome.
- Committed and pushed to `main`.

**What did you have to verify or fix manually?**

- The first UI draft had two bugs found only by checking behavior: the success message disappeared because of an immediate `st.rerun()`, and "Complete task" never changed the stored task because the selectbox returned a copy (fixed by selecting by index).
- `_slot_hint` first built a throwaway Owner; simplified with an `ignore` parameter.
- Early test and demo commands failed with `python: command not found` (use `python3`); one agent command killed its own shell by using `pkill -f` on a pattern it also contained.
- The conflict screenshot was captured before the selectbox fix; it was still accurate because it shows only the warning.

---

## Prompt Comparison (SF11)

Compared two prompting strategies for conflict detection. Only Option B was implemented; Option A was evaluated by reasoning about its behavior on the demo data.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Claude Code (Sonnet 5.5) | Claude Code (Sonnet 5.5) |
| **Prompt** | "Detect if two tasks are scheduled at the same time" (exact start-time match) | "Detect tasks whose time windows overlap, using start time plus duration, across all pets" |
| **Response summary** | Group pending tasks by `due_time` and flag groups of 2+ | Sort pending tasks and flag pairs where the later start is before the earlier end |
| **What was useful** | Very short and easy to read | Catches a 08:00-08:30 walk overlapping an 08:15 feeding; back-to-back tasks are not flagged |
| **Problems noticed** | Misses that overlap without sharing a start time | Slightly longer; pairwise comparison is O(n²) |
| **Decision** | Rejected | Used |

**Which approach did you use in your final implementation and why?**

Option B (`Scheduler.detect_conflicts`). Real tasks have durations, so exact-time matching would miss the most common clash. O(n²) is fine for a household's daily tasks. Tests cover identical times, partial overlap, and back-to-back tasks.

*Option A's output was not run; its "problems" are from analysis. Edit these entries to match your own experience.*

---

# Final project (Applied AI System): agent reasoning traces

The **Fix-my-day agent** ([pawpal_ai/agent.py](pawpal_ai/agent.py)) runs a plan → act → verify loop with **native Groq tool calls** (`list_tasks`, `find_conflicts`, `find_next_slot`, `move_task`, `search_care_notes`, `finish`) against a *sandbox copy* of the schedule. After it finishes, code independently checks the result (conflicts before/after, time budget, medication moves), writes the summary from what actually changed, and applies the moves only after the owner approves. Every run writes a markdown trace to [assets/agent_traces/](assets/agent_traces/); the console output of the final run is in [assets/agent_run.txt](assets/agent_run.txt).

Reproduce with: `python pawpal_ai_cli.py fix` (or the "Fix my day" section in the Streamlit app).

## Committed traces

| Trace | Model | What it shows |
|---|---|---|
| [trace_example_success.md](assets/agent_traces/trace_example_success.md) | gpt-oss-120b | Final design. Lists tasks → finds the walk/feeding conflict → asks for the next free slot → moves feeding to 08:30 → re-checks conflicts → finishes. Verified 1 → 0 conflicts; flags that grooming is still over budget. |
| [trace_example_step_limit.md](assets/agent_traces/trace_example_step_limit.md) | gpt-oss-20b | The smaller model repeated the same lookups and hit the step cap. The guardrail stopped it, and verification still confirmed the one valid move. |
| [trace_example_model_error_midrun.md](assets/agent_traces/trace_example_model_error_midrun.md) | gpt-oss-20b | Groq rejected a malformed tool call mid-run. The agent stopped safely and verification reported only what had really changed. This led to the automatic retry for malformed generations. |
| [trace_example_20b_wanders.md](assets/agent_traces/trace_example_20b_wanders.md) | gpt-oss-20b | Before the prompt explained that budget-skipped tasks cannot be fixed by moving them, the agent fixed the conflict and then spent 5 steps moving the over-budget Grooming task around until it hit the 10-step cap. The verifier still flagged Grooming as over budget. (In an earlier run whose trace was not kept, the model's own summary claimed "all tasks now fit within the day" while Grooming was still over budget; that is why the summary is now written by code from the sandbox, not by the model.) |

## Embedded trace (final design, gpt-oss-120b)

| Step | Thought | Action | Args | Observation |
|---|---|---|---|---|
| 1 | We need to follow instructions. First call list_tasks to see tasks. | `list_tasks` | `{}` | Budget 90 min. id=0 08:00-08:30 Biscuit 'Morning walk' 30min high daily; id=1 08:15-08:25 Whiskers 'Feeding' 10min high daily; id=3 09:00-09:10 Nibbles 'Hay and water' 10min high daily; id=2 14:00-15:00 Whiskers 'Grooming' 60min low once (SKIPPED: does not fit the daily minute budget; moving it will not help) |
| 2 | We have tasks list. Need to find conflicts. There's overlap between id0 (08:00-08:30) and id1 (08:15-08:25). Also maybe other conflicts? Let's call find_conflicts. | `find_conflicts` | `{}` | Biscuit's 'Morning walk' (08:00-08:30) overlaps Whiskers's 'Feeding' (08:15) - next free slot: 08:30 |
| 3 | We have tasks: id0 08:00-08:30 (30min), id1 08:15-08:25 (10min) overlapping. Also id3 09:00-09:10 no conflict. id2 is SKIPPED, ignore. We need to move low priority tasks first, but id0 is high priority, id1 high priority. Both high. But we need to resolve conflict. Maybe move feeding (id1) to next f | `find_next_slot` | `{"after": "08:30", "task_id": 1}` | next free slot for id=1: 08:30 |
| 4 | We have conflict between task 0 (08:00-08:30) and task 1 (08:15-08:25). Need to move one. Prefer moving low-priority tasks, but both are high priority. Keep medication times unchanged (none). Could move feeding to 08:30 (duration 10min). Check if any other conflicts after moving. Let's move task 1 t | `move_task` | `{"new_time": "08:30", "task_id": 1}` | moved id=1 Whiskers 'Feeding' 08:15 -> 08:30 |
| 5 | We have tasks: id0 08:00-08:30 walk, id1 now 08:30-08:40 feeding (duration 10 min), id3 09:00-09:10 hay water, id2 skipped cannot move. Need to check conflicts again. | `find_conflicts` | `{}` | no conflicts |
| 6 | We have tasks: id0 08:00-08:30 walk, id1 now 08:30-08:40 feeding (duration 10 min), id3 09:00-09:10 hay, id2 is SKIPPED and cannot be moved. Budget 90 min: total durations: 30+10+10 = 50 min, within budget. No conflicts. Need to fit skipped important tasks? The owner request: "resolve conflicts and  | `finish` | `{}` | (finished) |

### Verification (independent of the model)

- Verified: **True**
- Moves: Whiskers - Feeding: 08:15 -> 08:30
- Problems: Still over the 90-min budget, not in today's plan: Whiskers 'Grooming'

### Agent summary

Agent finished. Moved Whiskers - Feeding: 08:15 -> 08:30. Conflicts: 1 -> 0.
