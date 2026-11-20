"""Cause-specific follow-up drafts. Drafts only; nothing is ever sent."""
from __future__ import annotations

from .classifier import Result

# ---- One template per cause: (internal next step, email body) --------------
TEMPLATES: dict[str, tuple[str, str]] = {
    "already_paid": (
        "Check bank feed / unapplied cash for this amount before chasing again.",
        "Thanks for letting us know {inv} was paid. We can't match it on our side yet. "
        "Could you share the remittance or payment reference (date + amount) so we can apply it?",
    ),
    "short_paid": (
        "Pull PO, receipt and agreed rate; hand the gap to an analyst to accept or contest.",
        "We received {paid} against {inv} for {amount}, leaving {gap} open. "
        "Could you tell us which line the difference relates to? We'll check it against the PO and delivery records.",
    ),
    "portal_rejected": (
        "Open the portal, read the rejection reason, fix and resubmit.",
        "It looks like {inv} was rejected in your portal. We're correcting it and resubmitting today. "
        "If there's a field your AP team needs filled differently, let us know and we'll match it.",
    ),
    "missing_po": (
        "Search earlier threads / order docs for the PO; if not found ask the buyer, not AP.",
        "{inv} needs a PO number to be processed on your side. Could you send the PO for this order, "
        "or point us to the person who raised it? We'll reissue the invoice with it straight away.",
    ),
    "contact_left": (
        "Find the new AP contact (signature lines, LinkedIn, sales rep) before resending.",
        "Our usual AP contact for your account seems to have moved on. Could you point us to whoever now "
        "handles supplier invoices? We'd like to make sure {inv} ({amount}) reaches the right person.",
    ),
    "approval_stalled": (
        "Ask who the approver is and follow up with them directly, not the shared AP inbox.",
        "Thanks for the update on {inv}. Could you let us know who is approving it, and whether there's "
        "anything they need from us (receipt, timesheet, contract) to sign off?",
    ),
    "never_received": (
        "Resend the invoice PDF and confirm the correct AP address / portal.",
        "Sorry about that. Attached is {inv} for {amount}. Could you confirm this is the right address "
        "for invoices going forward, or whether it should go through a portal?",
    ),
    "promise_broken": (
        "Promise date passed with no cash: follow up in the original thread, same day.",
        "Following up on {inv}: we had it down for payment on {promised}, but we haven't seen it arrive yet. "
        "Could you check whether it went out in that run, or let us know the new date?",
    ),
    "genuinely_slow": (
        "Customer is slow, not stuck: offer a written payment plan; flag for credit review.",
        "Thanks for being upfront about timing on {inv}. Would a short payment plan help? For example "
        "{half} now and the rest in 30 days. Happy to put it in writing.",
    ),
    "no_reply": (
        "No reply after chasing: try a different channel (phone) or contact; check address is right.",
        "Checking in on {inv} for {amount}, now {dpd} days past due. Is there anything holding it up on "
        "your side, or someone else we should be speaking with?",
    ),
    "needs_review": (
        "Rules could not tell why. A person reads the thread before anything is sent.",
        "[No draft: cause unclear for {inv}. Read the thread first.]",
    ),
}


def _money(x: float, cur: str) -> str:
    return f"{cur}{x:,.2f}"


def draft(invoice: dict, result: Result) -> dict:
    """Return {subject, body, next_step} for one classified invoice."""
    cur = invoice.get("currency_symbol", "$")
    amount = float(invoice["amount"])
    paid = float(invoice.get("amount_paid", 0) or 0)
    fields = {
        "inv": f"invoice {invoice['id']}",
        "amount": _money(amount, cur),
        "paid": _money(paid, cur),
        "gap": _money(amount - paid, cur),
        "half": _money(round((amount - paid) / 2, 2), cur),
        "promised": invoice.get("promised_date") or "the date you gave us",
        "dpd": invoice.get("days_past_due", "several"),
    }
    next_step, body = TEMPLATES[result.label]
    text = body.format(**fields)
    text = text[0].upper() + text[1:]  # templates may open with "{inv}"
    greeting = f"Hi {invoice.get('contact_first_name') or 'there'},"
    return {
        "subject": f"Re: Invoice {invoice['id']}",
        "body": f"{greeting}\n\n{text}\n\nThanks,\n{{your name}}",
        "next_step": next_step,
    }
