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
from enclave.components import BY_KEY, COMPONENTS, counts       # noqa: E402
from enclave.health import health_view, truth_view              # noqa: E402
from enclave.sampler import HARMLESS                            # noqa: E402
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
    # Every conclusion needs something to have been compared. A window too
    # short to hold both strata answers this question with "0 of 0 (0.0%)", and
    # a fixed sentence printed underneath that is a definite finding drawn from
    # a comparison of nothing. A short window is not a window in which the
    # artifact is unambiguous; it is a window in which the question was not
    # asked, and the two must not print the same thing.
    #
    # The qualifier on the clean-day line is "past budget with nothing saying
    # so" rather than "months past budget", because the collision is per VIEW:
    # a clean day's view is shared with SOME silent day, and only 88 of the
    # 210 share it with a day something was 60+ days past budget. 64 share it
    # with a day on which nothing was more than 29 days past, and the weakest
    # shares it with a day ONE day past. What holds of EVERY silent partner
    # day is what the line says, and it is also the property being measured.
    if not ind["clean_days"] or not ind["silent_days"]:
        print(f"   NOT MEASURED: this window has {ind['clean_days']} clean and "
              f"{ind['silent_days']} silent day(s), so there was no")
        print("   pair to compare and this question was not answered. Use a "
              "longer window.")
    else:
        print(f"   -> {ind['clean_days_ambiguous']} of {ind['clean_days']} clean "
              f"days ({ind['clean_days_ambiguous_pct']}%) produce a view that also")
        print(f"      occurs on a day something was past budget with nothing "
              f"saying so")
        print(f"   -> {ind['silent_days_ambiguous']} of {ind['silent_days']} "
              f"silent days ({ind['silent_days_ambiguous_pct']}%) produce a view "
              f"that also")
        print(f"      occurs on a day when nothing but the clock was stale")
        if ind["views_occurring_in_both"]:
            print("   The bytes are identical. No reader can distinguish them "
                  "because")
            print("   there is nothing there to distinguish.")
        else:
            print("   No view occurred in both strata in this window, so nothing "
                  "here is")
            print("   indistinguishable. That is a measured result, not a "
                  "comparison skipped.")

    # Ranked excluding the clock, for the reason summarize() gives: the clock
    # is past a 7-day budget on most days by construction, so counting it lets
    # a day on which NOTHING material is stale outrank one on which three
    # things are. On the default 730-day window the pick is day 226 either
    # way; on a short window it was the difference between an example and a
    # non-example.
    one_day = {}
    worst = max((d for d in tl
                 if set(d.silent_stale) - HARMLESS and not d.announced),
                key=lambda d: len(set(d.silent_stale) - HARMLESS), default=None)
    if worst:
        print(f"\n4. ONE DAY: day {worst.day}")
        t = truth_view(worst)
        print(f"   truth: past budget -> {', '.join(t['stale'])}")
        h = health_view(worst)
        print(f"   health output overall: {h['overall']}")
        for key, entry in h["components"].items():
            print(f"     {key:<19} {entry['status']:<9} {entry['detail']}")
        # Emitted as evidence, not just printed. A number nothing derives is
        # a number nothing can contradict, and a worked example is where that
        # bites hardest: this day's largest revocation gap is ONE day past
        # budget, while the same component's two-year maximum age is 89, and
        # the two are one plausible sentence apart. Emitting the day's own
        # arithmetic lets scripts/check_readme_numbers.py hold the prose to
        # it, as it holds every other published figure here.
        one_day = {
            "day": worst.day,
            "health_overall": h["overall"],
            "past_budget": [
                {"key": k,
                 "age_days": worst.age_days[k],
                 "budget_days": BY_KEY[k].budget_days,
                 "days_past": worst.age_days[k] - BY_KEY[k].budget_days,
                 "announces": not BY_KEY[k].is_silent()}
                for k in worst.stale],
        }
    else:
        # Saying why, instead of printing nothing. Dropping the section in
        # silence is the same defect as a fixed conclusion over an empty
        # comparison, one step quieter: a reader who asked for four
        # measurements and got three cannot tell an empty result from a
        # section that was never reached.
        print(f"\n4. ONE DAY: none to show. No day in this {args.days}-day "
              f"window has")
        print("   something past budget with nothing saying so, so there is no "
              "example")
        print("   of the gap this repository is about. Use a longer window.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "note": "A deployment pattern, not any vendor's software. Rates "
                    "are stated constants in enclave/timeline.py.",
            "stack": c, "year": s, "artifact": ind, "one_day": one_day,
        }, indent=2, default=str) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
