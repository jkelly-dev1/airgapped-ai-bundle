# SAMPLE_RUN

Actual output, not a transcript written by hand. The offline half regenerates
with `scripts/offline_demo.py`; the paid half is in `audit/`.

## Tests

```
$ .venv/bin/python -m pytest -q
.............
13 passed in 0.02s
```

Three of them exist because of defects they caught: every component must be
able to go stale (three could not, one structurally); the clock term must not
change any verdict (a claim made and withdrawn); and the assessor view must not
contain the answer key (it did, and it voided a paid run).

## The offline measurement

```
$ .venv/bin/python scripts/offline_demo.py --json audit/offline.json
airgapped-ai-bundle -- offline measurement
no model was called   simulated days: 730

1. THE STACK
   8 components depend on something outside the boundary
   2 can report their own input age; 6 cannot
   silent: model_weights, model_revocation, cve_feed, rag_corpus, eval_baseline, time_source

2. THE YEAR (730 days)
                                           incl. clock  excl. clock
   something past its budget                     95.5%        53.7%
   stale with NOTHING anywhere saying so         86.2%        44.4%
   The clock is past a 7-day budget on most days by construction --
   an air gap has no NTP -- and tests/test_enclave.py proves that
   staleness cannot change any other verdict. Act on the right column.

   component           budget  stale days  max age  reports age
   model_weights          180      0 ( 0.0%)      179  False
   model_revocation        45    100 (13.7%)       89  False
   policy_bundle           21     68 ( 9.3%)       41  True
   cve_feed                45     72 ( 9.9%)       89  False
   container_images        60      0 ( 0.0%)       59  True
   rag_corpus              14     18 ( 2.5%)       20  False
   eval_baseline          120    194 (26.6%)      314  False
   time_source              7    667 (91.4%)      179  False

3. THE ARTIFACT: how often it cannot tell the two apart
   distinct views seen on clean days     242
   distinct views seen on silent days    222
   views occurring in BOTH strata        134
   -> 210 of 338 clean days (62.1%) produce a view that also
      occurs on a day something was months past budget
   -> 186 of 324 silent days (57.4%) produce a view that also
      occurs on a day when nothing was wrong at all
   The bytes are identical. No reader can distinguish them because
   there is nothing there to distinguish.

4. ONE DAY -- day 226
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

wrote audit/offline.json
```

## The paid measurement

168 calls, two providers, $0.69. Both models handed the health output and the
stated budgets -- what an accreditation review receives -- over 42 days
balanced 14/14/14 across clean, announced and silent.

```
ASSESS -- verdict against what the evidence can support
  model            stratum      correct   wrong  unparsed
  claude-sonnet-5  clean         14/14        0         0
  claude-sonnet-5  announced     14/14        0         0
  claude-sonnet-5  silent        14/14        0         0
  gpt-5.4          clean         14/14        0         0
  gpt-5.4          announced     14/14        0         0
  gpt-5.4          silent        14/14        0         0

AUDIT -- did it name the signals that cannot be verified
  model                        recall          precision  named nothing
  claude-sonnet-5              100.0%             100.0%              0
  gpt-5.4                      100.0%             100.0%              0
```

BOTH MODELS ANSWERED `cannot_determine` ON EVERY CLEAN AND EVERY SILENT DAY,
and `outside_budget` on every announced day. Two independent judges, one
answer, on an artifact that supports exactly one conclusion.

WHAT WENT WRONG WITH THIS MEASUREMENT, TWICE. The first run had
`components_that_can_evidence_their_own_freshness` in the prompt -- the answer
key -- and was voided and re-run. Removing it changed nothing, which is how I
learned it was not the cause. The cause was my SCORING KEY: it graded a clean
day as `within_budget`, which asks for an assertion the evidence cannot
support, because six components never report an input age. Both models were
right on all 42 days and I had marked 28 wrong.

The offline proof in section 3 is what the paid run corroborates, and it is
free: 134 distinct views occur in both strata.

## What is not measured here

Any vendor's software, any program's transfer discipline, or whether the gap
is actually intact. Cadences and miss rates are stated constants in
`enclave/timeline.py` and every number in section 2 scales with them. Section 3
is a property of the artifact's shape and does not.
