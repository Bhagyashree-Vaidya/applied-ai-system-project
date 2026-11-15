"""Evaluation harness for PawPal AI.

Compares three configurations of the same Groq model on fixed cases:
  * specialized         - Care Coach prompt + few-shot + retrieved care notes (RAG)  [what the app runs]
  * specialized_no_rag  - Care Coach prompt + few-shot, no retrieval                  [isolates RAG]
  * baseline            - one-line prompt with the JSON keys                           [isolates specialization]

    python -m eval.run_eval              # needs GROQ_API_KEY
    python -m eval.run_eval --only specialized

Scores the *raw* model output for each mode (before guardrails repair anything), then runs
the guardrail cases through the full assistant pipeline. Prints a summary and writes
assets/eval_results.md and eval/results.json.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime

from pawpal_ai import PawPalAssistant
from pawpal_ai.config import ROOT
from pawpal_ai.guardrails import has_dosage
from pawpal_ai.llm import GroqJSONClient, LLMError
from pawpal_ai.sample import sample_owner
from pawpal_ai.specialist import coach_messages, parse_messages

CASES = json.loads((ROOT / "eval" / "eval_cases.json").read_text())
PET_NAMES = ("Biscuit", "Whiskers", "Nibbles")
CONFLICT_WORDS = re.compile(r"overlap|conflict|clash|same time|8:15|back[- ]to[- ]back", re.I)


def _norm(key, value):
    if value is None:
        return None
    if key == "time":
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value).strip())
        return f"{int(m.group(1)):02d}:{m.group(2)}" if m else str(value)
    if key in ("day_offset", "duration_minutes"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if isinstance(value, str):
        return value.strip().lower()
    return value


def score_parse(raw: dict | None, expect: dict) -> dict:
    if raw is None:
        return {"pass": False, "matched": 0, "total": len(expect), "misses": ["no valid JSON"]}
    misses = [f"{k}: want {v!r} got {raw.get(k)!r}" for k, v in expect.items()
              if _norm(k, raw.get(k, False if k == "is_task" else None)) != _norm(k, v)]
    return {"pass": not misses, "matched": len(expect) - len(misses), "total": len(expect), "misses": misses}


def score_coach(raw: dict | None, expect: dict) -> dict:
    if raw is None:
        return {"pass": False, "checks": {"schema": False}, "misses": ["no valid JSON"]}
    tips = raw.get("tips") if isinstance(raw.get("tips"), list) else None
    text = f"{raw.get('summary', '')} {' '.join(map(str, tips or []))}"
    checks = {
        "schema": isinstance(raw.get("summary"), str) and bool(raw["summary"].strip()) and tips is not None
                  and isinstance(raw.get("vet_flag"), bool),
        "tip_limits": tips is not None and len(tips) <= 3 and all(len(str(t).split()) < 25 for t in tips),
        "no_dosage": not has_dosage(text),
        "vet_flag": raw.get("vet_flag") == expect["vet_flag"],
        "in_scope": raw.get("in_scope", True) == expect["in_scope"],
    }
    if expect["in_scope"]:
        checks["grounded"] = any(n in text for n in PET_NAMES)
    if expect.get("mentions_conflict"):
        checks["conflict"] = bool(CONFLICT_WORDS.search(text))
    if expect.get("keywords"):
        checks["knowledge"] = any(k.lower() in text.lower() for k in expect["keywords"])
    misses = [k for k, ok in checks.items() if not ok]
    return {"pass": not misses, "checks": checks, "misses": misses}


def call(client, messages):
    start = time.perf_counter()
    try:
        raw = client.complete_json(messages)
    except LLMError as exc:
        raw = None
        print(f"   ! {exc}")
    return raw, time.perf_counter() - start


MODES = {"specialized": ("specialized", True), "specialized_no_rag": ("specialized", False),
         "baseline": ("baseline", False)}


def run_mode(client, mode: str, ai: PawPalAssistant) -> dict:
    pets = ai._pets()
    today = f"{ai.now:%A %Y-%m-%d}"
    context = ai.schedule_context()
    out = {"parse": [], "coach": []}
    prompt_mode, rag = MODES[mode]
    for case in CASES["parse"]:
        if mode == "specialized_no_rag":
            break  # parsing does not use retrieval; identical to "specialized"
        raw, secs = call(client, parse_messages(case["input"], pets, today, prompt_mode))
        out["parse"].append({"input": case["input"], "raw": raw, "secs": round(secs, 2),
                             **score_parse(raw, case["expect"])})
    for case in CASES["coach"]:
        chunks = ai.retrieve(case["question"]) if rag else []
        notes = "\n".join(c.cite() for c in chunks)
        raw, secs = call(client, coach_messages(context, case["question"], prompt_mode, notes))
        out["coach"].append({"question": case["question"] or "(review my day)", "raw": raw,
                             "retrieved": [c.id for c in chunks],
                             "secs": round(secs, 2), **score_coach(raw, case["expect"])})
    return out


def summarize(mode: str, res: dict) -> dict:
    p, c = res["parse"], res["coach"]
    confs = [r["raw"].get("confidence") for r in p + c
             if r["raw"] and isinstance(r["raw"].get("confidence"), (int, float))]
    kc = [r for r in c if "knowledge" in r["checks"]]
    return {
        "mode": mode,
        "parse_pass": f"{sum(r['pass'] for r in p)}/{len(p)}" if p else "n/a",
        "parse_field_acc": round(sum(r["matched"] for r in p) / sum(r["total"] for r in p), 2) if p else "n/a",
        "coach_pass": f"{sum(r['pass'] for r in c)}/{len(c)}",
        "vet_flag_acc": f"{sum(r['checks'].get('vet_flag', False) for r in c)}/{len(c)}",
        "style_ok": f"{sum(r['checks'].get('tip_limits', False) for r in c)}/{len(c)}",
        "knowledge_facts": f"{sum(r['checks']['knowledge'] for r in kc)}/{len(kc)}",
        "cited_sources": f"{sum(bool(r['raw'] and r['raw'].get('sources')) for r in c)}/{len(c)}",
        "avg_confidence": round(sum(confs) / len(confs), 2) if confs else None,
        "avg_latency_s": round(sum(r["secs"] for r in p + c) / len(p + c), 2),
    }


def run_guardrails(client, now) -> list[dict]:
    ai = PawPalAssistant(sample_owner(now), client, now=now)
    rows = []
    for case in CASES["guardrail"]:
        result = ai.propose_task(case["input"])
        rows.append({"input": case["input"] or "(empty)", "expected": case["expect_kind"], "got": result.kind,
                     "pass": result.kind == case["expect_kind"], "message": result.message})
    return rows


def write_report(model: str, summaries: list[dict], results: dict, guards: list[dict]) -> str:
    lines = [f"# PawPal AI evaluation results", "",
             f"Model: `{model}` on Groq. Run: {datetime.now():%Y-%m-%d %H:%M}. "
             f"Command: `python -m eval.run_eval`", "", "## Summary", "",
             "| Mode | Parse pass | Parse field accuracy | Coach pass | Vet-flag correct | Style limits met | Knowledge facts | Cited sources | Avg confidence | Avg latency (s) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        lines.append(f"| {s['mode']} | {s['parse_pass']} | {s['parse_field_acc']} | {s['coach_pass']} | "
                     f"{s['vet_flag_acc']} | {s['style_ok']} | {s['knowledge_facts']} | {s['cited_sources']} | "
                     f"{s['avg_confidence']} | {s['avg_latency_s']} |")
    lines += ["", "## Guardrail cases (full pipeline, specialized mode)", "",
              "| Input | Expected | Got | Result |", "|---|---|---|---|"]
    for g in guards:
        lines.append(f"| {g['input']} | {g['expected']} | {g['got']} | {'PASS' if g['pass'] else 'FAIL'} |")
    for mode, res in results.items():
        lines += ["", f"## Details: {mode}", "", "| Task-parse input | Result | Misses |", "|---|---|---|"]
        for r in res["parse"]:
            lines.append(f"| {r['input']} | {'PASS' if r['pass'] else 'FAIL'} | {'; '.join(r['misses']) or '-'} |")
        lines += ["", "| Coach question | Result | Failed checks | Retrieved notes |", "|---|---|---|---|"]
        for r in res["coach"]:
            lines.append(f"| {r['question']} | {'PASS' if r['pass'] else 'FAIL'} | {', '.join(r['misses']) or '-'} | "
                         f"{', '.join(r.get('retrieved', [])) or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(MODES))
    args = parser.parse_args()

    client = GroqJSONClient()
    now = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    modes = [args.only] if args.only else list(MODES)
    results, summaries = {}, []
    for mode in modes:
        print(f"Running {mode} mode ...")
        results[mode] = run_mode(client, mode, PawPalAssistant(sample_owner(now), client, now=now))
        summaries.append(summarize(mode, results[mode]))
    print("Running guardrail cases ...")
    guards = run_guardrails(client, now)

    print("\n" + " | ".join(summaries[0].keys()))
    for s in summaries:
        print(" | ".join(str(v) for v in s.values()))
    print(f"guardrails: {sum(g['pass'] for g in guards)}/{len(guards)} passed")
    for mode, res in results.items():
        for r in res["parse"] + res["coach"]:
            if not r["pass"]:
                print(f"  FAIL [{mode}] {r.get('input', r.get('question'))}: {r['misses']}")

    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "eval_results.md").write_text(write_report(client.model, summaries, results, guards))
    (ROOT / "eval" / "results.json").write_text(json.dumps(
        {"model": client.model, "summaries": summaries, "results": results, "guardrails": guards}, indent=2))
    print("\nWrote assets/eval_results.md and eval/results.json")


if __name__ == "__main__":
    main()
