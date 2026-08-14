"""A year inside the boundary: transfers arrive, or they do not, and time passes.

WHY A TIMELINE AND NOT A SNAPSHOT. "Is the enclave current?" is a question with
a different answer every day, and the interesting quantity is not whether it is
stale now but WHAT FRACTION OF ITS OPERATING LIFE IT SPENDS STALE WITHOUT
KNOWING. A snapshot cannot see that, and a snapshot is exactly what an
accreditation review takes.

THE TRANSFER PROCESS IS THE WHOLE SYSTEM. Nothing crosses the boundary by
itself. A human collects artifacts, a review approves them, a diode or a
sneakernet moves them, and someone installs them on the inside. Every step has
a failure rate, and the failure is almost always SILENT ON THE INSIDE: the
enclave does not know a transfer was due. It only knows what it has.

THE RATES BELOW ARE STATED CONSTANTS AND EVERY RESULT SCALES WITH THEM. They
are set to a cadence a real program would recognize -- a weekly corpus, a
monthly feed, a quarterly image refresh -- with a miss rate that reflects that
transfers compete with everything else the same people are doing. They are not
measurements of any program.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .components import BY_KEY, COMPONENTS

# Nominal cadence per dependency, in days, and the probability that a given
# scheduled transfer does not actually land. A missed transfer is not an
# outage: it is a week where the person who does it was on leave.
# CADENCE AND BUDGET ARE INDEPENDENT NUMBERS AND MUST NOT BE SET EQUAL. A
# refresh scheduled to land exactly on the expiry date makes a component pass
# unless a transfer is missed AND the arithmetic crosses, which is a knife
# edge no program would design and which quietly excludes the two
# longest-budget components from the result. The cadence is how often the
# process runs; the budget is what the accreditation package allows. Real
# programs leave headroom, so these do.
CADENCE_DAYS = {
    "an approved model transfer": 90,
    "a revocation feed transfer": 30,
    "a policy transfer": 14,
    "a CVE feed transfer": 30,
    "an image mirror transfer": 30,
    "a corpus transfer through the diode": 7,
    "an eval transfer": 45,
    # A TRUE AIR GAP HAS NO EXTERNAL TIME SOURCE, which the first two versions
    # of this file modeled as a daily transfer -- a network dependency inside
    # a boundary defined by not having one. A clock in an enclave is
    # disciplined when somebody physically visits with a reference, which is a
    # quarterly event, and free-runs in between.
    "a physical clock discipline visit": 90,
}

# Probability a scheduled transfer is missed. Higher for the ones that need a
# human decision (model, eval) than the ones that are automated once approved.
MISS_RATE = {
    "an approved model transfer": 0.35,
    "a revocation feed transfer": 0.25,
    "a policy transfer": 0.15,
    "a CVE feed transfer": 0.22,
    "an image mirror transfer": 0.30,
    "a corpus transfer through the diode": 0.18,
    "an eval transfer": 0.40,
    "a physical clock discipline visit": 0.25,
}

# CLOCK DRIFT, KEPT AND DEMOTED. It is tempting to call the clock "the one
# that poisons the others", on the reasoning that every staleness budget is
# measured against it. The arithmetic does not support the claim: a
# free-running enclave clock drifts on the order of seconds per day, so after a
# YEAR without discipline the error is minutes, and a budget expressed in days
# cannot be flipped by minutes. The term is kept because it is real and
# measured, and clock_error_days is reported so a reader can see it is
# immaterial rather than take my word for it.
#
# WHERE AN ENCLAVE CLOCK ACTUALLY HURTS is certificate and signature validity,
# which is checked at second granularity and fails LOUDLY. That is a different
# failure from the one this repository measures, and it is a safe one.
CLOCK_DRIFT_SECONDS_PER_DAY = 8.0


@dataclass
class Day:
    """One operating day, and the state of every component on it."""

    day: int
    age_days: dict = field(default_factory=dict)      # component key -> age
    stale: tuple = ()                                  # keys past budget
    silent_stale: tuple = ()                           # ... and saying nothing
    announced: tuple = ()                              # ... and saying so
    clock_error_days: float = 0.0


def simulate(days: int = 365, seed: int = 0) -> list:
    """Run the enclave for `days`, delivering transfers when they land."""
    rng = random.Random(f"enclave-{seed}")
    last_refresh = {c.key: 0 for c in COMPONENTS}
    out = []

    for day in range(1, days + 1):
        for comp in COMPONENTS:
            cadence = CADENCE_DAYS[comp.depends_on]
            if day % cadence != 0:
                continue
            if rng.random() < MISS_RATE[comp.depends_on]:
                continue                    # the transfer did not land
            last_refresh[comp.key] = day

        ages = {c.key: day - last_refresh[c.key] for c in COMPONENTS}

        # The enclave checks every budget against its own clock, so a drifting
        # clock shifts its idea of how old everything else is -- in the
        # flattering direction, since a slow clock makes everything look
        # younger. The term is computed and reported rather than assumed away.
        # It comes out at seconds against budgets in days: immaterial, which is
        # the measurement rather than the intuition. See the note on
        # CLOCK_DRIFT_SECONDS_PER_DAY.
        clock_age = ages["time_source"]
        clock_error_days = clock_age * CLOCK_DRIFT_SECONDS_PER_DAY / 86400.0

        stale, silent, announced = [], [], []
        for comp in COMPONENTS:
            believed_age = ages[comp.key] - clock_error_days
            if believed_age > comp.budget_days:
                stale.append(comp.key)
                (silent if comp.is_silent() else announced).append(comp.key)

        out.append(Day(day=day, age_days=ages, stale=tuple(stale),
                       silent_stale=tuple(silent), announced=tuple(announced),
                       clock_error_days=clock_error_days))
    return out


def summarize(timeline: list) -> dict:
    """The numbers this repository exists to report."""
    n = len(timeline)
    any_stale = sum(1 for d in timeline if d.stale)
    silent_only = sum(1 for d in timeline if d.silent_stale and not d.announced)
    any_silent = sum(1 for d in timeline if d.silent_stale)

    per_component = {}
    for comp in COMPONENTS:
        stale_days = sum(1 for d in timeline if comp.key in d.stale)
        per_component[comp.key] = {
            "stale_days": stale_days,
            "stale_pct": round(stale_days / n * 100, 1),
            "behavior": comp.behavior,
            "budget_days": comp.budget_days,
            "max_age_days": max(d.age_days[comp.key] for d in timeline),
            "announces": not comp.is_silent(),
        }

    # THE CLOCK IS ALMOST ALWAYS STALE AND ALMOST NEVER MATTERS, so the
    # headline is reported twice. Including it is true and misleading: a
    # free-running clock is past a 7-day budget on most days by construction,
    # and the test above proves that staleness cannot change any other
    # verdict. Excluding it is the number an operator should act on. Quoting
    # only the larger one would be this repository doing what it criticizes.
    harmless = {"time_source"}
    silent_only_material = sum(
        1 for d in timeline
        if set(d.silent_stale) - harmless and not d.announced)
    any_stale_material = sum(
        1 for d in timeline if set(d.stale) - harmless)

    return {
        "days": n,
        "days_with_something_stale": any_stale,
        "days_with_something_stale_pct": round(any_stale / n * 100, 1),
        "days_with_silent_staleness": any_silent,
        "days_with_silent_staleness_pct": round(any_silent / n * 100, 1),
        # THE HEADLINE. Days on which something was past its budget and NOTHING
        # anywhere in the stack was saying so -- no warning, no degraded
        # health, no banner. An operator looking at every dashboard they have
        # sees a working system.
        "days_stale_with_nothing_saying_so": silent_only,
        "days_stale_with_nothing_saying_so_pct": round(silent_only / n * 100, 1),
        "days_with_something_stale_excluding_clock": any_stale_material,
        "days_stale_with_nothing_saying_so_excluding_clock": silent_only_material,
        "days_stale_with_nothing_saying_so_excluding_clock_pct":
            round(silent_only_material / n * 100, 1),
        "per_component": per_component,
    }
