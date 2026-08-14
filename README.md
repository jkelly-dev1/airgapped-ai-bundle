# airgapped-ai-bundle

**When the network is removed, which failures are silent?** An enclave AI stack
simulated over two years, and a measurement of the artifact an accreditation
review actually receives.

A personal learning project. Air-gapping is usually discussed as "does it still
work?", and the answer is almost always yes -- that is what caching is for. The
question that decides whether an enclave is trustworthy is narrower: when a
component is operating on state that has expired, does anything say so?

The measurement imports nothing outside the standard library.

The rule this repo follows: no claim without a test.

## The one-sentence result

Over two years, **62% of the days on which the enclave was entirely healthy
produce a status artifact that is byte-identical to one produced on a day when
something was months past its budget.** Not similar -- identical. No reader can
distinguish them because there is nothing there to distinguish.

And the operational half: the enclave spends **54% of its days** past a
staleness budget with nothing anywhere reporting it.

## Why the artifact cannot tell you

Eight components depend on something outside the boundary. **Two can report
their own input age; six cannot.**

| component | budget | reports its own age |
|---|---|---|
| `model_weights` | 180 d | no |
| `model_revocation` | 45 d | **no** |
| `policy_bundle` | 21 d | yes |
| `cve_feed` | 45 d | **no** |
| `container_images` | 60 d | yes |
| `rag_corpus` | 14 d | no |
| `eval_baseline` | 120 d | no |
| `time_source` | 7 d | no |

A component that does not track its input age contributes a green light that is
indistinguishable from one refreshed an hour ago. The health view is therefore
not a lossy summary of the truth -- it is a **different object**, and reading it
more carefully recovers nothing, because what is missing was never in it.

The two that matter most are both silent. A scanner with a stale CVE feed
reports **CLEAN, not UNKNOWN** -- the same green as one that checked this
morning. A revocation check that cannot reach its list has two options and the
usable one is to allow, so a revoked model goes on answering.

## The proof, which needs no model

Take every day of a two-year run, render the view an accreditation review
receives, and count how many distinct views occur in **both** the clean stratum
and the silently-stale one:

```
  distinct views seen on clean days     242
  distinct views seen on silent days    222
  views occurring in BOTH strata        134

  -> 210 of 338 clean days (62.1%) produce a view that also occurs
     on a day something was months past budget
  -> 186 of 324 silent days (57.4%) produce a view that also occurs
     on a day when nothing was wrong at all
```

This is a property of the artifact's **shape**, not of any particular failure
rate. Any cadences that produce both strata produce the collision.

## One day, so it is a thing and not a percentage

```
day 226
  truth: past budget -> model_revocation, rag_corpus, eval_baseline, time_source
  health output overall: ok
    model_weights       ok        serving normally
    model_revocation    ok        serving normally
    policy_bundle       ok        current
    cve_feed            ok        serving normally
    container_images    ok        current
    rag_corpus          ok        serving normally
    eval_baseline       ok        serving normally
    time_source         ok        serving normally
```

The revocation list is 89 days past a 45-day budget. Every light is green. The
stack is not lying: each component is serving what it has, correctly.

## The year

```
                                        incl. clock   excl. clock
  something past its budget                  97.5%         62.2%
  stale with NOTHING anywhere saying so      89.3%         54.0%
```

**Act on the right column.** A free-running clock is past a 7-day budget on most
days by construction -- a true air gap has no NTP -- and
`tests/test_enclave.py` proves that staleness cannot change any other verdict.
Quoting only the larger number would be this repository doing what it
criticizes.

## What two models did with the same artifact

Both were handed exactly what an accreditation review receives -- the health
output and the package's stated budgets -- across 42 days balanced 14/14/14
across clean, announced and silent, and asked whether the enclave was within
its budgets, with `cannot_determine` available.

```
  model            stratum      correct
  claude-sonnet-5  clean          14/14
  claude-sonnet-5  announced      14/14
  claude-sonnet-5  silent         14/14
  gpt-5.4          (identical)    42/42

  AUDIT: name the signals whose freshness cannot be verified
  claude-sonnet-5   recall 100.0%   precision 100.0%
  gpt-5.4           recall 100.0%   precision 100.0%
```

**Both refused to certify on every non-announced day, and both named all six
unfalsifiable components with no false positives.** That is not a model
failure and it is not model excellence -- it is corroboration by two
independent judges that the artifact supports exactly one conclusion. The
models are not the weak link. The artifact is, and they demonstrate it by
being unable to do anything else with it.

**This measurement was designed to catch models trusting green lights, and it
caught a scoring key of mine instead.** The original key graded a clean day as
`within_budget`, which demands an assertion the evidence cannot support: no
view establishes freshness when six components never report it. Both models
answered correctly on all 42 days and I marked 28 of them wrong. The
pre-registration, written before the run, is in `audit/PREREGISTRATION.txt`.

## Claims backed by tests

| Claim | Test |
| --- | --- |
| The two-year run is deterministic, and a different seed gives a different year | `tests/test_enclave.py::test_the_simulation_is_deterministic` |
| Every one of the eight components can actually go past its budget, so no row is decoration | `tests/test_enclave.py::test_every_component_can_actually_go_stale` (checked over five years, because rare and impossible are different) |
| Transfers really are missed, so the miss rates are not quietly zero | `tests/test_enclave.py::test_transfers_are_actually_missed` |
| A component that does not track its input age reports `ok` on every day, including days it is months past budget | `tests/test_enclave.py::test_the_health_view_never_reveals_a_silent_component` |
| A component that does report its age shows as `degraded`, so the finding is that the health view is incomplete and not that it is useless | `tests/test_enclave.py::test_the_health_view_does_reveal_an_announcing_component` |
| The truth and the health view disagree on real days, which is the premise the repository rests on | `tests/test_enclave.py::test_the_truth_and_the_health_view_disagree` |
| Stale, silently stale, and stale-with-nothing-saying-so are nested, so the headline is a fraction of the row above it | `tests/test_enclave.py::test_the_three_counts_are_nested` |
| The silence is produced by the component behaviors and by nothing else | `tests/test_enclave.py::test_making_everything_announce_drives_the_silence_to_zero`, `::test_making_everything_silent_makes_every_stale_day_silent` (mutation-checked both ways: all-announcing drives the silent days to zero, all-silent makes every stale day a silent one) |
| The clock term cannot change any other verdict, which is why the right-hand column is the one to act on | `tests/test_enclave.py::test_the_clock_term_cannot_change_a_verdict` (mutation-checked: set the drift to zero and no day's verdict moves) |
| The view handed to a model does not contain the answer key | `tests/test_enclave.py::test_the_assessor_view_does_not_contain_the_answer_key` |
| The recommended view names exactly the components whose freshness cannot be evidenced, and they are exactly the silent ones | `tests/test_enclave.py::test_the_recommended_view_names_what_it_cannot_evidence` |
| Two of the eight components announce their input age and six do not | `tests/test_enclave.py::test_the_stack_is_mostly_unfalsifiable_and_that_is_stated` |

**The percentages are deliberately not in that table.** The 62% collision, the
54% figure and the year table are outputs of `scripts/offline_demo.py`: free to
re-run, deterministic under a fixed seed, and true of one set of stated
cadences rather than of enclaves in general. A test asserting them would pin a
constant, not a claim. What the tests pin is everything that has to hold before
those numbers mean anything -- that the components can go stale, that transfers
are missed, that the health view is blind exactly where it is claimed to be
blind, and that the clock term is immaterial.

The paid leg is absent for a second reason as well: it is evidence, and a test
that re-ran it would cost money on every commit and still not reproduce. Its
outcomes are in `audit/real_run.json`, the pre-registration written before it
in `audit/PREREGISTRATION.txt`, and the discarded run in
`audit/real_run_VOID_answer_key_in_prompt.json`.

## Reproducing

```
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                            # 13 tests
.venv/bin/python scripts/offline_demo.py --json audit/offline.json
```

Free, no API key. The paid leg prints its plan and exits without `--confirm`:

```
ENV_FILE=~/.secrets/ai.env .venv/bin/python scripts/real_run.py
```

| run | models | calls | cost | result |
|---|---|---|---|---|
| assess + audit | sonnet-5, gpt-5.4 | 168 | $0.69 | 42/42 both; audit 100/100 |
| (void) | sonnet-5, gpt-5.4 | 168 | $0.71 | answer key was in the prompt |

The void run is kept as `audit/real_run_VOID_answer_key_in_prompt.json`. A
discarded measurement that leaves no trace is the thing this portfolio's bug
logs keep objecting to.

## What this does not measure

- **Any vendor's software.** Every component is a pattern, and the behavior
  assigned to it is the behavior that pattern usually has, not a test result.
- **Any program's transfer discipline.** Cadences and miss rates are stated
  constants and every number in section 2 scales with them. Section 3 does not.
- **Whether the network is actually severed.** Auditing egress by observation
  rather than by documentation is a real and separate exercise; this repository
  assumes the gap and asks what happens behind it.
- **Loud failures.** Certificate expiry, signature validation and license
  refusal all break noisily inside an air gap. They are safe, and they are not
  what this measures.

## Layout

```
enclave/components.py       the eight components and what each does when stale
enclave/timeline.py         two years of transfers landing, or not
enclave/health.py           truth view, health view, assessor view, recommended
enclave/sampler.py          balanced strata, so no verdict wins on base rate
enclave/indistinguishable.py  the proof that needs no model
scripts/offline_demo.py     all four measurements, free
scripts/real_run.py         the paid leg, both providers
```

## Related repositories

One of sixteen small projects, each measuring one thing and publishing where
it fails:
[ai-compliance-checker](https://github.com/jkelly-dev1/ai-compliance-checker),
[vlm-extraction-integrity](https://github.com/jkelly-dev1/vlm-extraction-integrity),
[llm-observability-stack](https://github.com/jkelly-dev1/llm-observability-stack),
[prompt-injection-benchmark](https://github.com/jkelly-dev1/prompt-injection-benchmark),
[hardened-mcp-server](https://github.com/jkelly-dev1/hardened-mcp-server),
[ai-data-boundary-proxy](https://github.com/jkelly-dev1/ai-data-boundary-proxy),
[federated-retrieval-router](https://github.com/jkelly-dev1/federated-retrieval-router),
[least-privilege-agent](https://github.com/jkelly-dev1/least-privilege-agent),
[llm-eval-gate](https://github.com/jkelly-dev1/llm-eval-gate),
[citation-abstention-rag](https://github.com/jkelly-dev1/citation-abstention-rag),
[agentic-review-gate](https://github.com/jkelly-dev1/agentic-review-gate),
[typed-agent-service](https://github.com/jkelly-dev1/typed-agent-service),
[temporal-multi-agent](https://github.com/jkelly-dev1/temporal-multi-agent),
[agent-sandbox-escape](https://github.com/jkelly-dev1/agent-sandbox-escape),
[parser-eval](https://github.com/jkelly-dev1/parser-eval).

Two are worth reading directly against this one.
[llm-observability-stack](https://github.com/jkelly-dev1/llm-observability-stack)
asks the same question of a connected system: what the telemetry copies, what
it under-bills, and which failures it never keeps. This one asks what telemetry
means when it cannot be refreshed at all.
[ai-compliance-checker](https://github.com/jkelly-dev1/ai-compliance-checker)
measures the same boundary from the other side -- what fraction of a regulatory
decision can be made without ever being wrong -- and reaches the same place
from a different direction: the honest answer is often that the evidence does
not support one.

## License

MIT. See `LICENSE`.
