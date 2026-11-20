from datetime import date
from pathlib import Path

from stuckcheck.classifier import LABELS, classify
from stuckcheck.drafter import TEMPLATES, draft
from stuckcheck.evaluate import evaluate

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 20)


def inv(**kw):
    base = {"id": "INV-1", "customer": "Test Co (synthetic)", "amount": 1000.0,
            "amount_paid": 0.0, "due_date": "2026-10-01", "days_past_due": 50}
    base.update(kw)
    return base


def cust(text, days_ago=1):
    return {"from": "customer", "days_ago": days_ago, "text": text}


# ---- Classifier: one clear case per cause ----
def test_already_paid():
    assert classify(inv(), [cust("We already paid this, remittance attached.")], TODAY).label == "already_paid"

def test_short_paid_from_ledger_alone():
    assert classify(inv(amount_paid=600), [], TODAY).label == "short_paid"

def test_portal_rejected():
    assert classify(inv(), [cust("Coupa rejected it, please resubmit.")], TODAY).label == "portal_rejected"

def test_missing_po():
    assert classify(inv(), [cust("Please add the PO number.")], TODAY).label == "missing_po"

def test_contact_left_from_bounce_flag():
    assert classify(inv(contact_bounced=True), [], TODAY).label == "contact_left"

def test_approval_stalled():
    assert classify(inv(), [cust("Still pending approval with our CFO.")], TODAY).label == "approval_stalled"

def test_never_received():
    assert classify(inv(), [cust("We never received it.")], TODAY).label == "never_received"

def test_promise_broken_needs_past_date():
    t = [cust("It will be paid on Friday.")]
    assert classify(inv(promised_date="2026-11-14"), t, TODAY).label == "promise_broken"

def test_promise_in_future_is_not_broken():
    r = classify(inv(promised_date="2026-11-27"), [], TODAY)
    assert r.label != "promise_broken"

def test_genuinely_slow():
    assert classify(inv(), [cust("Cash flow is tight, can we do a payment plan?")], TODAY).label == "genuinely_slow"

def test_silence_is_no_reply():
    t = [{"from": "us", "days_ago": 7, "text": "reminder"}]
    assert classify(inv(), t, TODAY).label == "no_reply"

def test_unknown_reply_goes_to_human_not_guess():
    r = classify(inv(), [cust("Hmm, let me look into it.")], TODAY)
    assert r.label == "needs_review" and r.confidence == 0.0

def test_our_own_messages_do_not_trigger_cues():
    t = [{"from": "us", "days_ago": 3, "text": "Did you receive the PO number and approval?"}]
    assert classify(inv(), t, TODAY).label == "no_reply"

def test_newest_reply_wins():
    t = [cust("We never received it.", days_ago=10), cust("Got it now, it's pending approval.", days_ago=1)]
    assert classify(inv(), t, TODAY).label == "approval_stalled"

def test_evidence_is_returned():
    r = classify(inv(), [cust("Please add the PO number.")], TODAY)
    assert any("missing_po" in e for e in r.evidence)


# ---- Drafter ----
def test_every_label_has_a_template():
    for label in LABELS + ["needs_review"]:
        assert label in TEMPLATES

def test_short_paid_draft_states_the_gap():
    i = inv(amount_paid=600)
    d = draft(i, classify(i, [], TODAY))
    assert "$400.00" in d["body"] and "INV-1" in d["body"]

def test_drafts_differ_by_cause():
    a = draft(inv(), classify(inv(), [cust("We never received it.")], TODAY))
    b = draft(inv(), classify(inv(), [cust("Please add the PO number.")], TODAY))
    assert a["body"] != b["body"]


# ---- Eval sets: guard the reported numbers ----
def test_dev_set_accuracy():
    assert evaluate(str(ROOT / "data/dev_set.json"))["accuracy"] >= 0.9

def test_holdout_accuracy_floor():
    # Holdout was written before the rules were run and never tuned on.
    assert evaluate(str(ROOT / "data/holdout_set.json"))["accuracy"] >= 0.75
