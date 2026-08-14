"""How often a healthy enclave and a rotten one produce the same artifact.

The proof this repository leads with, and it needs no model. Everything else
here measures behavior. How often something is stale, whether anything says
so, what a reviewer concludes. This measures the ARTIFACT, by construction:
take every day of a two-year run, render the view an accreditation review
actually receives, and count how many distinct views occur in BOTH the clean
stratum and the silent one.

A view that occurs in both is a view that cannot distinguish an enclave inside
its budgets from one months past them. Not "is hard to distinguish". The bytes
are identical, so no reader, no checklist, no reviewer and no model can tell
them apart, because there is nothing there to tell apart.

The day number is excluded from the comparison, deliberately. Two views that
differ only in the date are the same evidence about different days; leaving the
date in would make every view unique and the count would be zero for a reason
that has nothing to do with what the artifact contains.
"""

from __future__ import annotations

import json

from .health import assessor_view
from .sampler import CLEAN, SILENT, stratum_of
from .timeline import simulate


def _signature(day) -> str:
    view = dict(assessor_view(day))
    view.pop("day")
    return json.dumps(view, sort_keys=True, default=str)


def measure(days: int = 730) -> dict:
    buckets = {CLEAN: {}, SILENT: {}}
    for day in simulate(days):
        stratum = stratum_of(day)
        if stratum in buckets:
            buckets[stratum].setdefault(_signature(day), []).append(day.day)

    shared = set(buckets[CLEAN]) & set(buckets[SILENT])
    clean_days = sum(len(v) for v in buckets[CLEAN].values())
    silent_days = sum(len(v) for v in buckets[SILENT].values())
    clean_ambiguous = sum(len(buckets[CLEAN][k]) for k in shared)
    silent_ambiguous = sum(len(buckets[SILENT][k]) for k in shared)

    return {
        "days": days,
        "distinct_views_clean": len(buckets[CLEAN]),
        "distinct_views_silent": len(buckets[SILENT]),
        "views_occurring_in_both": len(shared),
        "clean_days": clean_days,
        "silent_days": silent_days,
        "clean_days_ambiguous": clean_ambiguous,
        "silent_days_ambiguous": silent_ambiguous,
        "clean_days_ambiguous_pct": round(clean_ambiguous / clean_days * 100, 1)
        if clean_days else 0.0,
        "silent_days_ambiguous_pct":
            round(silent_ambiguous / silent_days * 100, 1) if silent_days else 0.0,
        # An example, so a reader can look at the thing rather than the count.
        "example": _example(buckets, shared),
    }


def _example(buckets, shared) -> dict:
    if not shared:
        return {}
    # The signature is the second sort key because several views tie on the day
    # count. A tie broken by set iteration order is decided by the hash seed,
    # which differs from one process to the next, so the same input would pick
    # a different example every run and audit/offline.json could not be
    # regenerated and diffed.
    key = sorted(shared, key=lambda k: (-(len(buckets[CLEAN][k])
                                          + len(buckets[SILENT][k])), k))[0]
    return {
        "clean_days_with_this_view": buckets[CLEAN][key][:5],
        "silent_days_with_this_view": buckets[SILENT][key][:5],
        "the_view": json.loads(key),
    }
