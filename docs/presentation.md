# PawPal AI — presentation outline (5–7 minutes)

Slide-by-slide plan with speaker notes and the commands to run live. Times are targets.

---

## 1. The problem (0:30)
**On screen:** "Busy pet owners juggle walks, meds and feeding across several pets. Forms are tedious; chatbots give generic advice and can be unsafe."
**Say:** PawPal+ (my Module 2 project) was a rule-based scheduler: forms in, a priority-first daily plan out, plus conflict warnings. It had no AI and a one-sentence explanation.

## 2. What I built (0:45)
**On screen:** the four AI features as icons:
1. Plain-English task entry (specialized model)
2. Care Coach grounded in the schedule plus a pet-care knowledge base (RAG)
3. Fix-my-day agent (tool calls → verify → human approval)
4. Guardrails + evaluation harness
**Say:** The design rule throughout: deterministic code owns the facts and safety; the model handles language and planning.

## 3. Architecture (0:45)
**On screen:** `diagrams/architecture.mmd` (rendered in the README on GitHub).
**Say:** Walk one request through it: input guardrails → emergency detector → scheduler context + retrieved notes + few-shot → Groq → validation/retry → human confirmation → scheduler. Point at the dotted logging and testing edges.

## 4. Live demo (2:00)
```bash
python pawpal_ai_cli.py add "Whiskers needs her kidney meds at 7:30pm every day"
python pawpal_ai_cli.py review "Nibbles seems bored in the afternoons, any ideas?"
python pawpal_ai_cli.py review "Biscuit ate a bunch of grapes off the counter"
python pawpal_ai_cli.py fix
```
**Say while it runs:**
- The kidney meds become a high-priority daily task, validated against real pets.
- The rabbit answer cites `rabbit_care#…` notes; species-specific advice came from retrieval, not the model's memory.
- Grapes → emergency message with **no model call**.
- The agent's steps print as it works; point out that it plans before moving, verifies conflicts 1 → 0, flags that Grooming is still over budget, and asks before applying.
**Backup if Wi-Fi or Groq fails:** show `assets/demo_run.txt`, `assets/agent_run.txt` and the fallback message. The app degrades to rule-based behavior, which is itself a feature.

## 5. Does it actually work? (1:00)
**On screen:** the summary table from `assets/eval_results.md` (specialized vs no-RAG vs baseline) and "53/53 offline tests".
**Say:** The specialized prompt made the parser reliable (baseline scheduled "buy milk" as a pet task). Retrieval raised the share of answers that contain the key care fact. The first eval run showed the coach missing vet flags on thirst and dosing questions; fixing the rules took it from 4/6 to 6/6.

## 6. What went wrong and what I changed (0:45)
**On screen:** two quotes from the traces.
- The coach claimed the scheduler "moved" a task. The scheduler can't do that, so suggestions are now phrased as suggestions.
- The agent claimed "all tasks fit" while Grooming was over budget, so the summary is now written by code from the verified sandbox, not by the model.
**Say:** Most reliability gains came from measuring, not from bigger prompts.

## 7. Limits and ethics (0:30)
- Keyword safety nets miss paraphrases ("chewed my Advil bottle").
- The knowledge base is small and dog/cat-heavy; confidence scores are poorly calibrated.
- PawPal never gives doses and routes symptoms to a vet.

## 8. What this says about me / next steps (0:30)
**Say:** your portfolio sentence from the README.
**Next:** embedding-based retrieval, a larger vet-reviewed knowledge base, and an LLM-as-judge or human rating for advice quality.
