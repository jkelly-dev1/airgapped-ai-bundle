"""The spending ceiling, tested against what a run is BILLED.

Why this file exists. `--max-cost` was compared only against the pre-flight
estimate, which is built from an ASSUMED output length per provider. A model
that runs longer than that assumption bills more than the estimate, and
nothing was checking the difference: the token counters the providers returned
were accumulated all the way through the run, totaled once at the end, and
printed. A ceiling on a guess is not a ceiling.

These tests drive the real calling loop with a fake `call_for`, so no API key
is needed and nothing is billed. That is also why `run_calls` is a function
rather than a stretch of `main()`. The paid path had no test at all before
this, which is how the gap survived.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from real_run import PRICING, run_calls, spend_usd   # noqa: E402

MODEL = "claude-sonnet-5"


def _days(n):
    """`n` (stratum, day) pairs from the simulation the paid run samples."""
    from enclave.timeline import simulate
    tl = simulate(400)
    from real_run import CLEAN
    return [(CLEAN, d) for d in tl[:n]]


def _reply(out_tokens):
    """A parseable assessor reply that bills `out_tokens` of output."""
    def call(_client, _model, _prompt):
        return ('{"verdict": "ok", "unverifiable": []}',
                {"input_tokens": 1000, "output_tokens": out_tokens,
                 "stop_reason": "end_turn"})
    return call


def test_spend_usd_prices_both_directions_from_the_price_table():
    spend = Counter({(MODEL, "in"): 1_000_000, (MODEL, "out"): 1_000_000})
    assert spend_usd(spend, [MODEL]) == (PRICING[MODEL]["in"]
                                         + PRICING[MODEL]["out"])


def test_a_run_that_stays_under_the_ceiling_makes_every_call():
    days = _days(4)
    records, spend = run_calls([MODEL], days, "inv", max_cost=1000.0,
                               client_for=lambda m: None,
                               call_for=lambda m: _reply(900),
                               echo=lambda *a, **k: None)
    assert len(records) == 8, "four days x two conditions"
    assert spend_usd(spend, [MODEL]) < 1000.0


def test_the_ceiling_stops_a_run_that_bills_past_it():
    """The load-bearing test. Output long enough that the bill crosses a
    ceiling the pre-flight estimate would have cleared. The run must stop, and
    it must stop having recorded fewer calls than it was asked to make."""
    days = _days(20)
    asked = len(days) * 2
    ceiling = 0.05
    records, spend = run_calls([MODEL], days, "inv", max_cost=ceiling,
                               client_for=lambda m: None,
                               call_for=lambda m: _reply(4000),
                               echo=lambda *a, **k: None)
    assert len(records) < asked, (
        f"billed ${spend_usd(spend, [MODEL]):.4f} against a ${ceiling} "
        f"ceiling and still made all {asked} calls")
    assert spend_usd(spend, [MODEL]) > ceiling, (
        "the test did not actually cross the ceiling, so it proves nothing")


def test_the_run_stops_on_the_first_call_that_crosses():
    """It stops AT the crossing, not one lap later. The call that crosses is
    kept, it was billed whether or not it is recorded, but nothing after it
    is made."""
    days = _days(20)
    per_call = 1000 / 1e6 * PRICING[MODEL]["in"] \
        + 4000 / 1e6 * PRICING[MODEL]["out"]
    ceiling = per_call * 3.5           # crossed by the 4th call
    records, _ = run_calls([MODEL], days, "inv", max_cost=ceiling,
                           client_for=lambda m: None,
                           call_for=lambda m: _reply(4000),
                           echo=lambda *a, **k: None)
    assert len(records) == 4, f"expected to stop at the 4th call, got {len(records)}"
