"""Re-derive README.md's published figures from the evidence in audit/.

A README is prose and drifts; audit/*.json is evidence and does not. This
script rebuilds each figure from the JSON and asserts the exact string is
present in the README, so a re-run that shifts a figure fails loudly instead of
leaving a wrong figure in the document.

Three files feed it: audit/offline.json for the simulation, audit/real_run.json
for the paid run, and the voided run beside it for the re-keying sentences.
The paid block is rebuilt by calling real_run.report() over the stored
records, so the README and SAMPLE_RUN.md are held to what the report code
prints and not to a copy of it. SAMPLE_RUN.md's offline block is rebuilt by
running scripts/offline_demo.py, the command it shows, in a scratch
directory. Two figures come from the repository's own code rather than from
audit/: the test count, counted from the test functions in tests/, and the
five-year window, read from LONG in tests/test_enclave.py.

Not derived here: counts written as words inside explanatory sentences, and
the value 0.50 in the claims table's mutation note, which is the edit a reader
is invited to make and not a result. The constant it replaces, 0.22, is read
from enclave/timeline.py.

    python3 scripts/check_readme_numbers.py            check
    python3 scripts/check_readme_numbers.py --emit     print what it derives

Whitespace AND emphasis are normalized on both sides, so a reflowed paragraph
is not a false alarm that trains a reader to ignore the script.

Both columns of the two-year table are derived, including the one excluding the
clock, because the page's own instruction is to act on the right column and a
deriver that only checked the larger number would be doing what the page warns
against.

The count is printed whether OR NOT anything is missing, so a version of this
script that stopped deriving half of them shows it in the count.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)


def load(name="offline.json"):
    with open(os.path.join(ROOT, "audit", name), encoding="utf-8") as fh:
        return json.load(fh)


def report_block():
    """real_run.report() over the stored paid run, as printed."""
    import real_run                                     # noqa: PLC0415
    run = load("real_run.json")
    out = []
    real_run.report(run["records"], run["models"], echo=out.append)
    return "\n".join(out).strip("\n")


def _short(model):
    return model.replace("claude-", "")


def _assess_score(records, model):
    rows = [r for r in records if r.get("model") == model
            and r.get("condition") == "assess"]
    ok = sum(1 for r in rows if r.get("parsed")
             and r.get("verdict") == r.get("correct"))
    return ok, len(rows)


def _audit_score(records, model):
    tp = fp = fn = 0
    for r in records:
        if r.get("model") == model and r.get("condition") == "audit":
            named = set(r.get("named") or [])
            truth = set(r["truth_unverifiable"])
            tp += len(named & truth)
            fp += len(named - truth)
            fn += len(truth - named)
    rec = round(100 * tp / (tp + fn)) if tp + fn else 0
    prec = round(100 * tp / (tp + fp)) if tp + fp else 0
    return rec, prec


def rows_paid():
    """The paid run: its report block, its cost table, and the re-keying.

    The re-keying sentences read the VOIDED run, because that is the run the
    pre-registered key was applied to. Its records carry the key that was in
    force (`correct`), so how many answers that key marked wrong, and which
    stratum they fell in, come out of the file and not out of memory.
    """
    run, void = load("real_run.json"), load(
        "real_run_VOID_answer_key_in_prompt.json")
    recs, models = run["records"], run["models"]
    names = ", ".join(_short(m) for m in models)

    scores = [_assess_score(recs, m) for m in models]
    audits = [_audit_score(recs, m) for m in models]
    result = ("%d/%d both" % scores[0] if len(set(scores)) == 1 else
              ", ".join("%s %d/%d" % ((_short(m),) + s)
                        for m, s in zip(models, scores)))
    result += ("; audit %d/%d" % audits[0] if len(set(audits)) == 1 else
               "; audit " + ", ".join("%s %d/%d" % ((_short(m),) + a)
                                      for m, a in zip(models, audits)))

    wrong = [r for r in void["records"] if r.get("condition") == "assess"
             and r.get("verdict") != r.get("correct")]
    asked = sum(1 for r in void["records"] if r.get("condition") == "assess")
    strata = {r.get("stratum") for r in wrong}
    where = ("every one of them a %s day" % strata.pop() if len(strata) == 1
             else "across %d strata" % len(strata))

    key = lambda r: (r["model"], r["day"], r["condition"])
    ans = lambda r: (r.get("verdict"), tuple(sorted(r.get("named") or [])))
    vmap = {key(r): ans(r) for r in void["records"]}
    same = sum(1 for r in recs if vmap.get(key(r)) == ans(r))
    agree = ("agree on all %d calls" % len(recs) if same == len(recs)
             else "agree on %d of %d calls" % (same, len(recs)))
    return [
        ("paid:report", report_block()),
        ("paid:design", "across " + _design(run)[len("over "):]),
        ("paid:table",
         "| assess + audit | %s | %d | $%.2f | %s |"
         % (names, len(recs), run["actual_cost_usd"], result)),
        ("paid:void-table",
         "| (void) | %s | %d | $%.2f | answer key was in the prompt |"
         % (", ".join(_short(m) for m in void["models"]),
            len(void["records"]), void["actual_cost_usd"])),
        ("paid:rekey",
         "Under that key, %d of the %d ASSESS answers were marked wrong, %s."
         % (len(wrong), asked, where)),
        ("paid:agree",
         "the voided first run and the stored run %s" % agree),
    ]


def _design(run):
    days = {r["day"] for r in run["records"] if r.get("condition") == "assess"}
    per = run["per_stratum"]
    return ("over %d days balanced %d/%d/%d across clean, announced and silent"
            % (len(days), per, per, per))


def _void_wrong():
    """The ASSESS answers the pre-registered key marked wrong, and where."""
    void = load("real_run_VOID_answer_key_in_prompt.json")
    wrong = [r for r in void["records"] if r.get("condition") == "assess"
             and r.get("verdict") != r.get("correct")]
    asked = sum(1 for r in void["records"] if r.get("condition") == "assess")
    return void, wrong, asked


def offline_block():
    """What `offline_demo.py --json audit/offline.json` prints, run for real.

    It runs in a scratch directory, so the relative --json path lands there
    and the shipped audit/offline.json is never written by a check.
    """
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "offline_demo.py"),
             "--json", os.path.join("audit", "offline.json")],
            cwd=tmp, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("scripts/offline_demo.py exited %d with %d byte(s) of "
                 "output, so SAMPLE_RUN.md's offline block could not be "
                 "rebuilt and NOTHING about it was checked.\n%s"
                 % (r.returncode, len(r.stdout), r.stderr))
    return r.stdout.strip("\n")


def sample_run_rows():
    """SAMPLE_RUN.md: the paid block, the offline block, and their prose."""
    run = load("real_run.json")
    void, wrong, _ = _void_wrong()
    per_model = {m: sum(1 for r in wrong if r["model"] == m)
                 for m in void["models"]}
    strata = {r.get("stratum") for r in wrong}
    if len(set(per_model.values())) == 1 and len(strata) == 1:
        rekey = ("the %d %s days of each model, %d answers, were marked wrong"
                 % (per_model[void["models"][0]], strata.pop(), len(wrong)))
    else:
        rekey = "%d answers, were marked wrong" % len(wrong)
    return [
        ("sample:tests", "%d passed in" % test_count()),
        ("sample:offline", offline_block()),
        ("sample:report", report_block()),
        ("sample:cost",
         "The capture cost %d calls, two providers, $%.2f."
         % (len(run["records"]), run["actual_cost_usd"])),
        ("sample:design", _design(run)),
        ("sample:rekey", rekey),
        ("sample:both",
         "%d distinct views occur in both strata"
         % load()["artifact"]["views_occurring_in_both"]),
    ]


def test_count():
    """Test functions defined at the top level of tests/test_*.py."""
    tests = os.path.join(ROOT, "tests")
    n = 0
    for name in sorted(os.listdir(tests)):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(tests, name), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            n += sum(1 for node in tree.body
                     if isinstance(node, ast.FunctionDef)
                     and node.name.startswith("test_"))
    return n


def _long_window():
    """LONG in tests/test_enclave.py, the window the go-stale test runs."""
    with open(os.path.join(ROOT, "tests", "test_enclave.py"),
              encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and getattr(node.targets[0], "id", None) == "LONG"):
            return eval(compile(ast.Expression(node.value), "LONG", "eval"),
                        {"__builtins__": {}})
    sys.exit("tests/test_enclave.py defines no LONG, so the five-year claim "
             "could not be derived and NOTHING about it was checked.")


def rows_quoted():
    """Figures the page restates in prose, each anchored to its sentence."""
    from enclave.timeline import MISS_RATE                 # noqa: PLC0415
    d = load()
    a, y = d["artifact"], d["year"]
    gaps = [e["days_past"] for e in d["one_day"]["past_budget"]]
    least = min(gaps)
    carried = sum(1 for c in y["per_component"].values() if c["stale_days"])
    return [
        ("prose:span-intro",
         "enclave AI stack simulated over %s years" % _years(y["days"])),
        ("prose:span-proof",
         "Take every day of a %s-year run" % _years(y["days"])),
        ("prose:one-day-lead",
         "%s day%s past budget is not the dramatic case"
         % (_word(least), "" if least == 1 else "s")),
        ("prose:reproduce",
         "Reproduce with `python scripts/offline_demo.py --days %d`."
         % y["days"]),
        ("prose:clock-budget",
         "A free-running clock is past a %d-day budget on most days"
         % y["per_component"]["time_source"]["budget_days"]),
        ("prose:carried",
         "carried by %s of the %s rows in the table"
         % (_word(carried).lower(), _word(len(y["per_component"])).lower())),
        ("prose:long-window",
         "both components do go stale over a %s-year window"
         % _years(_long_window())),
        ("prose:long-claim",
         "(checked over %s years" % _years(_long_window())),
        ("prose:collision-quoted",
         "The %d%% collision" % round(a["clean_days_ambiguous_pct"])),
        ("prose:mutation-constant",
         '`MISS_RATE["a CVE feed transfer"]` %.2f -> 0.50'
         % MISS_RATE["a CVE feed transfer"]),
        ("prose:test-count", "# %d tests" % test_count()),
    ]


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
        # was 60+ days past budget. 64 of them share it only with days on
        # which nothing was more than 29 days past, and the weakest shares it
        # with a day ONE day past. What holds of every silent partner day is the
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
        # The same row quoted by name further down the page, rounded.
        ("years:quoted", "the %d%% figure" % round(excl_stale)),
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
    from enclave.components import BY_KEY                  # noqa: PLC0415
    from enclave.timeline import CADENCE_DAYS              # noqa: PLC0415
    never = [(k, c) for k, c in y["per_component"].items()
             if c["stale_days"] == 0]
    listing = " and ".join(
        "`%s` (max age %d d against a %d d budget)"
        % (k, c["max_age_days"], c["budget_days"]) for k, c in never)
    twice = all(c["budget_days"] == 2 * CADENCE_DAYS[BY_KEY[k].depends_on]
                for k, c in never)
    return ("prose:never-stale",
            "%s of the %s components never go past budget at all in this "
            "window: %s. %s"
            % (_word(len(never)), _word(len(y["per_component"])).lower(),
               listing,
               "Each has a budget of exactly twice its transfer cadence"
               if twice else "Their budgets are not all twice their cadence"))


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
         "Over %s years, %d%% of the days on which nothing but the "
         "free-running clock was past budget produce a status artifact that "
         "is byte-identical"
         % (_years(y["days"]), round(a["clean_days_ambiguous_pct"]))),
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
        _row_one_day_block(d),
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


def _row_one_day_block(d):
    """The worked example's code block, line by line from the evidence.

    The prose under the block was derived and the block itself was not, so a
    changed truth line or status line passed every gate. offline_demo.py now
    emits the truth list and each component's status and detail into the
    one_day block, and this rebuilds what that script prints from them.
    """
    od = d["one_day"]
    if "health_components" not in od or "truth_stale" not in od:
        sys.exit("audit/offline.json's one_day block carries no health "
                 "lines, so the worked example's code block could not be "
                 "derived and NOTHING about it was checked. Regenerate the "
                 "evidence:\n  python3 scripts/offline_demo.py --days 730 "
                 "--json audit/offline.json")
    lines = ["day %d" % od["day"],
             "truth: past budget -> %s" % ", ".join(od["truth_stale"]),
             "health output overall: %s" % od["health_overall"]]
    lines += ["%s %s %s" % (k, e["status"], e["detail"])
              for k, e in od["health_components"].items()]
    return ("prose:one-day-block", "\n".join(lines))


def _trim(x):
    return "%g" % round(x, 1)


def _years(days):
    """A window as the page words it: 730 days is "two" years."""
    return (_word(days // 365).lower() if days % 365 == 0
            else "%g" % round(days / 365, 1))


def _word(n):
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
            6: "six", 7: "Seven", 8: "Eight"}.get(n, str(n))


def emit():
    return (rows_components() + rows_collision() + rows_two_years()
            + prose_figures() + rows_quoted() + rows_paid())


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
          "(%d table rows and blocks, %d in prose)"
          % (len(derived) - len(missing), len(derived), tables,
             len(derived) - tables))
    with open(os.path.join(ROOT, "SAMPLE_RUN.md"), encoding="utf-8") as fh:
        sample = squash(fh.read())
    sample_rows = sample_run_rows()
    sample_missing = [(t, r) for t, r in sample_rows
                      if squash(r) not in sample]
    for tag, row in sample_missing:
        print("MISSING in SAMPLE_RUN.md [%s]\n  %s" % (tag, row))
    print("%d of %d derived blocks found verbatim in SAMPLE_RUN.md"
          % (len(sample_rows) - len(sample_missing), len(sample_rows)))
    return 1 if missing or sample_missing else 0


if __name__ == "__main__":
    sys.exit(main())
