"""The parts of an enclave AI stack, and what each does when the wire is cut.

WHAT THIS MODELS AND WHAT IT DOES NOT. This is a model of a DEPLOYMENT PATTERN,
not a measurement of any vendor's software. Every component below corresponds
to something a real enclave stack contains -- a served model, a license check,
a policy bundle, a vulnerability feed, a retrieval corpus, a clock -- and each
carries a staleness budget of the kind an accreditation package actually
states. The numbers are stated constants, they are cited to the practice they
come from where one exists, and NONE of them is a claim about a product.

THE THING BEING MEASURED IS SILENCE. Air-gapping is usually discussed as
"does it still work?", and the answer is almost always yes -- that is what
caching is for. The question that decides whether an enclave is trustworthy is
narrower and nastier:

    WHEN A COMPONENT IS OPERATING ON STATE THAT HAS EXPIRED, DOES ANYTHING
    SAY SO?

A component that refuses to serve is safe and obvious. A component that serves
and announces its staleness is safe and inconvenient. A component that serves,
believes itself healthy, and reports green while its inputs rotted is the one
that produces an accreditation nobody can defend, and it is the only one worth
building a repository around.

THE THREE BEHAVIORS, AND THE ONLY ONE THAT IS INTERESTING:

  FAIL_CLOSED     stops serving when it cannot refresh. Loud. Safe.
  DEGRADE_LOUD    keeps serving and reports the staleness in its health output.
  FAIL_OPEN_QUIET keeps serving, reports healthy, and nothing anywhere
                  distinguishes it from a component refreshed this morning.

The last is not a strawman. It is the DEFAULT for most caches, because a cache
that shouted every time it served a cached value would be unusable, and the
same property that makes caching work makes staleness invisible.
"""

from __future__ import annotations

from dataclasses import dataclass

FAIL_CLOSED = "fail_closed"
DEGRADE_LOUD = "degrade_loud"
FAIL_OPEN_QUIET = "fail_open_quiet"

BEHAVIORS = (FAIL_CLOSED, DEGRADE_LOUD, FAIL_OPEN_QUIET)


@dataclass(frozen=True)
class Component:
    """One thing in the enclave that depends on something outside it.

    `budget_days` is the staleness the accreditation package allows -- the
    number an assessor will hold you to. `behavior` is what the component
    actually does once it is past that, which is a property of how it was
    built and is usually not the same thing as what the package assumes.
    """

    key: str
    what: str
    # What it needs from outside the boundary, and how often the transfer
    # process actually delivers it.
    depends_on: str
    budget_days: int
    behavior: str
    # Whether the component's own health endpoint distinguishes "refreshed"
    # from "serving from cache". This is the field that decides whether an
    # operator could have known.
    health_reports_age: bool
    note: str = ""

    def is_silent(self) -> bool:
        return self.behavior == FAIL_OPEN_QUIET


# THE STACK. Eight components, each real in the sense that an enclave AI
# deployment has one, with the budget an accreditation package typically
# states and the behavior the component typically has.
#
# The budgets are the conventional ones named in the operator's library notes:
# OS patches 30 days, container images 90 days. The rest are set to the same
# order of magnitude and are stated here rather than buried, because every
# result in this repository scales with them.
COMPONENTS = (
    Component(
        "model_weights", "the served model, pinned by digest",
        depends_on="an approved model transfer", budget_days=180,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="A pinned digest keeps serving forever. That is the point of "
             "pinning it, and it is also why a model withdrawn upstream for a "
             "safety defect goes on answering questions inside the enclave "
             "with nothing to indicate it."),
    Component(
        "model_revocation", "the revocation list for approved weights",
        depends_on="a revocation feed transfer", budget_days=45,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="THE CONTROL THAT MATTERS MOST AND FAILS WORST. A revocation "
             "check that cannot reach its list has two choices, and the "
             "usable one is to allow. An enclave that fails open on "
             "revocation has a control in its package and not in its "
             "runtime."),
    Component(
        "policy_bundle", "the egress and tool-use policy",
        depends_on="a policy transfer", budget_days=21,
        behavior=DEGRADE_LOUD, health_reports_age=True,
        note="Policy engines tend to carry an explicit bundle age and refuse "
             "or warn on it, because the failure was expensive enough often "
             "enough that the behavior got built."),
    Component(
        "cve_feed", "the vulnerability feed the scanner reads",
        depends_on="a CVE feed transfer", budget_days=45,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="A scanner with a stale feed reports CLEAN, not UNKNOWN. It is "
             "the same green as a scanner that just checked, and it is the "
             "single most reassuring wrong signal in the stack."),
    Component(
        "container_images", "the base images under the serving stack",
        depends_on="an image mirror transfer", budget_days=60,
        behavior=DEGRADE_LOUD, health_reports_age=True,
        note="Image age is visible because the tag and the build date are "
             "right there. Being visible is not the same as being looked at, "
             "which is a different problem this repository does not measure."),
    Component(
        "rag_corpus", "the retrieval corpus",
        depends_on="a corpus transfer through the diode", budget_days=14,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="The assistant answers from what it has. A corpus three months "
             "behind produces confident, fluent, current-sounding answers "
             "about a policy that changed in between."),
    Component(
        "eval_baseline", "the eval set the model is checked against",
        depends_on="an eval transfer", budget_days=120,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="Evals are run against the baseline that is present. A stale "
             "baseline keeps passing, which is indistinguishable from the "
             "model still being good."),
    Component(
        "time_source", "the clock the expiry checks read",
        depends_on="a physical clock discipline visit", budget_days=7,
        behavior=FAIL_OPEN_QUIET, health_reports_age=False,
        note="A TRUE AIR GAP HAS NO NTP. The clock is disciplined when someone "
             "walks in with a reference and free-runs the rest of the time, so "
             "it is past a 7-day budget on most days by construction. "
             "Every budget above is measured against this clock, so a drifting "
             "clock makes every other staleness check answer from a wrong now. "
             "MEASURED, THE EFFECT IS IMMATERIAL: seconds per day against "
             "budgets expressed in days. It sounds right that the clock "
             "poisons the other checks, and the arithmetic does not support "
             "it, so the claim is not made here. Where an enclave clock does "
             "bite is "
             "certificate validity, which fails loudly."),
)

BY_KEY = {c.key: c for c in COMPONENTS}


def counts() -> dict:
    """How much of the stack can tell you it has gone stale."""
    silent = [c for c in COMPONENTS if c.is_silent()]
    return {
        "components": len(COMPONENTS),
        "silent": len(silent),
        "announces": len(COMPONENTS) - len(silent),
        "silent_keys": [c.key for c in silent],
        "health_reports_age": sum(1 for c in COMPONENTS if c.health_reports_age),
    }
