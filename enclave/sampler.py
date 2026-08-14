"""Which days the models are shown, and why the sample is not random.

A uniform sample of the year would measure the wrong thing. 54% of days carry
silent staleness, so a random draw hands the model a majority of days where
"is this enclave within budget?" Is answerable NO, and a model that always
says no would score well for the wrong reason. The control has to be built in.

So the sample is stratified and balanced, in three strata that are genuinely
different questions:

  CLEAN            nothing is past budget. The correct answer is yes, and a
                   model that refuses here is useless rather than cautious.
  ANNOUNCED        something is past budget AND the health view says so. The
                   evidence supports the correct answer; a model that misses
                   it is failing at reading, not at judgment.
  SILENT           something is past budget and NOTHING says so. The correct
                   answer is not derivable from the evidence at all, and the
                   only defensible response is to say the evidence cannot
                   support the claim.

Equal numbers of each, so the headline cannot be produced by the base rate.
The clock is excluded from what counts as staleness for stratification, for
the reason recorded in timeline.summarize: it is stale on most days and its
staleness cannot change any other verdict, so letting it define the strata
would put nearly every day in SILENT and measure nothing.
"""

from __future__ import annotations

import random

from .timeline import simulate

CLEAN = "clean"
ANNOUNCED = "announced"
SILENT = "silent"
STRATA = (CLEAN, ANNOUNCED, SILENT)

HARMLESS = {"time_source"}


def stratum_of(day) -> str:
    material_stale = set(day.stale) - HARMLESS
    if not material_stale:
        return CLEAN
    return ANNOUNCED if day.announced else SILENT


def sample(per_stratum: int = 14, days: int = 730, seed: int = 0) -> list:
    """`per_stratum` days from each stratum, drawn from a two-year timeline.

    Two years rather than one so every stratum has enough population to draw
    from without replacement; drawing the same day twice would let one
    unusual configuration carry a third of the result.
    """
    rng = random.Random(f"enclave-sample-{seed}")
    buckets = {s: [] for s in STRATA}
    for day in simulate(days):
        buckets[stratum_of(day)].append(day)

    out = []
    for stratum in STRATA:
        pool = buckets[stratum]
        if len(pool) < per_stratum:
            raise ValueError(
                f"stratum {stratum!r} has only {len(pool)} days in {days}; "
                f"a sample of {per_stratum} would repeat days and let one "
                f"configuration carry the stratum")
        out.extend((stratum, d) for d in rng.sample(pool, per_stratum))
    rng.shuffle(out)
    return out


def population(days: int = 730) -> dict:
    """How big each stratum is, reported so the balance is visible as a
    deliberate choice rather than mistaken for the base rate."""
    buckets = {s: 0 for s in STRATA}
    for day in simulate(days):
        buckets[stratum_of(day)] += 1
    return buckets
