"""What the operator sees, what the assessor is given, and what is true.

THE GAP BETWEEN THESE THREE IS THE REPOSITORY. An enclave produces a health
view assembled from what its components report about themselves. A component
that does not track its own input age contributes a green light that is
indistinguishable from a component refreshed an hour ago, so the health view is
not a lossy summary of the truth -- it is a DIFFERENT OBJECT, and no amount of
reading it more carefully recovers what it never contained.

THREE VIEWS, DELIBERATELY SEPARATE OBJECTS:

  truth_view    every component's real input age. Nothing inside the enclave
                can produce this; the simulation knows it because it built it.
  health_view   what the stack reports. Ages appear ONLY for components that
                track them. Everything else says "ok".
  assessor_view what an accreditation review is handed: the health view plus
                the package's stated budgets, which is what makes it look
                complete.

A reader of the health view cannot distinguish a fresh CVE feed from one 95
days old, because the scanner reports CLEAN either way. That is not a bug in
the scanner. A scanner whose feed is stale has genuinely found no vulnerability
it knows about.
"""

from __future__ import annotations

from .components import BY_KEY, COMPONENTS


def truth_view(day) -> dict:
    """Every real age. Only the simulation can produce this."""
    return {"day": day.day,
            "ages": dict(day.age_days),
            "stale": list(day.stale),
            "silent_stale": list(day.silent_stale)}


def health_view(day) -> dict:
    """What the stack itself reports. The only thing an operator has."""
    out = {"day": day.day, "overall": "ok", "components": {}}
    for comp in COMPONENTS:
        age = day.age_days[comp.key]
        if comp.health_reports_age:
            stale = age > comp.budget_days
            out["components"][comp.key] = {
                "status": "degraded" if stale else "ok",
                "input_age_days": age,
                "detail": (f"bundle is {age} days old, budget "
                           f"{comp.budget_days}") if stale else "current",
            }
            if stale:
                out["overall"] = "degraded"
        else:
            # THE WHOLE FINDING, IN THREE LINES. No age, no staleness, no way
            # to tell. The component is working: it is serving what it has.
            out["components"][comp.key] = {"status": "ok",
                                           "detail": "serving normally"}
    return out


def assessor_view(day) -> dict:
    """The health view plus the package's promises. What a review receives.

    An assessor reads a green health view NEXT TO a table of stated budgets
    and concludes the budgets are being met. Nothing in the pairing is a lie
    and the conclusion does not follow: the budgets describe an intent and the
    health view describes six components that cannot report on it.

    THIS VIEW DELIBERATELY DOES NOT SAY WHICH COMPONENTS CAN EVIDENCE THEIR
    OWN FRESHNESS, because a real package does not say so. Including that
    list makes the view an ANSWER KEY and voids any measurement taken against
    it: both models read it, apply the only rule it supports -- "six of eight
    cannot be evidenced, so nothing can be determined" -- and return
    cannot_determine on every clean day as well as every silent one. That is
    correct reasoning from a prompt that should never contain the field. See
    recommended_view() for where it belongs.
    """
    health = health_view(day)
    return {
        "day": day.day,
        "overall": health["overall"],
        "stated_budgets": {c.key: c.budget_days for c in COMPONENTS},
        "reported": health["components"],
    }


def recommended_view(day) -> dict:
    """What this repository argues a package SHOULD carry.

    The assessor view plus the one field that makes it honest: which
    components can evidence their own input freshness, and therefore which
    green lights are unfalsifiable. It is the deliverable, and it is exactly
    why it must never appear in the evidence a model is graded on.
    """
    view = assessor_view(day)
    view["components_that_can_evidence_their_own_freshness"] = [
        c.key for c in COMPONENTS if c.health_reports_age]
    view["unfalsifiable"] = unfalsifiable(day)
    return view


def unfalsifiable(day) -> list:
    """Components whose green light cannot be wrong, because it says nothing.

    This is the list an auditor should be asking for and is the one no health
    endpoint emits.
    """
    return [c.key for c in COMPONENTS if not c.health_reports_age]
