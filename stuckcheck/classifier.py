"""Late-invoice root-cause classifier (rules only, runs offline).

Input: one overdue invoice (ledger fields) + its email thread.
Output: a cause label, a confidence, and the evidence that fired.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# ---- Cause labels ----------------------------------------------------------
# First seven mirror the stuck reasons listed on meetalder.com and
# meetalder.com/collections; the last three cover "genuinely slow" and silence.
LABELS = [
    "already_paid",       # customer says it paid, ledger still open (unapplied cash)
    "short_paid",         # paid less than invoiced / amount dispute
    "portal_rejected",    # AP portal (Coupa, Ariba...) rejected the invoice
    "missing_po",         # customer needs a PO number on the invoice
    "contact_left",       # AP contact gone, mail bounces
    "approval_stalled",   # invoice sits with an approver
    "never_received",     # customer has no copy of the invoice
    "promise_broken",     # promised a pay date, date passed, no cash
    "genuinely_slow",     # cash-flow issue, asks for time / payment plan
    "no_reply",           # we chased, customer never answered
]

# Tie-break order when two causes score the same (more specific first).
PRIORITY = {label: i for i, label in enumerate(LABELS)}

# ---- Text cues per cause (matched on CUSTOMER messages only) ---------------
CUES: dict[str, list[str]] = {
    "already_paid": [
        r"\b(already|we) paid\b", r"\bpaid (this|it|that) on\b", r"\bremittance\b",
        r"\b(wire|ach|payment|check|cheque) (was|went) (sent|out|mailed|released)\b",
        r"\bcheck was mailed\b", r"\bpayment reference\b", r"\bcleared on our side\b",
        r"\bshows as paid\b",
    ],
    "short_paid": [
        r"\bshort[- ]?pa(y|id)\b", r"\bdeduct(ed|ion)\b", r"\bonly (received|got|delivered)\b",
        r"\b(rate|price|pricing) (is|was|looks) (wrong|incorrect|higher)\b",
        r"\bagreed (rate|price)\b", r"\bquantity (is|was) (wrong|off|incorrect)\b",
        r"\bpaid the (undisputed|correct) (portion|amount)\b", r"\bcredit (note|memo)\b",
        r"\boverbill", r"\bdisput",
    ],
    "portal_rejected": [
        r"\b(coupa|ariba|tungsten|openinvoice|basware|supplier portal|vendor portal)\b",
        r"\brejected\b", r"\bresubmit", r"\bsubmit (it )?(through|via|in) (the|our) portal\b",
        r"\bnot (in|on) (the|our) portal\b",
    ],
    "missing_po": [
        r"\bpo (number|#|no\.?)\b", r"\bpurchase order\b", r"\bpo\s*#",
        r"\bwithout a po\b", r"\bno po\b", r"\bneeds? a po\b",
    ],
    "contact_left": [
        r"\bno longer (with|at|works)\b", r"\bleft the company\b", r"\bhas left\b",
        r"\bmailbox (is )?not monitored\b", r"\bundeliverable\b", r"\baddress not found\b",
        r"\bdelivery (has )?failed\b", r"\bplease contact .* instead\b", r"\bnew ap contact\b",
    ],
    "approval_stalled": [
        r"\bapprov(al|er|e)\b", r"\bsign[- ]?off\b", r"\bsitting with\b",
        r"\bwaiting on (the )?(controller|cfo|vp|director|manager|budget owner)\b",
        r"\bnot (yet )?been released\b", r"\bon hold internally\b",
    ],
    "never_received": [
        r"\bnever (received|got|saw)\b", r"\b(didn'?t|did not|haven'?t|have not) (receive|get|see)\b",
        r"\bno record of\b", r"\bcan('t| not|not) find (this|the|that) invoice\b",
        r"\b(re)?send (us )?(a )?(copy|the invoice)\b", r"\bresend\b", r"\bnot in our system\b",
    ],
    "promise_broken": [
        r"\bwill (be )?pa(y|id)\b", r"\bpayment run\b", r"\bscheduled (for|on)\b",
        r"\bby (monday|tuesday|wednesday|thursday|friday|end of (the )?(week|month))\b",
        r"\bin (the )?next (pay|payment) (run|cycle)\b",
    ],
    "genuinely_slow": [
        r"\bcash ?flow\b", r"\btight (this|right now)\b", r"\bpayment plan\b",
        r"\binstal(l)?ments?\b", r"\bpartial payments?\b", r"\bmore time\b",
        r"\bwaiting (on|for) (our )?(own )?customers? to pay\b", r"\bfunding\b",
    ],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in CUES.items()}

# Words that cancel a promise-to-pay cue (customer is talking about a past
# payment, not a future one).
PAID_CONTEXT = re.compile(r"\b(already|was) (paid|sent)\b", re.I)


@dataclass
class Result:
    invoice_id: str
    label: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def classify(invoice: dict, thread: list[dict], today: date | None = None) -> Result:
    """Score each cause from ledger signals + customer replies; return the top one.

    invoice: {id, customer, amount, amount_paid, due_date, promised_date?, contact_bounced?}
    thread:  [{"from": "us"|"customer"|"system", "days_ago": int, "text": str}, ...]
    """
    today = today or date.today()
    scores = {label: 0.0 for label in LABELS}
    evidence: list[str] = []

    # ---- Structured ledger signals ----
    amount = float(invoice.get("amount", 0))
    paid = float(invoice.get("amount_paid", 0) or 0)
    if 0 < paid < amount:
        scores["short_paid"] += 3
        evidence.append(f"ledger: paid {paid:.2f} of {amount:.2f}")
    if invoice.get("contact_bounced"):
        scores["contact_left"] += 3
        evidence.append("ledger: last email to AP contact bounced")
    promised = _parse_date(invoice.get("promised_date"))
    if promised and promised < today and paid < amount:
        scores["promise_broken"] += 3
        evidence.append(f"ledger: promise to pay {promised.isoformat()} has passed")

    # ---- Text signals: customer + bounce notices, newest weighted higher ----
    msgs = [m for m in thread if m.get("from") in ("customer", "system")]
    msgs.sort(key=lambda m: m.get("days_ago", 0))  # newest first
    for rank, m in enumerate(msgs):
        weight = 2.0 if rank == 0 else 1.0
        text = m.get("text", "")
        for label, patterns in COMPILED.items():
            for p in patterns:
                hit = p.search(text)
                if not hit:
                    continue
                if label == "promise_broken" and PAID_CONTEXT.search(text):
                    continue
                scores[label] += weight
                evidence.append(f"{m['from']} ({m.get('days_ago', '?')}d ago): '{hit.group(0)}' -> {label}")
                break  # one hit per label per message

    # A promise only counts as broken if its date is gone. Text-only promise
    # with no ledger date: treat as weak.
    if not promised:
        scores["promise_broken"] *= 0.5

    # ---- Silence ----
    if not msgs:
        chases = sum(1 for m in thread if m.get("from") == "us")
        scores["no_reply"] = 1.0 + 0.5 * chases
        evidence.append(f"thread: {chases} follow-up(s) from us, no customer reply")

    best = max(LABELS, key=lambda l: (scores[l], -PRIORITY[l]))
    total = sum(scores.values())
    if scores[best] == 0:
        return Result(invoice["id"], "needs_review", 0.0, ["customer replied but no known cause matched; route to a human"], scores)
    confidence = round(scores[best] / total, 2) if total else 0.0
    return Result(invoice["id"], best, confidence, evidence, scores)
