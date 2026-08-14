#!/usr/bin/env python3
"""The whole offline measurement. No network, no cost, no API key.

    python scripts/offline_demo.py
    python scripts/offline_demo.py --days 730 --json audit/offline.json

FOUR QUESTIONS:

  1 THE STACK        how much of it can report its own input freshness
  2 THE YEAR         how much of it is spent past a staleness budget, and how
                     much of that with nothing anywhere saying so
  3 THE ARTIFACT     how often the view an accreditation review receives is
                     IDENTICAL for a healthy enclave and a rotten one
  4 ONE DAY          the truth beside the health output, so the gap is a thing
                     a reader can look at rather than a percentage

What this models and what it does not. A deployment PATTERN, not any vendor's
software. Cadences, miss rates and budgets are stated constants in
enclave/timeline.py and every result scales with them. Question 3 is the
exception and is the reason it leads the README: it is a property of the
artifact's SHAPE, and it holds for any rates that produce both strata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enclave import indistinguishable                           # noqa: E402
from enclave.components import COMPONENTS, counts               # noqa: E402
from enclave.health import health_view, truth_view              # noqa: E402
from enclave.timeline import simulate, summarize                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    print("airgapped-ai-bundle -- offline measurement")
    print(f"no model was called   simulated days: {args.days}\n")

    c = counts()
    print("1. THE STACK")
    print(f"   {c['components']} components depend on something outside the "
          f"boundary")
    print(f"   {c['announces']} can report their own input age; "
          f"{c['silent']} cannot")
    print(f"   silent: {', '.join(c['silent_keys'])}")

    tl = simulate(args.days)
    s = summarize(tl)
    print(f"\n2. THE YEAR ({s['days']} days)")
    print(f"   {'':<38} {'incl. clock':>12} {'excl. clock':>12}")
    print(f"   {'something past its budget':<38} "
          f"{s['days_with_something_stale_pct']:>11.1f}% "
          f"{s['days_with_something_stale_excluding_clock'] / s['days'] * 100:>11.1f}%")
    print(f"   {'stale with NOTHING anywhere saying so':<38} "
          f"{s['days_stale_with_nothing_saying_so_pct']:>11.1f}% "
          f"{s['days_stale_with_nothing_saying_so_excluding_clock_pct']:>11.1f}%")
    print("   The clock is past a 7-day budget on most days by construction --")
    print("   an air gap has no NTP -- and tests/test_enclave.py proves that")
    print("   staleness cannot change any other verdict. Act on the right"
          " column.")

    print(f"\n   {'component':<19}{'budget':>7}{'stale days':>12}"
          f"{'max age':>9}  reports age")
    for comp in COMPONENTS:
        p = s["per_component"][comp.key]
        print(f"   {comp.key:<19}{p['budget_days']:>7}"
              f"{p['stale_days']:>7} ({p['stale_pct']:>4.1f}%)"
              f"{p['max_age_days']:>9}  {comp.health_reports_age}")

    ind = indistinguishable.measure(args.days)
    print("\n3. THE ARTIFACT: how often it cannot tell the two apart")
    print(f"   distinct views seen on clean days   {ind['distinct_views_clean']:>5}")
    print(f"   distinct views seen on silent days  {ind['distinct_views_silent']:>5}")
    print(f"   views occurring in BOTH strata      {ind['views_occurring_in_both']:>5}")
    print(f"   -> {ind['clean_days_ambiguous']} of {ind['clean_days']} clean "
          f"days ({ind['clean_days_ambiguous_pct']}%) produce a view that also")
    print(f"      occurs on a day something was months past budget")
    print(f"   -> {ind['silent_days_ambiguous']} of {ind['silent_days']} "
          f"silent days ({ind['silent_days_ambiguous_pct']}%) produce a view "
          f"that also")
    print(f"      occurs on a day when nothing was wrong at all")
    print("   The bytes are identical. No reader can distinguish them because")
    print("   there is nothing there to distinguish.")

    worst = max((d for d in tl if d.silent_stale and not d.announced),
                key=lambda d: len(d.silent_stale), default=None)
    if worst:
        print(f"\n4. ONE DAY -- day {worst.day}")
        t = truth_view(worst)
        print(f"   truth: past budget -> {', '.join(t['stale'])}")
        h = health_view(worst)
        print(f"   health output overall: {h['overall']}")
        for key, entry in h["components"].items():
            print(f"     {key:<19} {entry['status']:<9} {entry['detail']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "note": "A deployment pattern, not any vendor's software. Rates "
                    "are stated constants in enclave/timeline.py.",
            "stack": c, "year": s, "artifact": ind,
        }, indent=2, default=str) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
