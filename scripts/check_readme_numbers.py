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
        ("collision:clean-rate",
         "-> %d of %d clean days (%s%%) produce a view that also occurs on a "
         "day something was months past budget"
         % (a["clean_days_ambiguous"], a["clean_days"],
            _trim(a["clean_days_ambiguous_pct"]))),
        ("collision:silent-rate",
         "-> %d of %d silent days (%s%%) produce a view that also occurs on a "
         "day when nothing was wrong at all"
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


def prose_figures():
    d = load()
    a, y, s = d["artifact"], d["year"], d["stack"]
    excl_stale = 100.0 * y["days_with_something_stale_excluding_clock"] / y["days"]
    return [
        ("prose:headline",
         "Over two years, %d%% of the days on which the enclave was entirely "
         "healthy produce a status artifact that is byte-identical"
         % round(a["clean_days_ambiguous_pct"])),
        # The operational half quotes the column excluding the clock, which is
        # the one the page tells a reader to act on. Deriving it from the
        # including-clock figure would put 86% in a sentence the page wrote to
        # avoid exactly that.
        ("prose:operational",
         "the enclave spends %d%% of its days past a staleness budget with "
         "nothing anywhere reporting it" % round(excl_stale)),
        ("prose:split",
         "%s components depend on something outside the boundary. %s can "
         "report their own input age; %s cannot."
         % (_word(s["components"]), _word(s["announces"]), _word(s["silent"]))),
    ]


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
