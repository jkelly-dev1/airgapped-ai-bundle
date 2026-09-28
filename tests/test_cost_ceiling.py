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


def test_a_paid_run_does_not_overwrite_stored_evidence(tmp_path, monkeypatch,
                                                       capsys):
    """--confirm with an existing --out refuses before anything is spent.

    The default --out is the stored paid run. A dry run and a run to a new
    file are unaffected, and --force is the explicit way to replace it.
    """
    import real_run

    stored = tmp_path / "real_run.json"
    stored.write_text('{"stored": true}\n', encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["real_run.py", "--confirm",
                                      "--out", str(stored)])
    assert real_run.main() == 2
    assert "already exists" in capsys.readouterr().out
    assert stored.read_text(encoding="utf-8") == '{"stored": true}\n'

    # A dry run against the same file refuses nothing on that account.
    monkeypatch.setattr(sys, "argv", ["real_run.py", "--out", str(stored)])
    real_run.main()
    assert "already exists" not in capsys.readouterr().out

    # Nor does a confirmed run to a file that does not exist yet, or one with
    # --force. Both stop later, at the SDK or the key, which is not tested here.
    for extra in (["--out", str(tmp_path / "new.json")],
                  ["--out", str(stored), "--force"]):
        monkeypatch.setattr(sys, "argv", ["real_run.py", "--confirm", *extra])
        monkeypatch.setattr(real_run, "_api_key", lambda name: (_ for _ in ()).throw(
            SystemExit("stopped at the key")))
        try:
            real_run.main()
        except SystemExit:
            pass
        assert "already exists" not in capsys.readouterr().out


# ------------------------------------------------ the report over the records

def test_a_failed_call_stays_in_the_report_denominators():
    """A call that raised is still a call that was asked. Every third call
    fails here; the report must count those failures in their stratum and
    keep them in the denominator instead of printing a perfect score over
    the calls that happened to succeed."""
    import json
    from real_run import CORRECT, report
    from enclave.sampler import sample
    days = sample(per_stratum=2)
    n = {"calls": 0}

    def flaky(_client, _model, _prompt):
        n["calls"] += 1
        if n["calls"] % 3 == 0:
            raise RuntimeError("provider unavailable")
        # Every fifth call answers in prose, so the unparsed column has
        # something to count and cannot be confused with the failed one.
        text = ("no object here" if n["calls"] % 5 == 0 else
                json.dumps({"verdict": "cannot_determine",
                            "unverifiable": []}))
        return (text, {"input_tokens": 10, "output_tokens": 10,
                       "stop_reason": "end_turn"})

    records, _ = run_calls([MODEL], days, "inv", max_cost=1000.0,
                           client_for=lambda m: None,
                           call_for=lambda m: flaky,
                           echo=lambda *a, **k: None)
    failed = [r for r in records if "error" in r]
    assert failed and all("stratum" in r for r in failed)
    # A failed call carries what it was scored against, like any other.
    for r in failed:
        if r["condition"] == "assess":
            assert r["correct"] == CORRECT[r["stratum"]], r
        else:
            assert "truth_unverifiable" in r, r
    lines = []
    report(records, [MODEL], echo=lines.append)
    rows = {ln.split()[1]: ln.split() for ln in lines
            if ln.strip().startswith(MODEL) and "%" not in ln}
    assert set(rows) == {"clean", "announced", "silent"}, lines
    for stratum, cols in rows.items():
        asked = sum(1 for r in records if r["condition"] == "assess"
                    and r["stratum"] == stratum)
        assert cols[2].endswith("/%d" % asked), (stratum, cols)
        in_stratum = [r for r in records if r["condition"] == "assess"
                      and r["stratum"] == stratum]
        assert int(cols[4]) == sum(1 for r in in_stratum
                                   if "error" not in r and not r["parsed"])
        assert int(cols[5]) == sum(1 for r in in_stratum if "error" in r)
    assert any(int(c[4]) for c in rows.values()), (
        "no unparsed reply reached the report, so its column was not tested")
    assert sum(int(c[-1]) for c in rows.values()) == sum(
        1 for r in failed if r["condition"] == "assess")
    right = sum(1 for r in records if r["condition"] == "assess"
                and r.get("parsed") and r["verdict"] == CORRECT[r["stratum"]])
    assert sum(int(c[2].split("/")[0]) for c in rows.values()) == right
    # AUDIT: a failed call is counted under failed, and only there.
    audit = [r for r in records if r["condition"] == "audit"]
    row = [ln.split() for ln in lines
           if ln.strip().startswith(MODEL) and "%" in ln]
    assert len(row) == 1, lines
    assert int(row[0][-1]) == sum(1 for r in audit if "error" in r) > 0
    assert int(row[0][-2]) == sum(1 for r in audit if "error" not in r
                                  and not r.get("named"))


def test_the_stored_paid_run_is_scored_with_the_current_key():
    """audit/real_run.json is the run the README reports. Each assess record
    stores the answer it was scored against, and that must be the key in
    real_run.CORRECT today, or the published table is a score under a key
    the code no longer states."""
    import json
    from real_run import CORRECT
    path = Path(__file__).resolve().parents[1] / "audit" / "real_run.json"
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    assess = [r for r in records if r.get("condition") == "assess"]
    assert assess
    for r in assess:
        assert r["correct"] == CORRECT[r["stratum"]], r
