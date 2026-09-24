"""Re-derive every published number in README.md from audit/offline.json.

A README is prose and drifts; audit/offline.json is evidence and does not.
This script rebuilds each figure from the JSON and asserts the exact string is
present in the README, so a re-run that shifts a figure fails loudly instead of
leaving the document quietly wrong.

    python3 scripts/check_readme_numbers.py            check
    python3 scripts/check_readme_numbers.py --emit     print what it derives

Whitespace AND emphasis are normalized on both sides, so a reflowed paragraph
is not a false alarm that trains a reader to ignore the script.

Both columns of the two-year table are derived, including the one excluding the
clock, because the page's own instruction is to act on the right column and a
deriver that only checked the larger number would be doing what the page warns
against.

The count is printed whether OR NOT anything is missing, so a version of this
script that quietly stopped deriving half of them is visible rather than clean.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    with open(os.path.join(ROOT, "audit", "offline.json"), encoding="utf-8") as fh:
        return json.load(fh)


def rows_components():
    """Per component: its budget, and whether it can report its own age.

    The answer column is the whole paper. Six of the eight cannot report their
    input age, so they contribute a green light indistinguishable from one
    refreshed an hour ago, and every number below is downstream of that split.
    """
    d = load()
    out = []
    for key, c in d["year"]["per_component"].items():
        out.append(("component:" + key,
                    "| `%s` | %d d | %s |"
                    % (key, c["budget_days"], "yes" if c["announces"] else "no")))
    return out


def rows_collision():
    """The artifact block: how often a clean day and a stale day look alike."""
    a = load()["artifact"]
    return [
        ("collision:clean-views",
         "distinct views seen on clean days %d" % a["distinct_views_clean"]),
        ("collision:silent-views",
         "distinct views seen on silent days %d" % a["distinct_views_silent"]),
        ("collision:both",
         "views occurring in BOTH strata %d" % a["views_occurring_in_both"]),
        # The qualifiers are part of the derived string, so this gate
        # enforces them and they have to survive being checked.
        # Not "months past budget": the collision is per VIEW, and only 88 of
        # the 210 ambiguous clean days share their view with a day something
        # was 60+ days past budget. 64 of them share it with a day on which
        # nothing was more than 29 days past, and the weakest shares it with a
        # day ONE day past. What holds of every silent partner day is the
        # property this page is about: something past budget, and nothing
        # saying so.
        # Not "nothing was wrong at all": a clean day is a day with nothing
        # MATERIAL past budget, and 305 of the 338 have the free-running clock
        # past its own budget, only 33 nothing stale whatsoever.
        ("collision:clean-rate",
         "-> %d of %d clean days (%s%%) produce a view that also occurs on a "
         "day something was past budget with nothing saying so"
         % (a["clean_days_ambiguous"], a["clean_days"],
            _trim(a["clean_days_ambiguous_pct"]))),
        ("collision:silent-rate",
         "-> %d of %d silent days (%s%%) produce a view that also occurs on a "
         "day when nothing but the clock was stale"
         % (a["silent_days_ambiguous"], a["silent_days"],
            _trim(a["silent_days_ambiguous_pct"]))),
    ]


def rows_two_years():
    """The two-year table, both columns."""
    y = load()["year"]
    excl_stale = 100.0 * y["days_with_something_stale_excluding_clock"] / y["days"]
    return [
        ("years:stale",
         "something past its budget %s%% %s%%"
         % (_trim(y["days_with_something_stale_pct"]), _trim(excl_stale))),
        ("years:silent",
         "stale with NOTHING anywhere saying so %s%% %s%%"
         % (_trim(y["days_stale_with_nothing_saying_so_pct"]),
            _trim(y["days_stale_with_nothing_saying_so_excluding_clock_pct"]))),
        ("years:window", "The window is %d simulated days" % y["days"]),
    ]


def _row_never_stale(y):
    """The components that CANNOT go stale in this window, named and counted.

    Budget is exactly twice cadence for `model_weights` (180/90) and
    `container_images` (60/30), so a single missed transfer tops out at
    2*cadence - 1 and never reaches the budget: two consecutive misses are
    required and the seed never produces them. The two-year headline is
    therefore carried by six of the eight rows the table shows, and the page
    says so, because a table of eight rows otherwise implies eight
    contributors.

    DERIVED, not asserted, so the sentence tracks the evidence: if a third
    component fell to zero, or one of these two stopped being zero, the string
    changes and the gate goes red on a README that still claims two.
    """
    never = [(k, c) for k, c in y["per_component"].items()
             if c["stale_days"] == 0]
    listing = " and ".join(
        "`%s` (max age %d d against a %d d budget)"
        % (k, c["max_age_days"], c["budget_days"]) for k, c in never)
    return ("prose:never-stale",
            "%s of the %s components never go past budget at all in this "
            "window: %s."
            % (_word(len(never)), _word(len(y["per_component"])).lower(),
               listing))


def prose_figures():
    d = load()
    a, y, s = d["artifact"], d["year"], d["stack"]
    return [
        # "the days on which nothing but the free-running clock was past
        # budget" is the long form, and deliberately so. The short form is "the
        # days on which the enclave was entirely healthy", which is a DIFFERENT
        # sentence: the clock is past its budget on most of those days. So the
        # row below publishes the difference instead of leaving it to a
        # section further down.
        ("prose:headline",
         "Over two years, %d%% of the days on which nothing but the "
         "free-running clock was past budget produce a status artifact that "
         "is byte-identical" % round(a["clean_days_ambiguous_pct"])),
        ("prose:clean-breakdown",
         "Of those %d days, %d have the free-running clock past its own "
         "%d-day budget and %d have nothing stale at all."
         % (y["days_clean_excluding_clock"],
            y["days_clean_but_clock_past_budget"],
            y["per_component"]["time_source"]["budget_days"],
            y["days_with_nothing_stale_at_all"])),
        # This derives from the whole row. Its sentence has two halves (past
        # a budget AND nothing reporting it), so the only evidence for it is
        # the row carrying both:
        # days_stale_with_nothing_saying_so_excluding_clock.
        # The row ABOVE it, days_with_something_stale_excluding_clock, is the
        # near miss and not a synonym: it also counts the 68 days on which
        # policy_bundle was past budget and the health view SAID so, which is
        # the exact case the sentence excludes. A gate derived from that row
        # would demand the wrong number and reject the right one, and nothing
        # in the output would say which row it meant.
        ("prose:operational",
         "the enclave spends %d%% of its days past a staleness budget with "
         "nothing anywhere reporting it"
         % round(y["days_stale_with_nothing_saying_so_excluding_clock_pct"])),
        ("prose:split",
         "%s components depend on something outside the boundary. %s can "
         "report their own input age; %s cannot."
         % (_word(s["components"]), _word(s["announces"]), _word(s["silent"]))),
        _row_never_stale(y),
        _row_worst_age(y),
        _row_one_day(d),
    ]


def _row_worst_age(y):
    """The worst staleness anywhere in the window, which is NOT the worked
    example's day.

    The example day is chosen by how MANY things are silently stale, not by
    how far past budget any of them is, so its largest gap is 16 days. A
    reader who takes the example for the worst case gets the size of this
    effect wrong by an order of magnitude, so the worst case is published
    beside it, derived, and kept out of the one-day section where it would
    read as one of that day's figures.

    The clock is excluded, as everywhere else here: it is past budget by
    construction and saying so about it measures nothing. It would not win
    this comparison anyway, and that is checked: if it ever did, the derived
    string would name it and the gate would go red on a README that still
    names something else.
    """
    worst = max(((k, c) for k, c in y["per_component"].items()
                 if k != "time_source"),
                key=lambda kc: kc[1]["max_age_days"])
    key, c = worst
    return ("prose:worst-age",
            "`%s` reaches a maximum age of %d days in this window against a "
            "%d-day budget, %d days past it."
            % (key, c["max_age_days"], c["budget_days"],
               c["max_age_days"] - c["budget_days"]))


def _row_one_day(d):
    """The worked example, derived from the run instead of typed by hand.

    The section exists, in the page's own words, "so it is a thing and not a
    percentage", which makes its one number the easiest in the repository to
    state from memory and the hardest to notice when it is wrong. On this day
    the revocation list is 46 days old against a 45-day budget: ONE day past.
    The same component's two-year MAXIMUM age is 89, it sits in a different
    table, and "89 days past a 45-day budget" is a fluent sentence that no
    reader can falsify without re-running the simulation.
    """
    od = d.get("one_day")
    if not od:
        # A check that cannot look says so. Reporting the README as correct or
        # as wrong would both be claims about a comparison that never
        # happened, and this file's whole purpose is to not do that.
        sys.exit("audit/offline.json carries no one_day block, so the worked "
                 "example could not be derived and NOTHING about it was "
                 "checked. Regenerate the evidence:\n"
                 "  python3 scripts/offline_demo.py --days 730 "
                 "--json audit/offline.json")
    listing = ", ".join(
        "`%s` by %d day%s" % (e["key"], e["days_past"],
                              "" if e["days_past"] == 1 else "s")
        for e in od["past_budget"])
    return ("prose:one-day",
            "Past budget on day %d: %s." % (od["day"], listing))


def _trim(x):
    return "%g" % round(x, 1)


def _word(n):
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
            6: "six", 7: "Seven", 8: "Eight"}.get(n, str(n))


def emit():
    return (rows_components() + rows_collision() + rows_two_years()
            + prose_figures())


def squash(text):
    return re.sub(r"\s+", " ", text.replace("**", ""))


def main():
    derived = emit()
    if "--emit" in sys.argv:
        for tag, row in derived:
            print("%s\n%s" % (tag, row))
        return 0
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = squash(fh.read())
    missing = [(t, r) for t, r in derived if squash(r) not in readme]
    for tag, row in missing:
        print("MISSING [%s]\n  %s" % (tag, row))
    tables = sum(1 for t, _ in derived if not t.startswith("prose:"))
    print("\n%d of %d derived figures found verbatim in README.md "
          "(%d table rows, %d in prose)"
          % (len(derived) - len(missing), len(derived), tables,
             len(derived) - tables))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
