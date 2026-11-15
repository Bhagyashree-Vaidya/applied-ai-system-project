from datetime import datetime, time

from pathlib import Path

import streamlit as st

from pawpal_ai import PawPalAssistant
from pawpal_ai.agent import FixMyDayAgent
from pawpal_system import Owner, Pet, Scheduler, Task

DATA_FILE = Path(__file__).parent / "data.json"

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# Streamlit reruns this script on every interaction, so keep the Owner in session_state.
if "owner" not in st.session_state:
    st.session_state.owner = Owner.load(DATA_FILE)  # persisted across app restarts
owner: Owner = st.session_state.owner
scheduler = Scheduler(owner)

st.subheader("Owner")
owner.name = st.text_input("Owner name", value=owner.name)
owner.available_minutes_per_day = int(
    st.number_input("Minutes available today", 10, 1440, owner.available_minutes_per_day)
)

st.subheader("Add a pet")
with st.form("add_pet", clear_on_submit=True):
    pet_name = st.text_input("Pet name")
    species = st.selectbox("Species", ["dog", "cat", "other"])
    age = st.number_input("Age", 0, 40, 1)
    if st.form_submit_button("Add pet"):
        if pet_name.strip():
            owner.add_pet(Pet(pet_name.strip(), species, int(age)))
            st.success(f"Added {pet_name.strip()}!")
        else:
            st.error("Please enter a pet name.")

owner.save(DATA_FILE)  # persist pets/tasks after any change above

if not owner.pets:
    st.info("Add a pet to start scheduling tasks.")
    st.stop()

st.subheader("Schedule a task")
with st.form("add_task", clear_on_submit=True):
    target = st.selectbox("Pet", [p.name for p in owner.pets])
    description = st.text_input("Task", value="Morning walk")
    c1, c2, c3 = st.columns(3)
    when = c1.time_input("Time", value=time(8, 0))
    duration = c2.number_input("Duration (min)", 1, 240, 20)
    priority = c3.selectbox("Priority", ["high", "medium", "low"])
    frequency = st.selectbox("Repeats", ["once", "daily", "weekly"])
    if st.form_submit_button("Add task"):
        due = datetime.combine(datetime.now().date(), when)
        pet = next(p for p in owner.pets if p.name == target)
        pet.add_task(Task(description, due, int(duration), priority, frequency))
        owner.save(DATA_FILE)
        st.success(f"Added '{description}' for {target}.")

st.subheader("🤖 Add a task in plain English")
ai = PawPalAssistant(owner)
with st.form("ai_task", clear_on_submit=True):
    request = st.text_input("Describe the task", placeholder="Whiskers needs her meds at 7:30pm every day")
    if st.form_submit_button("Ask PawPal AI") and request:
        result = ai.propose_task(request)
        if result.kind == "task":
            st.session_state.proposal = result.proposal
        elif result.kind == "emergency":
            st.error(result.message)
        else:
            st.warning(result.message)

if proposal := st.session_state.get("proposal"):
    st.info(f"Proposed: {proposal.describe()}")
    if proposal.needs_confirmation:
        st.caption("Low confidence - please check the details before scheduling.")
    c1, c2 = st.columns(2)
    if c1.button("✅ Schedule it"):
        for warning in ai.accept(proposal):
            st.warning(f"Schedule conflict: {warning}")
        owner.save(DATA_FILE)
        del st.session_state.proposal
        st.success("Scheduled!")
    if c2.button("✖️ Discard"):
        del st.session_state.proposal
        st.rerun()


def rows(tasks):
    return [
        {"Time": t.due_time.strftime("%a %H:%M"), "Pet": t.pet_name, "Task": t.description,
         "Min": t.duration_minutes, "Priority": t.priority, "Repeats": t.frequency,
         "Done": t.completed}
        for t in tasks
    ]


st.subheader("Tasks")
f1, f2 = st.columns(2)
pet_filter = f1.selectbox("Pet", ["All"] + [p.name for p in owner.pets])
status = f2.selectbox("Status", ["All", "Pending", "Completed"])
shown = scheduler.filter_tasks(
    pet_name=None if pet_filter == "All" else pet_filter,
    completed={"All": None, "Pending": False, "Completed": True}[status],
)
shown = scheduler.sort_by_time(shown)
if shown:
    st.table(rows(shown))
else:
    st.info("No tasks match.")

for warning in scheduler.conflict_warnings():
    st.warning(f"Schedule conflict: {warning}. Consider moving one of them.")

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))  # survives the rerun after completing a task

pending = scheduler.filter_tasks(completed=False)
if pending:
    # Select by index: Streamlit may hand back a copy of object options, which would not be the stored task.
    idx = st.selectbox(
        "Mark complete", range(len(pending)),
        format_func=lambda i: f"{pending[i].pet_name}: {pending[i].description} ({pending[i].due_time:%a %H:%M})",
    )
    pick = pending[idx]
    if st.button("Complete task"):
        nxt = scheduler.complete_task(pick)
        owner.save(DATA_FILE)
        st.session_state.flash = "Done!" + (f" Next one scheduled for {nxt.due_time:%a %H:%M}." if nxt else "")
        st.rerun()

st.divider()
st.subheader("Today's plan")
if st.button("Generate schedule"):
    plan = scheduler.build_daily_plan()
    if plan:
        st.table(rows(plan))
        st.success(scheduler.explain_plan(plan))
    else:
        st.info("No pending tasks for today.")

st.divider()
st.subheader("🩺 Care Coach")
question = st.text_input("Optional question about today's care", placeholder="Is Biscuit getting enough exercise?")
if st.button("Review my day"):
    with st.spinner("Asking the PawPal Care Coach..."):
        result = PawPalAssistant(owner).review_day(question)
    if result.kind == "emergency" or (result.advice and result.advice.get("vet_flag")):
        st.error(result.message)
    elif result.kind == "advice":
        st.success(result.message)
    else:
        st.info(result.message)
    for tip in (result.advice or {}).get("tips", []):
        st.markdown(f"- {tip}")
    if result.retrieved:
        with st.expander("Care notes used (retrieved from knowledge/)"):
            cited = set((result.advice or {}).get("sources", []))
            for chunk in result.retrieved:
                st.markdown(f"{'✅' if chunk.id in cited else '▫️'} **{chunk.id}** - {chunk.text}")
    if result.advice and "confidence" in result.advice:
        st.caption(f"Model confidence: {result.advice['confidence']:.2f}")
    for note in result.notes:
        st.caption(note)

st.divider()
st.subheader("🛠️ Fix my day (agent)")
st.caption("The agent plans, moves tasks on a copy of your schedule, checks its own work, and waits for your approval.")
if st.button("Run agent"):
    assistant = PawPalAssistant(owner)
    if assistant.client is None:
        st.info("AI is unavailable; resolve conflicts manually.")
    else:
        with st.spinner("Agent is working..."):
            st.session_state.agent_run = FixMyDayAgent(owner, assistant.client).run(
                "Fix my day: resolve conflicts and fit skipped important tasks.")

if run := st.session_state.get("agent_run"):
    for s in run.steps:
        st.markdown(f"**Step {s['step']}** `{s['action']}` {s['args'] or ''}  \n_{s['thought']}_  \n→ {s['observation']}")
    (st.success if run.verified else st.warning)(f"{run.summary} (verified: {run.verified})")
    for p in run.problems:
        st.caption(f"Check: {p}")
    if run.moves:
        st.table([{"Pet": m.pet_name, "Task": m.description, "From": f"{m.old_time:%H:%M}", "To": f"{m.new_time:%H:%M}"}
                  for m in run.moves])
        c1, c2 = st.columns(2)
        if c1.button("✅ Apply changes"):
            FixMyDayAgent(owner, None).apply(run)
            owner.save(DATA_FILE)
            del st.session_state.agent_run
            st.rerun()
        if c2.button("✖️ Discard changes"):
            del st.session_state.agent_run
            st.rerun()
