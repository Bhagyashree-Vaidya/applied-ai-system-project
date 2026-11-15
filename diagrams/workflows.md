# PawPal AI workflows

The overall system is in [architecture.mmd](architecture.mmd). These sequence diagrams show each workflow step by step, matching the code in `pawpal_ai/`.

## 1. Plain-English task entry (specialized model + human-in-the-loop)

```mermaid
sequenceDiagram
    actor Owner
    participant UI as app.py / CLI
    participant G as guardrails.py
    participant A as assistant.py
    participant P as specialist.py
    participant LLM as Groq gpt-oss-20b (JSON mode)
    participant S as Scheduler

    Owner->>UI: "Whiskers needs her kidney meds at 7:30pm every day"
    UI->>A: propose_task(text)
    A->>G: check_input + is_emergency
    alt blocked (empty, too long, injection)
        G-->>UI: rejected + reason
    else emergency (toxin, seizure)
        G-->>UI: contact-your-vet message (no model call)
    else ok
        A->>P: parse_messages(rules + 6 few-shot examples + household)
        P->>LLM: chat request
        LLM-->>A: JSON task
        A->>G: validate_task (real pet, HH:MM, 1-240 min, enums)
        opt invalid
            A->>LLM: retry once with the validation errors
            LLM-->>A: corrected JSON
        end
        alt confidence < 0.7
            A-->>UI: proposal + "please confirm"
            Owner->>UI: Schedule it / Discard
        else confident
            A-->>UI: proposal
        end
        UI->>A: accept(proposal)
        A->>S: pet.add_task + conflict_warnings
        S-->>UI: task scheduled (+ any conflicts)
    end
```

## 2. Care Coach review (RAG over the knowledge base)

```mermaid
sequenceDiagram
    actor Owner
    participant A as assistant.py
    participant S as Scheduler
    participant R as retriever.py (BM25)
    participant KB as knowledge/*.md
    participant LLM as Groq gpt-oss-20b
    participant G as guardrails.py

    Owner->>A: review_day("Nibbles seems bored in the afternoons")
    A->>G: input + emergency checks
    A->>S: build_daily_plan, skipped tasks, conflict_warnings
    S-->>A: schedule context
    A->>R: retrieve(question, species of pets mentioned)
    R->>KB: rank sections (species filter + boost)
    KB-->>A: top-3 notes with ids, e.g. rabbit_care#enrichment-ideas
    A->>LLM: rules + few-shot + context + care notes
    LLM-->>A: summary, tips, vet_flag, confidence, sources
    A->>G: validate_advice (drop doses, max 3 tips, drop invented citations)
    alt valid
        G-->>Owner: advice + cited notes (+ vet warning if flagged)
    else invalid twice or API down
        A-->>Owner: rule-based Scheduler.explain_plan fallback
    end
```

## 3. Fix-my-day agent (plan, act, verify, approve)

```mermaid
sequenceDiagram
    actor Owner
    participant AG as agent.py
    participant SB as Sandbox (deep copy of schedule)
    participant LLM as Groq gpt-oss-120b (tool calls)
    participant T as assets/agent_traces/

    Owner->>AG: run("Fix my day")
    AG->>SB: copy owner, count conflicts_before
    loop up to 10 steps
        AG->>LLM: messages + tool schemas
        LLM-->>AG: tool call (list_tasks / find_conflicts / find_next_slot / move_task / search_care_notes)
        AG->>SB: execute tool (whitelisted, args validated)
        SB-->>AG: observation
        AG->>LLM: tool result message
    end
    LLM-->>AG: finish (or plain-text reply)
    AG->>AG: verify independently: conflicts before/after, budget, medication moves
    AG->>T: write markdown trace
    AG-->>Owner: moves + verification + code-written summary
    alt Owner approves
        Owner->>AG: apply(run)
        AG->>AG: copy moves onto the real schedule
    else Owner discards
        AG-->>Owner: real schedule unchanged
    end
```

## 4. Reliability and evaluation loop

```mermaid
flowchart LR
    C[("eval/eval_cases.json: 8 parse, 9 coach, 5 guardrail")] --> E["eval/run_eval.py"]
    E --> M1["specialized + RAG"]
    E --> M2["specialized, no RAG"]
    E --> M3["baseline prompt"]
    M1 & M2 & M3 --> SC["Score raw output: fields, schema, vet flag, style, knowledge facts, citations"]
    E --> GR["Guardrail cases through full pipeline"]
    SC --> REP["assets/eval_results.md + eval/results.json"]
    GR --> REP
    REP --> FIX["Read failures, tighten prompt/guardrails"]
    FIX --> E
    PT["pytest: 53 offline tests, fake model clients"] --> CI["Runs without a key or network"]
```
