from datetime import datetime, time
from pathlib import Path

import streamlit as st

from pawpal_ai import PawPalAssistant
from pawpal_ai.agent import FixMyDayAgent
from pawpal_ai.config import groq_agent_model
from pawpal_ai.llm import GroqJSONClient
from pawpal_system import Owner, Pet, Scheduler, Task

DATA_FILE = Path(__file__).parent / "data.json"

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --pp-blue: #1F4FD8; --pp-blue-dark: #15389E; --pp-orange: #FF7A1A;
            --pp-green: #00A86B; --pp-cream: #FFFBF5; --pp-ink: #1B2340; --pp-soft: #EEF3FF;
        }
        html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea, select, label {
            font-family: 'Nunito', system-ui, sans-serif !important;
        }
        .block-container { max-width: 1280px; padding-top: 1.5rem; }
        h1, h2, h3 { font-weight: 900 !important; letter-spacing: -0.02em; color: var(--pp-ink); }

        /* Hero banner */
        .pp-hero {
            position: relative; overflow: hidden; border-radius: 28px; padding: 2.2rem 2.4rem;
            background: linear-gradient(120deg, var(--pp-blue) 0%, #3D6BF0 55%, #5B8CFF 100%);
            color: #fff; box-shadow: 0 14px 36px rgba(31,79,216,.25); margin-bottom: 1.4rem;
        }
        .pp-hero h1 { color: #fff !important; font-size: 2.4rem; margin: 0 0 .35rem 0; line-height: 1.1; }
        .pp-hero p { margin: 0; font-size: 1.08rem; opacity: .95; font-weight: 600; }
        .pp-hero .pp-paws { position: absolute; right: 1.6rem; top: 50%; transform: translateY(-50%) rotate(-12deg);
            font-size: 6.5rem; opacity: .18; pointer-events: none; }
        .pp-pill { display: inline-block; margin-top: 1rem; padding: .4rem .95rem; border-radius: 999px;
            font-size: .85rem; font-weight: 800; }
        .ai-on { background: #fff; color: var(--pp-green); }
        .ai-off { background: rgba(255,255,255,.25); color: #fff; }

        /* Buttons: rounded, bold, friendly */
        .stButton > button, .stFormSubmitButton > button {
            border-radius: 999px !important; font-weight: 800 !important; padding: .55rem 1.3rem !important;
            border: 2px solid var(--pp-blue) !important; transition: transform .08s ease, box-shadow .15s ease;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button {
            background: var(--pp-orange) !important; border-color: var(--pp-orange) !important; color: #fff !important;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover {
            transform: translateY(-1px); box-shadow: 0 6px 16px rgba(255,122,26,.3);
        }

        /* Cards */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 20px !important; border: 1px solid #E6ECFA !important; background: #fff;
            box-shadow: 0 4px 14px rgba(27,35,64,.06);
        }
        div[data-testid="stMetricValue"] { color: var(--pp-blue); font-weight: 900; }
        div[data-testid="stMetricLabel"] p { font-weight: 800; text-transform: uppercase; font-size: .78rem;
            letter-spacing: .06em; color: #5A6482; }

        /* Tabs as pills */
        .stTabs [data-baseweb="tab-list"] { gap: .5rem; border-bottom: none; }
        .stTabs [data-baseweb="tab"] {
            background: var(--pp-soft); border-radius: 999px; padding: .55rem 1.2rem; font-weight: 800;
            color: var(--pp-blue-dark); border: none;
        }
        .stTabs [aria-selected="true"] { background: var(--pp-blue) !important; color: #fff !important; }
        .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

        /* Sidebar */
        section[data-testid="stSidebar"] { background: #FFF1E3; border-right: none; }
        section[data-testid="stSidebar"] h1 { color: var(--pp-orange) !important; }
        .pp-pet { display: flex; align-items: center; gap: .7rem; background: #fff; border-radius: 16px;
            padding: .6rem .8rem; margin-bottom: .5rem; box-shadow: 0 2px 8px rgba(27,35,64,.06); }
        .pp-pet .pp-avatar { font-size: 1.6rem; background: var(--pp-soft); border-radius: 50%;
            width: 2.6rem; height: 2.6rem; display: flex; align-items: center; justify-content: center; }
        .pp-pet b { display: block; color: var(--pp-ink); }
        .pp-pet span { font-size: .82rem; color: #5A6482; }

        /* Inputs and alerts */
        .stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div {
            border-radius: 14px !important; }
        div[data-testid="stAlert"] { border-radius: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

AVATAR = {"dog": "🐶", "cat": "🐱", "rabbit": "🐰"}


def rows(tasks):
    return [
        {
            "Time": t.due_time.strftime("%a %H:%M"),
            "Pet": t.pet_name,
            "Task": t.description,
            "Min": t.duration_minutes,
            "Priority": t.priority,
            "Repeats": t.frequency,
            "Done": t.completed,
        }
        for t in tasks
    ]


# Streamlit reruns this script on every interaction, so keep the Owner in session_state.
if "owner" not in st.session_state:
    st.session_state.owner = Owner.load(DATA_FILE)
owner: Owner = st.session_state.owner
scheduler = Scheduler(owner)
ai = PawPalAssistant(owner)
ai_enabled = ai.client is not None

with st.sidebar:
    st.title("🐾 PawPal+")
    st.caption("A little structure. A lot of care.")
    st.divider()
    st.subheader("Owner settings")
    owner.name = st.text_input("Owner name", value=owner.name)
    owner.available_minutes_per_day = int(
        st.number_input("Minutes available today", 10, 1440, owner.available_minutes_per_day)
    )

    st.divider()
    st.subheader("Add a pet")
    with st.form("add_pet", clear_on_submit=True):
        pet_name = st.text_input("Pet name", placeholder="e.g. Biscuit")
        species = st.selectbox("Species", ["dog", "cat", "rabbit", "other"])
        age = st.number_input("Age", 0, 40, 1)
        if st.form_submit_button("Add pet", use_container_width=True):
            if pet_name.strip():
                owner.add_pet(Pet(pet_name.strip(), species, int(age)))
                owner.save(DATA_FILE)
                st.success(f"Added {pet_name.strip()}!")
            else:
                st.error("Please enter a pet name.")

    if owner.pets:
        st.subheader("Your pets")
        for pet in owner.pets:
            st.markdown(
                f'<div class="pp-pet"><div class="pp-avatar">{AVATAR.get(pet.species, "🐾")}</div>'
                f'<div><b>{pet.name}</b><span>{pet.species.capitalize()} · {pet.age} yr</span></div></div>',
                unsafe_allow_html=True,
            )

owner.save(DATA_FILE)  # persist owner settings and any pet changes

greeting = f"Hi {owner.name}! " if owner.name else ""
st.markdown(
    f'''<div class="pp-hero"><div class="pp-paws">🐾</div>
    <h1>{greeting}Let's take great care of your crew.</h1>
    <p>{datetime.now():%A, %B %d} · Walks, meals, meds and play, planned around your day.</p>
    <span class="pp-pill {"ai-on" if ai_enabled else "ai-off"}">{"● PawPal AI is on" if ai_enabled else "○ AI off: set GROQ_API_KEY"}</span>
    </div>''',
    unsafe_allow_html=True,
)

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
for warning in st.session_state.pop("proposal_warnings", []):
    st.warning(f"Schedule conflict: {warning}")

today = datetime.now().date()
pending = scheduler.filter_tasks(completed=False)
pending_today = [task for task in pending if task.due_time.date() == today]
daily_plan = scheduler.build_daily_plan()
planned_minutes = sum(task.duration_minutes for task in daily_plan)
conflict_warnings = scheduler.conflict_warnings()

pet_metric, task_metric, time_metric, conflict_metric = st.columns(4)
with pet_metric.container(border=True):
    st.metric("Pets", len(owner.pets))
    st.caption("In your household")
with task_metric.container(border=True):
    st.metric("Pending tasks today", len(pending_today))
    st.caption("Still to check off")
with time_metric.container(border=True):
    st.metric("Minutes planned / budget", f"{planned_minutes} / {owner.available_minutes_per_day}")
    st.caption(f"{len(daily_plan)} tasks fit today's budget")
with conflict_metric.container(border=True):
    st.metric("Conflicts", len(conflict_warnings))
    st.caption("Pending task overlaps · all dates")

today_tab, add_tab, coach_tab, fix_tab = st.tabs(["📅 Today", "➕ Add task", "🩺 Care Coach", "🛠️ Fix my day"])

if not owner.pets:
    for tab, message in (
        (today_tab, "Welcome to PawPal+! Add your first pet in the sidebar to start planning their care."),
        (add_tab, "Add a pet in the sidebar, then create a task here."),
        (coach_tab, "Add a pet in the sidebar so the Care Coach can tailor its advice."),
        (fix_tab, "Add a pet and some tasks to get help with your schedule."),
    ):
        with tab:
            st.info(message)
    st.stop()

with today_tab:
    st.subheader("Your tasks")
    st.caption("See what's coming up, check off care, and make room for the essentials.")
    f1, f2, f3 = st.columns(3)
    pet_filter = f1.selectbox("Pet", ["All"] + [p.name for p in owner.pets], key="task_pet_filter")
    status = f2.selectbox("Status", ["All", "Pending", "Completed"])
    date_filter = f3.selectbox("Show tasks for", ["Today", "All dates"])
    shown = scheduler.filter_tasks(
        pet_name=None if pet_filter == "All" else pet_filter,
        completed={"All": None, "Pending": False, "Completed": True}[status],
    )
    if date_filter == "Today":
        shown = [task for task in shown if task.due_time.date() == today]
    shown = scheduler.sort_by_time(shown)
    if shown:
        st.dataframe(rows(shown), use_container_width=True, hide_index=True)
    else:
        st.info("No tasks match. Adjust the filters or head to Add task to schedule some care.")

    for warning in conflict_warnings:
        st.warning(f"Schedule conflict: {warning}. Consider moving one of them.")

    complete_column, plan_column = st.columns(2)
    with complete_column.container(border=True):
        st.subheader("Check off care")
        if pending:
            # Select by index: Streamlit may copy object options instead of returning the stored task.
            idx = st.selectbox(
                "Mark complete", range(len(pending)),
                format_func=lambda i: (
                    f"{pending[i].pet_name}: {pending[i].description} "
                    f"({pending[i].due_time:%a %H:%M})"
                ),
                help="All pending tasks are available here, regardless of the table filters.",
            )
            pick = pending[idx]
            if st.button("Complete task", type="primary"):
                nxt = scheduler.complete_task(pick)
                owner.save(DATA_FILE)
                st.session_state.flash = "Done!" + (
                    f" Next one scheduled for {nxt.due_time:%a %H:%M}." if nxt else ""
                )
                st.rerun()
        else:
            st.success("All caught up! No pending tasks.")

    with plan_column.container(border=True):
        st.subheader("Today's plan")
        st.caption("Prioritize today's care within your available minutes.")
        skipped_count = len(pending_today) - len(daily_plan)
        if skipped_count:
            st.warning(f"{skipped_count} pending task(s) won't fit today's minute budget.")
        if st.button("Generate schedule", type="primary"):
            if daily_plan:
                st.dataframe(rows(daily_plan), use_container_width=True, hide_index=True)
                st.success(scheduler.explain_plan(daily_plan))
            elif pending_today:
                st.info("No tasks fit today's budget. Increase your available minutes in the sidebar.")
            else:
                st.info("No pending tasks for today.")

with add_tab:
    st.subheader("Make time for care")
    st.caption("Enter the details yourself, or describe a task for PawPal AI to prepare.")
    manual_column, ai_column = st.columns(2)

    with manual_column.container(border=True):
        st.subheader("Schedule a task")
        with st.form("add_task", clear_on_submit=True):
            target = st.selectbox("Pet", [p.name for p in owner.pets], key="new_task_pet")
            description = st.text_input("Task", value="Morning walk")
            c1, c2 = st.columns(2)
            when = c1.time_input("Time", value=time(8, 0))
            duration = c2.number_input("Duration (min)", 1, 240, 20)
            c3, c4 = st.columns(2)
            priority = c3.selectbox("Priority", ["high", "medium", "low"])
            frequency = c4.selectbox("Repeats", ["once", "daily", "weekly"])
            if st.form_submit_button("Add task", type="primary", use_container_width=True):
                due = datetime.combine(today, when)
                pet = next(p for p in owner.pets if p.name == target)
                pet.add_task(Task(description, due, int(duration), priority, frequency))
                owner.save(DATA_FILE)
                st.session_state.flash = f"Added '{description}' for {target}."
                st.rerun()

    with ai_column.container(border=True):
        st.subheader("Add a task in plain English")
        st.caption("Review the proposal before anything is added to your schedule.")
        with st.form("ai_task", clear_on_submit=True):
            request = st.text_input(
                "Describe the task", placeholder="Whiskers needs her meds at 7:30pm every day"
            )
            if st.form_submit_button("Ask PawPal AI", type="primary", use_container_width=True) and request:
                with st.spinner("Preparing a task proposal..."):
                    result = ai.propose_task(request)
                if result.kind == "task":
                    st.session_state.proposal = result.proposal
                elif result.kind == "emergency":
                    st.error(result.message)
                else:
                    st.warning(result.message)

        if proposal := st.session_state.get("proposal"):
            st.markdown("**Review your task**")
            st.info(f"Proposed: {proposal.describe()}")
            if proposal.needs_confirmation:
                st.caption("Low confidence - please check the details before scheduling.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Schedule it", type="primary", use_container_width=True):
                st.session_state.proposal_warnings = ai.accept(proposal)
                owner.save(DATA_FILE)
                del st.session_state.proposal
                st.session_state.flash = "Scheduled! Review your task in Today."
                st.rerun()
            if c2.button("✖️ Discard", use_container_width=True):
                del st.session_state.proposal
                st.rerun()

with coach_tab:
    st.subheader("Care Coach")
    st.caption("Review today's care with advice grounded in your pets, schedule, and care notes.")
    with st.container(border=True):
        question = st.text_input(
            "Optional question about today's care", placeholder="Is Biscuit getting enough exercise?"
        )
        review_day = st.button("Review my day", type="primary")

    if review_day:
        with st.spinner("Asking the PawPal Care Coach..."):
            result = ai.review_day(question)
        st.markdown("**Care summary**")
        if result.kind == "emergency" or (result.advice and result.advice.get("vet_flag")):
            st.error(result.message)
        elif result.kind == "advice":
            st.success(result.message)
        else:
            st.info(result.message)
        tips = (result.advice or {}).get("tips", [])
        if tips:
            st.markdown("**Tips for your day**")
            for tip in tips:
                st.markdown(f"- {tip}")
        if result.advice and "confidence" in result.advice:
            st.caption(f"Model confidence: {result.advice['confidence']:.2f}")
        if result.retrieved:
            with st.expander("Retrieved care notes"):
                st.caption("✅ Cited in this advice · ▫️ Retrieved for context")
                cited = set((result.advice or {}).get("sources", []))
                for chunk in result.retrieved:
                    st.markdown(f"{'✅' if chunk.id in cited else '▫️'} **{chunk.id}**")
                    st.write(chunk.text)
        for note in result.notes:
            st.caption(note)

with fix_tab:
    st.subheader("Fix my day")
    st.caption("The agent works on a copy of your schedule, checks its changes, and waits for your approval.")
    if st.button("Run agent", type="primary"):
        if ai.client is None:
            st.info("AI is unavailable; resolve conflicts manually.")
        else:
            with st.spinner("Agent is working..."):
                st.session_state.agent_run = FixMyDayAgent(
                    owner, GroqJSONClient(model=groq_agent_model())
                ).run("Fix my day: resolve conflicts and fit skipped important tasks.")

    if run := st.session_state.get("agent_run"):
        if run.verified:
            st.success(f"Verification passed · {run.summary}")
        else:
            st.warning(f"Verification needs review · {run.summary}")
        for problem in run.problems:
            st.warning(f"Check: {problem}")

        trace_column, moves_column = st.columns([3, 2])
        with trace_column:
            with st.expander(f"Step-by-step trace · {len(run.steps)} steps", expanded=True):
                for step in run.steps:
                    st.markdown(f"**Step {step['step']} · `{step['action']}`**")
                    if step["thought"]:
                        st.caption(step["thought"])
                    if step["args"]:
                        st.json(step["args"], expanded=False)
                    st.write(step["observation"])
                    st.divider()
                if not run.steps:
                    st.caption("No steps were recorded for this run.")

        with moves_column.container(border=True):
            st.subheader("Proposed moves")
            if run.moves:
                st.dataframe(
                    [
                        {
                            "Pet": move.pet_name,
                            "Task": move.description,
                            "From": f"{move.old_time:%H:%M}",
                            "To": f"{move.new_time:%H:%M}",
                        }
                        for move in run.moves
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No schedule changes proposed.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Apply changes", type="primary", disabled=not run.moves, use_container_width=True):
                FixMyDayAgent(owner, None).apply(run)
                owner.save(DATA_FILE)
                del st.session_state.agent_run
                st.session_state.flash = "Schedule updated. Review your tasks in Today."
                st.rerun()
            if c2.button("✖️ Discard changes", use_container_width=True):
                del st.session_state.agent_run
                st.rerun()
