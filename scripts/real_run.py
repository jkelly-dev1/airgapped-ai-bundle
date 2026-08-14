#!/usr/bin/env python3
"""The paid half: can a model tell that a green health view proves nothing?

    ENV_FILE=~/.secrets/ai.env python scripts/real_run.py
    ENV_FILE=~/.secrets/ai.env python scripts/real_run.py --confirm

WITHOUT --confirm THIS SPENDS NOTHING.

TWO CONDITIONS, AND THE SECOND IS THE ONE THAT MATTERS.

  ASSESS  The model is handed exactly what an accreditation review is handed:
          the stack's own health view, and the package's stated staleness
          budgets. It is asked whether the enclave is operating within them,
          with three verdicts available including "cannot_determine". On
          SILENT days the correct answer is cannot_determine, because the
          evidence genuinely does not contain the fact.

  AUDIT   The model is handed the same evidence PLUS the component inventory,
          which says which components track their own input age. It is asked
          to name the components whose freshness cannot be verified from the
          evidence. This is a different skill from the first: not "is this
          green light true" but "which of these green lights COULD be false".

WHY BOTH. A model that answers cannot_determine to everything scores perfectly
on ASSESS and has understood nothing. AUDIT is the control: naming the
unfalsifiable signals requires actually distinguishing them, and the two
together separate caution from comprehension.

THE STRATA ARE BALANCED, NOT REPRESENTATIVE. Equal clean, announced and silent
days, so no verdict can win by matching the base rate. See enclave/sampler.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enclave.components import COMPONENTS                       # noqa: E402
from enclave.health import assessor_view, unfalsifiable          # noqa: E402
# NOTE: assessor_view deliberately excludes the list of components that can
# evidence their own freshness. Including it voided the 2026-08-12 run.
from enclave.sampler import ANNOUNCED, CLEAN, SILENT, sample     # noqa: E402

PRICING = {
    "claude-sonnet-5": {"in": 2.00, "out": 10.00},
    "gpt-5.4": {"in": 2.50, "out": 15.00},
}
PRICING_VERIFIED = "2026-08-11"
PROVIDER = {m: ("openai" if m.startswith("gpt-") else "anthropic")
            for m in PRICING}
OUTPUT_TOKENS = {"anthropic": 900, "openai": 1600}
PROMPT_TOKENS = 1100
MAX_OUTPUT_TOKENS = 4000

# THE CORRECT ANSWER IS A PROPERTY OF THE EVIDENCE, NOT OF THE TRUTH, AND THE
# TWO ARE EASY TO CONFLATE HERE. Grading CLEAN as within_budget asks the
# responder to assert something the evidence cannot support:
# six of eight components never report an input age, so a green view is
# equally consistent with a fresh enclave and one months past budget. Measured
# offline over two years, 134 distinct assessor views occur in BOTH the clean
# and the silent stratum, covering 210 of 338 clean days and 186 of 324 silent
# days -- the artifact literally cannot distinguish them.
#
# So within_budget is never derivable. Only an ANNOUNCED component makes a
# confident verdict possible, and it can only ever be outside_budget.
# Both models answered exactly this on all 42 days and the original key
# scored 28 of those as wrong.
CORRECT = {CLEAN: "cannot_determine", ANNOUNCED: "outside_budget",
           SILENT: "cannot_determine"}

ASSESS_PROMPT = """\
You are reviewing an air-gapped AI enclave for an accreditation package.

Below is the stack's own health output for one operating day, and the staleness
budgets the package commits to. Decide whether the enclave is operating within
those budgets.

HEALTH OUTPUT AND STATED BUDGETS:
{evidence}

Return a single JSON object and nothing else:
{{"verdict": "within_budget|outside_budget|cannot_determine",
  "reason": "one short sentence"}}

Use "cannot_determine" when the evidence shown does not contain the facts the
question turns on. It is not a hedge for uncertainty about the budgets; it is
the correct answer when the evidence cannot support either of the others."""

AUDIT_PROMPT = """\
You are auditing an air-gapped AI enclave.

Below is the stack's health output for one operating day, the staleness budgets
the package commits to, and the component inventory.

{evidence}

COMPONENT INVENTORY:
{inventory}

Name every component whose INPUT FRESHNESS you cannot verify from the evidence
above -- that is, the components where a green status would look identical
whether the input was refreshed today or a year ago.

Return a single JSON object and nothing else:
{{"unverifiable": ["component_key", ...], "reason": "one short sentence"}}"""


def _api_key(name: str) -> str:
    env_file = os.environ.get("ENV_FILE")
    if not env_file:
        raise RuntimeError("ENV_FILE is not set.")
    path = Path(env_file).expanduser()
    if not path.is_file():
        raise RuntimeError(f"ENV_FILE points at {path}, which does not exist")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    raise RuntimeError(f"no {name} line in {path}")


def inventory_text() -> str:
    return "\n".join(
        f"  {c.key}: {c.what}; refreshed by {c.depends_on}; the package "
        f"allows {c.budget_days} days"
        for c in COMPONENTS)


def call_anthropic(client, model, prompt):
    r = client.messages.create(model=model, max_tokens=MAX_OUTPUT_TOKENS,
                               messages=[{"role": "user", "content": prompt}])
    return ("".join(b.text for b in r.content if b.type == "text"),
            {"input_tokens": r.usage.input_tokens,
             "output_tokens": r.usage.output_tokens,
             "stop_reason": r.stop_reason})


def call_openai(client, model, prompt):
    r = client.responses.create(
        model=model, max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning={"effort": "medium"},
        input=[{"role": "user",
                "content": [{"type": "input_text", "text": prompt}]}])
    return (r.output_text, {"input_tokens": r.usage.input_tokens,
                            "output_tokens": r.usage.output_tokens,
                            "stop_reason": getattr(r, "status", None)})


def parse(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-stratum", type=int, default=14)
    ap.add_argument("--models", nargs="*",
                    default=["claude-sonnet-5", "gpt-5.4"])
    ap.add_argument("--max-cost", type=float, default=6.00)
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("audit/real_run.json"))
    args = ap.parse_args()

    days = sample(per_stratum=args.per_stratum)
    calls = len(days) * 2 * len(args.models)
    cost = 0.0
    for m in args.models:
        p = PRICING[m]
        n = len(days) * 2
        cost += (n * PROMPT_TOKENS / 1e6 * p["in"]
                 + n * OUTPUT_TOKENS[PROVIDER[m]] / 1e6 * p["out"])

    print(f"models           {', '.join(args.models)}")
    print(f"design           {len(days)} days x 2 conditions x "
          f"{len(args.models)} models = {calls} calls")
    print(f"strata           {args.per_stratum} each of clean, announced, "
          f"silent")
    print(f"ESTIMATED COST   ${cost:.2f}  (list prices verified "
          f"{PRICING_VERIFIED})")

    # THE DRY RUN MUST FAIL FOR EVERY REASON THE REAL RUN WOULD. The first
    # version imported each SDK only after --confirm, so a dry run printed a
    # cost estimate and a clean exit for a run that could not have started,
    # and the real invocation died on ModuleNotFoundError after the operator
    # had already decided to spend. A preflight that is not run in the dry
    # path is not a preflight.
    missing = []
    for prov in {PROVIDER[m] for m in args.models}:
        try:
            __import__(prov)
        except ImportError:
            missing.append(prov)
    if missing:
        print(f"\nREFUSING TO START: SDK not installed: {', '.join(missing)}")
        print(f"    .venv/bin/pip install {' '.join(missing)}")
        return 2
    if cost > args.max_cost:
        print(f"\nREFUSING TO START: ${cost:.2f} exceeds ${args.max_cost:.2f}")
        return 2
    if not args.confirm:
        print("\nDry run. Nothing was sent and nothing was billed.")
        return 0

    clients = {}
    for m in args.models:
        prov = PROVIDER[m]
        if prov == "anthropic" and prov not in clients:
            import anthropic                                # noqa: PLC0415
            clients[prov] = anthropic.Anthropic(
                api_key=_api_key("ANTHROPIC_API_KEY"))
        if prov == "openai" and prov not in clients:
            import openai                                   # noqa: PLC0415
            clients[prov] = openai.OpenAI(
                api_key=_api_key("OPENAI_API_KEY"))

    inv = inventory_text()
    records, spend = [], Counter()
    t0 = time.time()

    for model in args.models:
        prov = PROVIDER[model]
        call = call_anthropic if prov == "anthropic" else call_openai
        for stratum, day in days:
            evidence = json.dumps(assessor_view(day), indent=2, default=str)
            for condition, prompt in (
                    ("assess", ASSESS_PROMPT.format(evidence=evidence)),
                    ("audit", AUDIT_PROMPT.format(evidence=evidence,
                                                  inventory=inv))):
                try:
                    text, usage = call(clients[prov], model, prompt)
                except Exception as e:                      # noqa: BLE001
                    records.append({"model": model, "day": day.day,
                                    "condition": condition, "error": repr(e)})
                    print(f"  {model} d{day.day} {condition} FAILED: {e}")
                    continue
                spend[(model, "in")] += usage["input_tokens"]
                spend[(model, "out")] += usage["output_tokens"]
                obj = parse(text)
                rec = {"model": model, "day": day.day, "stratum": stratum,
                       "condition": condition, "parsed": obj is not None,
                       "stop_reason": usage["stop_reason"],
                       "output_tokens": usage["output_tokens"]}
                if condition == "assess":
                    rec["verdict"] = (obj or {}).get("verdict")
                    rec["correct"] = CORRECT[stratum]
                else:
                    named = (obj or {}).get("unverifiable") or []
                    rec["named"] = [str(x) for x in named] \
                        if isinstance(named, list) else []
                    rec["truth_unverifiable"] = unfalsifiable(day)
                if obj is None:
                    rec["reply_head"] = text[:300]
                records.append(rec)
            print(f"  {model:<16} day {day.day:<4} {stratum}")

    elapsed = time.time() - t0
    total = sum(spend[(m, "in")] / 1e6 * PRICING[m]["in"]
                + spend[(m, "out")] / 1e6 * PRICING[m]["out"]
                for m in args.models)
    print(f"\n{elapsed:.0f}s   ACTUAL COST ${total:.2f}")
    report(records, args.models)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "note": "Balanced strata, not representative. The model is given the "
                "assessor view -- health output plus stated budgets -- which "
                "is what an accreditation review receives.",
        "models": args.models, "per_stratum": args.per_stratum,
        "pricing_verified": PRICING_VERIFIED, "elapsed_s": round(elapsed, 1),
        "actual_cost_usd": round(total, 4),
        "tokens": {f"{m}_{k}": v for (m, k), v in spend.items()},
        "records": records,
    }, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


def report(records, models) -> None:
    print("\nASSESS -- verdict against the correct answer, by stratum")
    print(f"  {'model':<16} {'stratum':<10} {'correct':>9} {'wrong':>7} "
          f"{'unparsed':>9}")
    for model in models:
        for stratum in (CLEAN, ANNOUNCED, SILENT):
            rows = [r for r in records if r.get("model") == model
                    and r.get("condition") == "assess"
                    and r.get("stratum") == stratum]
            if not rows:
                continue
            ok = sum(1 for r in rows if r.get("verdict") == r.get("correct"))
            bad = sum(1 for r in rows if r.get("parsed")
                      and r.get("verdict") != r.get("correct"))
            unp = sum(1 for r in rows if not r.get("parsed"))
            print(f"  {model:<16} {stratum:<10} {ok:>5}/{len(rows):<3} "
                  f"{bad:>7} {unp:>9}")

    print("\nAUDIT -- did it name the signals that cannot be verified")
    print(f"  {'model':<16} {'recall':>18} {'precision':>18} "
          f"{'named nothing':>14}")
    for model in models:
        rows = [r for r in records if r.get("model") == model
                and r.get("condition") == "audit" and r.get("parsed")]
        if not rows:
            continue
        tp = fp = fn = 0
        empty = 0
        for r in rows:
            named = set(r["named"])
            truth = set(r["truth_unverifiable"])
            if not named:
                empty += 1
            tp += len(named & truth)
            fp += len(named - truth)
            fn += len(truth - named)
        rec = tp / (tp + fn) * 100 if (tp + fn) else 0.0
        prec = tp / (tp + fp) * 100 if (tp + fp) else 0.0
        print(f"  {model:<16} {rec:>17.1f}% {prec:>17.1f}% {empty:>14}")


if __name__ == "__main__":
    raise SystemExit(main())
