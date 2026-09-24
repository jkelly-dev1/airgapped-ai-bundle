"""What must be true of the simulation before anything is measured against it.

These exist because the paid run is graded against this model. A model with a
defect does not produce a wrong paid result, it produces a meaningless one, and
the money is spent either way. Every test here is about the SIMULATION being
what it claims, not about any component being well designed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from enclave import timeline
from enclave.components import (BY_KEY, COMPONENTS, DEGRADE_LOUD,
                                FAIL_OPEN_QUIET, counts)
from enclave.health import (assessor_view, health_view, recommended_view,
                            truth_view, unfalsifiable)
from enclave.timeline import simulate, summarize

YEAR = 365
LONG = 365 * 5


def test_the_simulation_is_deterministic():
    """Same seed, same year. Two runs that disagree are not comparable and
    every number in the README compares runs."""
    a = summarize(simulate(YEAR, seed=1))
    b = summarize(simulate(YEAR, seed=1))
    assert a == b
    assert summarize(simulate(YEAR, seed=2)) != a


def test_the_measurement_is_the_same_in_any_process():
    """Same input, same JSON, whatever the hash seed.

    `measure` picks the example view by sorting a set of signatures, and
    several of them tie on the day count. A tie left to set iteration order is
    decided by the hash seed, which differs from one process to the next, so
    two calls INSIDE ONE PROCESS agree even when the function is wrong. Only a
    subprocess with a different seed can see it, and audit/offline.json is
    regenerated from this function and diffed against what ships.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = ("import json, sys; sys.path.insert(0, sys.argv[1]); "
           "from enclave.indistinguishable import measure; "
           "print(json.dumps(measure(240), sort_keys=True))")
    out = []
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", src, root],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        out.append(r.stdout)
    assert out[0] == out[1] == out[2]


def test_every_component_can_actually_go_stale():
    """A component that never exceeds its budget contributes nothing.

    Its cadence/budget pair is then a no-op, its row is a column of zeros, and
    the headline is carried by the others while appearing to be about all
    eight. This is the same defect class as a rule that is never violated:
    it does not fail, it just quietly stops being part of the measurement.

    Checked over five years rather than one, because "rare" and "impossible"
    are different and only the second is a defect.
    """
    tl = simulate(LONG)
    never = [c.key for c in COMPONENTS
             if not any(c.key in d.stale for d in tl)]
    assert not never, (
        f"these components cannot go stale in {LONG} days, so their budgets "
        f"are untested and their rows are decoration: {never}")


def test_transfers_are_actually_missed():
    """If every scheduled transfer landed, nothing would ever be stale and the
    whole repository would be measuring a miss rate of zero."""
    tl = simulate(YEAR)
    assert any(d.stale for d in tl)
    ages = [d.age_days["rag_corpus"] for d in tl]
    cadence = timeline.CADENCE_DAYS["a corpus transfer through the diode"]
    assert max(ages) > cadence, (
        "no corpus transfer was ever missed; the miss rates are not firing")


def test_the_health_view_never_reveals_a_silent_component():
    """The core invariant. A component that does not track its input age must
    contribute a green light on every day, including days it is months past
    budget. If this ever fails, the health view has become able to see
    something it cannot see, and the gap this repository measures is gone."""
    for day in simulate(YEAR):
        view = health_view(day)
        for key in day.silent_stale:
            entry = view["components"][key]
            assert entry["status"] == "ok", (
                f"day {day.day}: {key} is past budget and the health view "
                f"reported {entry['status']}")
            assert "input_age_days" not in entry


def test_the_health_view_does_reveal_an_announcing_component():
    """The other half, without which the finding would be that health views
    are useless rather than that they are incomplete."""
    seen = False
    for day in simulate(YEAR):
        view = health_view(day)
        for key in day.announced:
            assert view["components"][key]["status"] == "degraded"
            assert view["overall"] == "degraded"
            seen = True
    assert seen, "no announcing component ever went stale in a year"


def test_the_three_counts_are_nested():
    """stale-with-nothing-saying-so is a subset of silently-stale, which is a
    subset of stale. A crossover would mean the three are counting different
    populations and the headline is not a fraction of the row above it."""
    s = summarize(simulate(YEAR))
    assert (s["days_stale_with_nothing_saying_so"]
            <= s["days_with_silent_staleness"]
            <= s["days_with_something_stale"] <= s["days"])


def test_making_everything_announce_drives_the_silence_to_zero():
    """MUTATION CHECK. If the silent-days metric cannot be driven to zero by
    changing only the behaviors, it is not measuring the behaviors."""
    original = timeline.COMPONENTS
    loud = tuple(
        type(c)(c.key, c.what, c.depends_on, c.budget_days, DEGRADE_LOUD,
                True, c.note)
        for c in original)
    timeline.COMPONENTS = loud
    try:
        s = summarize(simulate(YEAR))
        assert s["days_with_silent_staleness"] == 0
        assert s["days_stale_with_nothing_saying_so"] == 0
        assert s["days_with_something_stale"] > 0, (
            "nothing went stale at all, so the mutation proves nothing")
    finally:
        timeline.COMPONENTS = original


def test_making_everything_silent_makes_every_stale_day_silent():
    """The mutation in the other direction, which catches a metric that is
    accidentally counting something else."""
    original = timeline.COMPONENTS
    quiet = tuple(
        type(c)(c.key, c.what, c.depends_on, c.budget_days, FAIL_OPEN_QUIET,
                False, c.note)
        for c in original)
    timeline.COMPONENTS = quiet
    try:
        s = summarize(simulate(YEAR))
        assert (s["days_stale_with_nothing_saying_so"]
                == s["days_with_something_stale"] > 0)
    finally:
        timeline.COMPONENTS = original


def test_the_clock_term_cannot_change_a_verdict():
    """Pins a claim that does not survive measurement. It sounds right that
    the clock poisons every other staleness check, since they are all measured
    against it. Measured, the drift is seconds against budgets in days. This
    asserts that: setting the drift to zero must change no day's verdict. If
    someone later raises the constant to something that does matter, this
    fails and the claim has to be argued rather than quietly assumed."""
    original = timeline.CLOCK_DRIFT_SECONDS_PER_DAY
    with_drift = [d.stale for d in simulate(YEAR)]
    timeline.CLOCK_DRIFT_SECONDS_PER_DAY = 0.0
    try:
        without = [d.stale for d in simulate(YEAR)]
    finally:
        timeline.CLOCK_DRIFT_SECONDS_PER_DAY = original
    assert with_drift == without
    # Bound tied to what matters, not an invented constant. Asserting the
    # drift is under some small made-up figure, 0.01 days, say, breaks the
    # moment the clock model becomes realistic, and it breaks on the THRESHOLD
    # rather than on the claim. Ages and budgets are whole days, so a drift
    # under one full day cannot move a comparison between them. That is the
    # actual reason the term is immaterial, so that is what is asserted.
    assert max(d.clock_error_days for d in simulate(YEAR)) < 1.0


def test_the_truth_and_the_health_view_disagree():
    """The premise. If these agreed, an operator could see everything and
    there would be nothing here to measure."""
    disagreements = 0
    for day in simulate(YEAR):
        truth = truth_view(day)
        view = health_view(day)
        if truth["stale"] and view["overall"] == "ok":
            disagreements += 1
    assert disagreements > 0


def test_the_assessor_view_does_not_contain_the_answer_key():
    """Pins the defect that voided a paid run. The view handed to a model must
    be what a real accreditation package contains. It must NOT say which
    components can evidence their own freshness, that is the finding, and a
    prompt containing it supports exactly one conclusion regardless of the
    day, which is what both models returned."""
    day = simulate(30)[-1]
    view = assessor_view(day)
    assert "components_that_can_evidence_their_own_freshness" not in view
    assert "unfalsifiable" not in view
    # The health output must not leak it either: a component that cannot report
    # its age must not be distinguishable by an extra key.
    silent_entries = [v for k, v in view["reported"].items()
                      if k in unfalsifiable(day)]
    assert all(set(e) == {"status", "detail"} for e in silent_entries)


def test_the_recommended_view_names_what_it_cannot_evidence():
    """The one honest field, in the object that is the deliverable rather than
    the object that is the evidence."""
    day = simulate(30)[-1]
    view = recommended_view(day)
    evidenced = set(view["components_that_can_evidence_their_own_freshness"])
    assert evidenced == {c.key for c in COMPONENTS if c.health_reports_age}
    assert set(unfalsifiable(day)) == {c.key for c in COMPONENTS
                                       if not c.health_reports_age}
    assert evidenced & set(unfalsifiable(day)) == set()


def test_the_stack_is_mostly_unfalsifiable_and_that_is_stated():
    c = counts()
    assert c["components"] == len(COMPONENTS)
    assert c["silent"] + c["announces"] == c["components"]
    assert c["health_reports_age"] == c["announces"]


def test_the_shipped_evidence_regenerates_byte_for_byte(tmp_path):
    """audit/offline.json must still be what this code produces.

    Every published figure is checked against audit/offline.json by
    scripts/check_readme_numbers.py, so that file is the evidence the whole
    page rests on, and a gate that compares prose to a committed artifact says
    nothing about whether the artifact still matches the code. Without this test a changed constant moves every real number
    while every other gate stays green: setting
    MISS_RATE["a CVE feed transfer"] from 0.22 to 0.50 leaves the suite
    passing, the demo exiting 0 and the checker reporting every figure
    present, while the two-year result moves from 53.7%/44.4% to 66.2%/56.8%.
    The README's claim is that the file "can be regenerated and diffed"; this
    is what does the diffing.

    Byte-for-byte, not value-by-value, because the claim being made about this
    file is that it regenerates, and a comparison of parsed values would
    pass on a file whose key order or float formatting had drifted, which is
    exactly the kind of difference that makes a reviewer distrust a diff.

    It runs the real script in a subprocess instead of calling summarize()
    here, because what ships is the script's output and an in-process
    reimplementation would pin this test to a copy of the code instead of to
    the code.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shipped = os.path.join(root, "audit", "offline.json")
    # Named, not left to FileNotFoundError. This file is tracked and shipped,
    # and its absence means the figures rest on nothing, which is a failure
    # and not a reason to skip; a reader needs to be told which happened.
    assert os.path.exists(shipped), (
        "audit/offline.json is missing from the tree at %s, so the published "
        "figures rest on no evidence at all" % root)
    fresh = tmp_path / "offline.json"
    r = subprocess.run(
        [sys.executable, os.path.join(root, "scripts", "offline_demo.py"),
         "--days", "730", "--json", str(fresh)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # The regeneration must have happened. Without this, a script that stopped
    # writing the file would leave the comparison below reading a stale path
    # or an empty one, and "the shipped evidence is correct" is the one
    # conclusion this test must never reach without looking.
    assert fresh.exists() and fresh.stat().st_size > 0, "nothing was written"
    with open(shipped, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert fresh.read_text(encoding="utf-8") == on_disk, (
        "audit/offline.json is not what scripts/offline_demo.py now produces. "
        "Regenerate it: python scripts/offline_demo.py --days 730 "
        "--json audit/offline.json")


def test_the_worked_example_is_carried_in_the_evidence(tmp_path):
    """The one-day section must leave the same trail every other figure does.

    The worked example's figures are the easiest in the repository to state
    from memory: the day's revocation gap is ONE day past budget, the same
    component's two-year maximum age is 89, and a sentence naming either is
    equally fluent. So the day's own arithmetic is emitted into
    audit/offline.json and re-derived by scripts/check_readme_numbers.py, and
    this asserts the block is present and internally consistent; a checker
    reading a block that is not there would be the same defect one level
    up.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shipped = os.path.join(root, "audit", "offline.json")
    assert os.path.exists(shipped), (
        "audit/offline.json is missing from the tree at %s, so the worked "
        "example rests on no evidence at all" % root)
    with open(shipped, encoding="utf-8") as fh:
        one_day = json.load(fh)["one_day"]
    assert one_day["past_budget"], "no component past budget in the example"
    day = simulate(730)[one_day["day"] - 1]
    assert day.day == one_day["day"]
    for entry in one_day["past_budget"]:
        assert entry["key"] in day.stale
        assert entry["age_days"] == day.age_days[entry["key"]]
        assert entry["days_past"] == (entry["age_days"]
                                      - BY_KEY[entry["key"]].budget_days)
        # A component is only PAST a budget by a positive number of days. A
        # zero here would print "by 0 days" in the README as a finding.
        assert entry["days_past"] > 0
    assert {e["key"] for e in one_day["past_budget"]} == set(day.stale)
