"""Offline tests for retrieval (RAG) and the Fix-my-day agent."""
from datetime import datetime

from pawpal_ai import PawPalAssistant
from pawpal_ai import guardrails as g
from pawpal_ai.agent import MAX_STEPS, FixMyDayAgent
from pawpal_ai.llm import LLMError
from pawpal_ai.retriever import Retriever, load_chunks, tokenize
from pawpal_ai.sample import sample_owner
from pawpal_system import Scheduler
from tests.test_ai import FakeClient, household

NOW = datetime(2026, 11, 14, 7, 0)


# --- retrieval ------------------------------------------------------------------------
def test_knowledge_base_loads_sections_with_species():
    chunks = load_chunks()
    assert len(chunks) >= 25
    assert {c.species for c in chunks} >= {"dog", "cat", "rabbit", "all"}
    assert all("#" in c.id and c.text for c in chunks)


def test_search_finds_relevant_section():
    hits = Retriever().search("my cat is drinking more water and peeing a lot", species={"cat"})
    assert hits[0][0].id == "cat_senior_care#thirst-and-urination-changes"


def test_species_filter_excludes_other_animals():
    hits = Retriever().search("hay diet enrichment exercise", species={"dog"}, k=10)
    assert hits and all(c.species in ("dog", "all") for c, _ in hits)


def test_off_topic_query_retrieves_nothing():
    assert Retriever().search("write a poem about the stock market") == []


def test_tokenize_drops_stopwords_and_plurals():
    assert tokenize("The rabbits are eating hays") == ["rabbit", "eating", "hay"]


def test_coach_prompt_contains_retrieved_notes_and_sources_are_checked():
    owner = household()
    client = FakeClient({"summary": "Jordan, call your vet about Whiskers.", "tips": ["Offer wet food."],
                         "vet_flag": True, "confidence": 0.9,
                         "sources": ["cat_senior_care#thirst-and-urination-changes", "made_up#note"]})
    result = PawPalAssistant(owner, client, now=NOW).review_day("Whiskers is drinking much more water")
    prompt = client.calls[0][-1]["content"]
    assert "Care notes:" in prompt and "[cat_senior_care#thirst-and-urination-changes]" in prompt
    assert result.advice["sources"] == ["cat_senior_care#thirst-and-urination-changes"]
    assert any("made_up#note" in n for n in result.notes)  # invented citation dropped


def test_rag_can_be_disabled():
    client = FakeClient({"summary": "ok", "tips": [], "vet_flag": False, "confidence": 0.5})
    PawPalAssistant(household(), client, now=NOW, use_rag=False).review_day("Whiskers drinking more water")
    assert "Care notes:" not in client.calls[0][-1]["content"]


def test_validate_advice_without_source_list_keeps_sources():
    clean, _ = g.validate_advice({"summary": "s", "tips": [], "sources": ["x#y"]})
    assert clean["sources"] == ["x#y"]


# --- agent ----------------------------------------------------------------------------
def step(action, **args):
    return {"thought": f"do {action}", "action": action, "args": args}


def agent_for(*replies, owner=None):
    owner = owner or sample_owner(NOW)
    return owner, FixMyDayAgent(owner, FakeClient(*replies), now=NOW, save_trace=False)


def _id(owner, description):
    return next(i for i, t in enumerate(owner.get_all_tasks()) if t.description == description)


def test_agent_resolves_conflict_in_sandbox_then_applies_after_approval():
    owner = sample_owner(NOW)
    feed = _id(owner, "Feeding")
    owner, agent = agent_for(step("list_tasks"), step("find_conflicts"),
                             step("find_next_slot", task_id=feed, after="08:00"),
                             step("move_task", task_id=feed, new_time="08:30"),
                             step("find_conflicts"), step("finish", summary="Moved feeding after the walk."),
                             owner=owner)
    run = agent.run()
    assert [s["action"] for s in run.steps][:3] == ["list_tasks", "find_conflicts", "find_next_slot"]
    assert "next free slot" in run.steps[2]["observation"]
    assert run.verified and len(run.moves) == 1 and run.moves[0].new_time.hour == 8
    # real schedule untouched until apply()
    assert Scheduler(owner).detect_conflicts()
    assert agent.apply(run) == []
    assert owner.get_all_tasks()[feed].due_time == NOW.replace(hour=8, minute=30)


def test_agent_verification_catches_new_conflict():
    owner = sample_owner(NOW)
    hay = _id(owner, "Hay and water")
    owner, agent = agent_for(step("move_task", task_id=hay, new_time="08:00"), step("finish", summary="done"),
                             owner=owner)
    run = agent.run()
    assert not run.verified and any("increased" in p for p in run.problems)


def test_agent_rejects_bad_tool_calls():
    _, agent = agent_for(step("delete_everything"), step("move_task", task_id=99, new_time="08:00"),
                         step("move_task", task_id=0, new_time="23:30"), step("finish", summary="x"))
    obs = [s["observation"] for s in agent.run().steps[:3]]
    assert obs[0].startswith("ERROR: unknown action") and "unknown task_id" in obs[1] and "between" in obs[2]


def test_agent_stops_at_step_limit():
    _, agent = agent_for(*[step("list_tasks")] * MAX_STEPS)
    run = agent.run()
    assert len(run.steps) == MAX_STEPS and "limit" in run.summary


def test_agent_handles_model_failure():
    _, agent = agent_for(LLMError("down"))
    run = agent.run()
    assert "unavailable" in run.summary and run.moves == []


def test_agent_writes_markdown_trace(tmp_path, monkeypatch):
    import pawpal_ai.agent as agent_mod
    monkeypatch.setattr(agent_mod, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(agent_mod, "ROOT", tmp_path)
    owner = sample_owner(NOW)
    agent = FixMyDayAgent(owner, FakeClient(step("find_conflicts"), step("finish", summary="nothing")), now=NOW)
    run = agent.run()
    text = (tmp_path / run.trace_path).read_text()
    assert "| 1 |" in text and "find_conflicts" in text and "Verification" in text
