from datetime import datetime, time
from html import escape
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
            --pp-green: #236B52; --pp-cream: #FFFBF5; --pp-ink: #1B2340; --pp-soft: #E8EEFF;
            --pp-peach: #FFE6D3; --pp-lilac: #F0E6FA; --pp-mint: #E1F2E9;
            --pp-clay: 9px 12px 24px rgba(77, 66, 107, .10),
                inset -5px -5px 10px rgba(87, 75, 111, .07),
                inset 5px 5px 10px rgba(255, 255, 255, .85);
            --pp-small-clay: 4px 5px 10px rgba(77, 66, 107, .12),
                inset -3px -3px 6px rgba(62, 68, 117, .09),
                inset 3px 3px 6px rgba(255, 255, 255, .8);
        }
        html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea, select, label {
            font-family: 'Nunito', system-ui, sans-serif !important;
        }
        [data-testid="stAppViewContainer"] {
            background: radial-gradient(ellipse at 95% 5%, #F1EDFF 0, transparent 42%), var(--pp-cream);
        }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { max-width: 1280px; padding-top: 2rem; padding-bottom: 3rem; }
        h1, h2, h3 { font-weight: 900 !important; letter-spacing: -0.02em; color: var(--pp-ink); }
        [data-testid="stCaptionContainer"] { color: #5A6482; }

        /* A soft blue clay stage, with the little crew peeking over its edge. */
        .pp-hero {
            position: relative; isolation: isolate; overflow: hidden; border-radius: 32px;
            padding: 2rem 2.2rem; margin-bottom: 1rem; min-height: 268px;
            background: linear-gradient(125deg, #E5EDFF 0%, #CDDDFF 55%, #ADC6F7 100%);
            border: 1px solid #FFFFFFB3; color: var(--pp-ink);
            box-shadow: 12px 14px 28px rgba(53, 81, 144, .16),
                inset -7px -7px 15px rgba(66, 96, 165, .13), inset 7px 7px 15px #FFFFFFB3;
        }
        .pp-hero-copy { position: relative; z-index: 1; width: 63%; }
        .pp-eyebrow { display: block; color: var(--pp-blue-dark); font-size: .73rem;
            letter-spacing: .14em; font-weight: 900; margin-bottom: .7rem; }
        .pp-hero h1 { color: var(--pp-blue-dark) !important; font-size: clamp(1.85rem, 2.8vw, 2.6rem);
            padding: 0; margin: 0 0 .8rem; line-height: 1.16; overflow-wrap: anywhere; }
        .pp-hero p { margin: 0; font-size: 1rem; color: #37476D; line-height: 1.6; font-weight: 600; }
        .pp-pill { display: inline-flex; margin-top: 1.1rem; padding: .45rem .9rem; border-radius: 999px;
            font-size: .78rem; font-weight: 800; box-shadow: var(--pp-small-clay); overflow-wrap: anywhere; }
        .ai-on { background: var(--pp-mint); color: var(--pp-green); }
        .ai-off { background: #F5F7FF; color: #3D4E77; }
        .pp-hero-art { position: absolute; width: 38%; height: 235px; right: .4rem; bottom: -12px;
            pointer-events: none; }
        .pp-hero-art::before { content: ""; position: absolute; inset: 45px 5px -60px;
            border-radius: 50%; background: #FFFFFF45; box-shadow: inset 4px 5px 12px #FFFFFF70; }
        .pp-hero-art .pp-animal { position: absolute; width: 47%; height: auto;
            filter: drop-shadow(3px 9px 5px rgba(42, 61, 101, .15)); }
        .pp-hero-art .pp-dog { left: -3%; bottom: 0; transform: rotate(-9deg); z-index: 2; }
        .pp-hero-art .pp-cat { left: 27%; bottom: 20px; transform: rotate(5deg); }
        .pp-hero-art .pp-rabbit { right: -3%; bottom: -3px; transform: rotate(10deg); z-index: 3; }

        /* Raised controls compress when pressed; focus remains visible. */
        .stButton > button, .stFormSubmitButton > button {
            border-radius: 24px !important; font-weight: 800 !important; padding: .65rem 1.25rem !important;
            min-height: 46px; background: #E7EEFF; color: var(--pp-blue-dark);
            border: 1px solid #FFFFFFB3 !important; box-shadow: var(--pp-small-clay);
            transition: transform .14s ease, box-shadow .14s ease, background .14s ease;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button {
            background: linear-gradient(145deg, #FFD1A6, #FFAD68) !important; color: #63300F !important;
            box-shadow: 5px 6px 12px #B9682526, inset -4px -4px 8px #CA671B26, inset 4px 4px 8px #FFFFFF99;
        }
        .stButton > button:hover:not(:disabled), .stFormSubmitButton > button:hover:not(:disabled) {
            transform: translateY(-2px); border-color: #8DA5E6 !important; color: var(--pp-blue-dark);
        }
        .stButton > button:active:not(:disabled), .stFormSubmitButton > button:active:not(:disabled) {
            transform: translateY(2px); box-shadow: 2px 2px 4px #4D426B1A,
                inset 3px 3px 6px #59436826, inset -2px -2px 5px #FFFFFF99;
        }
        .stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible,
        .stTabs [data-baseweb="tab"]:focus-visible { outline: 3px solid var(--pp-blue); outline-offset: 3px; }
        .stButton > button:disabled, .stFormSubmitButton > button:disabled {
            opacity: .5; box-shadow: none; transform: none; cursor: not-allowed;
        }

        /* Bordered containers in both older and newer Streamlit layouts. */
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
            border-radius: 28px !important; border: 1px solid #FFFFFFCC !important;
            background: #FFFCF8; box-shadow: var(--pp-clay);
        }
        div[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
            padding: 1.25rem !important; height: 100%;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) { background: var(--pp-peach); }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) { background: var(--pp-soft); }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) { background: var(--pp-mint); }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) { background: var(--pp-lilac); }
        div[data-testid="stMetricValue"] { color: var(--pp-blue-dark); font-weight: 900; font-size: 2rem; }
        div[data-testid="stMetricLabel"] p { font-weight: 800; text-transform: uppercase; font-size: .78rem;
            letter-spacing: .045em; color: #505B78; white-space: normal; }

        /* Give pill shadows room inside the horizontal tab scroller. */
        .stTabs [data-baseweb="tab-list"] { gap: .65rem; border-bottom: none; padding: .65rem .3rem 1rem; }
        .stTabs [data-baseweb="tab"] {
            background: #EEF1FD; border-radius: 24px; padding: .65rem 1.1rem; min-height: 46px;
            font-weight: 800; color: var(--pp-blue-dark); border: 1px solid #FFFFFFB3;
            box-shadow: var(--pp-small-clay); transition: transform .14s ease, box-shadow .14s ease;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(145deg, #3F6EE3, var(--pp-blue)) !important; color: #fff !important;
            box-shadow: 4px 6px 12px #1F4FD82B, inset -3px -3px 7px #102D8A55, inset 3px 3px 6px #FFFFFF55;
        }
        .stTabs [data-baseweb="tab"]:active {
            transform: translateY(2px); box-shadow: inset 2px 3px 6px #1B234026;
        }
        .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

        section[data-testid="stSidebar"] { background: #FFF2E5; border-right: 1px solid #FFFFFF;
            box-shadow: 6px 0 22px #73533B08; }
        section[data-testid="stSidebar"] h1 { color: var(--pp-blue-dark) !important; }
        [data-testid="stForm"] { border-radius: 28px; border: 1px solid #FFFFFFB3;
            background: #FFFCF880; box-shadow: inset 3px 3px 9px #FFFFFFB3, inset -3px -3px 9px #9B70440A; }
        .pp-pet { display: flex; align-items: center; gap: .8rem; background: #F5F3FF; border-radius: 24px;
            padding: .75rem; margin-bottom: .75rem; border: 1px solid #FFFFFFB3; box-shadow: var(--pp-clay); }
        .pp-pet-dog { background: var(--pp-peach); }
        .pp-pet-cat { background: var(--pp-lilac); }
        .pp-pet-rabbit { background: var(--pp-mint); }
        .pp-avatar { flex: 0 0 58px; width: 58px; height: 62px; display: flex;
            align-items: center; justify-content: center; border-radius: 22px; background: #FFFFFF70;
            box-shadow: var(--pp-small-clay); }
        .pp-avatar svg { width: 58px; height: 65px; }
        .pp-pet-copy { min-width: 0; overflow-wrap: anywhere; }
        .pp-pet b { display: block; color: var(--pp-ink); font-size: 1rem; }
        .pp-pet span { font-size: .82rem; color: #505B78; }

        /* Recessed clay fields keep their native input and keyboard behavior. */
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stNumberInputContainer"], [data-testid="stTextArea"] [data-baseweb="textarea"],
        div[data-baseweb="select"] > div, [data-testid="stTimeInput"] [data-baseweb="input"] {
            border-radius: 24px !important; background: #F4F5FD !important;
            border: 1px solid #D7DFF2 !important;
            box-shadow: inset 4px 4px 7px #6D79951A, inset -4px -4px 7px #FFFFFF, 2px 3px 5px #FFFFFF99;
            min-height: 46px;
        }
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        [data-testid="stTimeInput"] input { background: transparent !important; color: var(--pp-ink); }
        [data-baseweb="input"] > div { background: transparent; }
        [data-testid="stNumberInputContainer"] button { background: #E8EEFF; color: var(--pp-blue-dark); }
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stNumberInputContainer"]:focus-within,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        [data-testid="stTimeInput"] [data-baseweb="input"]:focus-within {
            border-color: var(--pp-blue) !important; outline: 2px solid #1F4FD840; outline-offset: 2px;
        }
        div[data-testid="stAlert"] { border-radius: 24px; box-shadow: var(--pp-clay); }
        div[data-testid="stAlert"] > div { border-radius: 24px; }
        .pp-empty { display: flex; gap: 1.3rem; align-items: center; padding: 1.25rem 1.6rem;
            margin: .25rem 0 1rem; border-radius: 28px; background: #F2F5FF;
            border: 1px solid #FFFFFFCC; box-shadow: var(--pp-clay); }
        .pp-empty svg { flex: 0 0 92px; width: 92px; height: 104px; }
        .pp-empty h3 { margin: 0 0 .35rem; padding: 0; font-size: 1.2rem; }
        .pp-empty p { color: #505B78; margin: 0; line-height: 1.6; overflow-wrap: anywhere; }
        @media (max-width: 1100px) {
            .pp-hero { padding: 1.75rem; }
            .pp-hero-copy { width: 65%; }
            .pp-hero-art { width: 35%; bottom: -4px; }
        }
        @media (max-width: 640px) {
            .block-container { padding: 1rem 1rem 2rem; }
            .pp-hero { padding: 1.5rem; border-radius: 28px; min-height: 0; }
            .pp-hero-copy { width: 100%; }
            .pp-hero h1 { font-size: 1.9rem; }
            .pp-hero p { font-size: .94rem; }
            .pp-hero-art { position: relative; width: 210px; height: 125px;
                margin: .75rem 0 -2.3rem auto; right: -1rem; bottom: 0; }
            .pp-hero-art::before { inset: 20px 5px -35px; }
            .pp-hero-art .pp-cat { bottom: 8px; }
            .stTabs [data-baseweb="tab"] { padding: .6rem .8rem; white-space: nowrap; }
            .pp-empty { padding: 1rem; gap: .85rem; align-items: flex-start; }
            .pp-empty svg { flex-basis: 64px; width: 64px; height: 78px; }
        }
        @media (prefers-reduced-motion: reduce) {
            .stButton > button, .stFormSubmitButton > button, .stTabs [data-baseweb="tab"] {
                transition: none; transform: none !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

def animal_svg(species, instance):
    """Original clay critters. Each placement gets unique SVG paint-server IDs."""
    species = species if species in {"dog", "cat", "rabbit"} else "other"
    light, shade, accent = {
        "dog": ("#FFF0D9", "#EFB27D", "#CB8554"),
        "cat": ("#F8EDFF", "#C6A6E3", "#A984C6"),
        "rabbit": ("#F4FFF7", "#A9D6BF", "#7EB59E"),
        "other": ("#EEF3FF", "#A8BDEC", "#7895D3"),
    }[species]
    paint = f"pp-{instance}-{species}"
    coat, detail, cream = (f"url(#{paint}-{part})" for part in ("coat", "detail", "cream"))
    defs = f'''<defs>
    <radialGradient id="{paint}-coat" cx="30%" cy="20%" r="85%">
    <stop stop-color="{light}"/><stop offset=".65" stop-color="{shade}"/><stop offset="1" stop-color="{accent}"/>
    </radialGradient>
    <linearGradient id="{paint}-detail" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="{shade}"/><stop offset="1" stop-color="{accent}"/></linearGradient>
    <radialGradient id="{paint}-cream" cx="35%" cy="20%" r="85%">
    <stop stop-color="#FFFEF9"/><stop offset="1" stop-color="#F1DCC7"/></radialGradient>
    </defs>'''
    if species == "other":
        shapes = f'''<g fill="{coat}" stroke="#FFFFFF" stroke-opacity=".45" stroke-width="2">
        <ellipse cx="45" cy="68" rx="15" ry="21" transform="rotate(-25 45 68)"/>
        <ellipse cx="76" cy="51" rx="15" ry="22" transform="rotate(-8 76 51)"/>
        <ellipse cx="108" cy="60" rx="15" ry="21" transform="rotate(20 108 60)"/>
        <ellipse cx="129" cy="87" rx="13" ry="18" transform="rotate(35 129 87)"/>
        <path d="M40 126C40 110 54 103 63 90C74 74 91 79 100 94C107 106 123 113 120 130C116 150 95 139 81 139C65 139 41 149 40 126Z"/>
        </g>'''
    else:
        ears = {
            "dog": f'''<ellipse cx="35" cy="87" rx="23" ry="42" fill="{detail}" transform="rotate(17 35 87)"/>
            <ellipse cx="125" cy="87" rx="23" ry="42" fill="{detail}" transform="rotate(-17 125 87)"/>
            <path d="M24 68Q18 90 25 105" fill="none" stroke="#FFE2BD" stroke-width="5" stroke-linecap="round" opacity=".65"/>''',
            "cat": f'''<path d="M32 86L28 39Q28 28 39 34L66 56M94 56L121 34Q132 28 132 40L128 86" fill="{coat}" stroke="{accent}" stroke-width="2" stroke-linejoin="round"/>
            <path d="M38 65L37 44L56 59M104 59L123 44L122 65" fill="#F3B3C1" stroke="#F3B3C1" stroke-width="5" stroke-linejoin="round"/>''',
            "rabbit": f'''<ellipse cx="57" cy="49" rx="18" ry="44" fill="{coat}" transform="rotate(-13 57 49)"/>
            <ellipse cx="104" cy="48" rx="18" ry="45" fill="{coat}" transform="rotate(13 104 48)"/>
            <ellipse cx="57" cy="45" rx="8" ry="28" fill="#F0B9BD" transform="rotate(-13 57 45)"/>
            <ellipse cx="105" cy="44" rx="8" ry="29" fill="#F0B9BD" transform="rotate(13 105 44)"/>''',
        }[species]
        extras = {
            "dog": '<path d="M72 120Q80 117 88 120L86 130Q80 137 74 130Z" fill="#EF9D9F"/><path d="M80 123V129" stroke="#C36D7B" stroke-width="2" stroke-linecap="round"/>',
            "cat": f'<path d="M70 61L74 73M82 59V71M94 61L90 73" stroke="{accent}" stroke-width="4" stroke-linecap="round" opacity=".6"/><path d="M44 113L25 108M44 120L24 121M116 113L135 108M116 120L136 121" stroke="#8C729C" stroke-width="2" stroke-linecap="round"/>',
            "rabbit": '<rect x="73" y="120" width="14" height="12" rx="4" fill="#FFFEFA"/><path d="M80 122V130" stroke="#CFD9CA" stroke-width="1.5"/>',
        }[species]
        shapes = f'''<ellipse cx="80" cy="169" rx="51" ry="7" fill="#39466A" opacity=".10"/>
        <ellipse cx="80" cy="147" rx="39" ry="28" fill="{coat}"/>
        <ellipse cx="80" cy="151" rx="24" ry="20" fill="{cream}"/>
        {ears}
        <rect x="32" y="60" width="96" height="86" rx="40" fill="{coat}"/>
        <path d="M46 85Q52 69 70 69" fill="none" stroke="{light}" stroke-width="5" stroke-linecap="round" opacity=".8"/>
        <ellipse cx="80" cy="119" rx="26" ry="19" fill="{cream}"/>
        <ellipse cx="47" cy="113" rx="10" ry="7" fill="#EC9C9E" opacity=".65"/>
        <ellipse cx="113" cy="113" rx="10" ry="7" fill="#EC9C9E" opacity=".65"/>
        <g fill="#3E3443"><ellipse cx="61" cy="101" rx="4.5" ry="6"/><ellipse cx="99" cy="101" rx="4.5" ry="6"/></g>
        <g fill="#FFFFFF"><circle cx="60" cy="99" r="1.5"/><circle cx="98" cy="99" r="1.5"/></g>
        {extras}
        <path d="M75 110Q80 107 85 110Q86 114 80 117Q74 114 75 110" fill="#72505B"/>
        <path d="M80 117V120M80 120Q74 126 70 120M80 120Q86 126 90 120" fill="none" stroke="#72505B" stroke-width="2" stroke-linecap="round"/>
        <path d="M56 144Q80 152 104 144" fill="none" stroke="{'#6D92DF' if species == 'dog' else '#ECAA7D'}" stroke-width="6" stroke-linecap="round"/>
        <circle cx="80" cy="149" r="5" fill="#FFE3A2"/>
        <ellipse cx="48" cy="158" rx="17" ry="12" fill="{coat}"/>
        <ellipse cx="112" cy="158" rx="17" ry="12" fill="{coat}"/>
        <path d="M42 158V162M49 159V163M106 159V163M113 158V162" stroke="{accent}" stroke-width="1.5" stroke-linecap="round" opacity=".6"/>'''
    return (f'<svg class="pp-animal pp-{species}" xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 160 180" aria-hidden="true" focusable="false">{defs}{shapes}</svg>').replace("\n", "")


def animal_empty_state(title, message, species, instance):
    st.markdown(
        f'<div class="pp-empty">{animal_svg(species, instance)}'
        f'<div><h3>{escape(title)}</h3><p>{escape(message)}</p></div></div>',
        unsafe_allow_html=True,
    )


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
        for pet_index, pet in enumerate(owner.pets):
            avatar_species = pet.species if pet.species in {"dog", "cat", "rabbit"} else "other"
            st.markdown(
                f'<div class="pp-pet pp-pet-{avatar_species}"><div class="pp-avatar">'
                f'{animal_svg(avatar_species, f"sidebar-{pet_index}")}</div>'
                f'<div class="pp-pet-copy"><b>{escape(pet.name)}</b>'
                f'<span>{escape(pet.species.capitalize())} · {pet.age} yr</span></div></div>',
                unsafe_allow_html=True,
            )

owner.save(DATA_FILE)  # persist owner settings and any pet changes

greeting = f"Hi {owner.name}! " if owner.name else ""
st.markdown(
    f'''<div class="pp-hero"><div class="pp-hero-copy">
    <span class="pp-eyebrow">LITTLE ROUTINES. HAPPY PETS.</span>
    <h1>{escape(greeting)}Let's take great care of your crew.</h1>
    <p>{datetime.now():%A, %B %d} · Walks, meals, meds and play, planned around your day.</p>
    <span class="pp-pill {"ai-on" if ai_enabled else "ai-off"}">{"● PawPal AI is on" if ai_enabled else "○ AI off: set GROQ_API_KEY"}</span>
    </div><div class="pp-hero-art" aria-hidden="true">
    {animal_svg("dog", "hero")}{animal_svg("cat", "hero")}{animal_svg("rabbit", "hero")}
    </div>
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
    for tab, message, species, instance in (
        (today_tab, "Welcome to PawPal+! Add your first pet in the sidebar to start planning their care.", "dog", "welcome"),
        (add_tab, "Add a pet in the sidebar, then create a task here.", "cat", "add"),
        (coach_tab, "Add a pet in the sidebar so the Care Coach can tailor its advice.", "rabbit", "coach"),
        (fix_tab, "Add a pet and some tasks to get help with your schedule.", "dog", "fix"),
    ):
        with tab:
            animal_empty_state("Add your first pet", message, species, instance)
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
        animal_empty_state(
            "A little room for care",
            "No tasks match. Adjust the filters or head to Add task to schedule some care.",
            "rabbit", "no-tasks",
        )

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
