"""Run on an AR aging CSV + email threads JSON; print a triage table and write drafts.

Usage: python -m stuckcheck.cli data/demo_aging.csv data/demo_threads.json [--out out/followups.md]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import date

from .classifier import classify
from .drafter import draft

TODAY = date(2026, 11, 20)  # fixed for reproducible demo output


def load_aging(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["amount"] = float(r["amount"])
            r["amount_paid"] = float(r.get("amount_paid") or 0)
            r["days_past_due"] = int(r["days_past_due"])
            r["contact_bounced"] = r.get("contact_bounced", "").lower() == "true"
            r["promised_date"] = r.get("promised_date") or None
            rows.append(r)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("aging_csv")
    ap.add_argument("threads_json")
    ap.add_argument("--out", default="out/followups.md")
    a = ap.parse_args()

    invoices = load_aging(a.aging_csv)
    with open(a.threads_json, encoding="utf-8") as f:
        threads = json.load(f)

    results = []
    print(f"{'invoice':10s} {'customer':32s} {'open':>10s}  {'cause':16s} conf")
    for inv in invoices:
        r = classify(inv, threads.get(inv["id"], []), today=TODAY)
        results.append((inv, r))
        open_amt = inv["amount"] - inv["amount_paid"]
        print(f"{inv['id']:10s} {inv['customer'][:32]:32s} {open_amt:>10,.0f}  {r.label:16s} {r.confidence:.2f}")

    # ---- Headline a sales demo would lead with ----
    counts = Counter(r.label for _, r in results)
    stuck = sum(v for k, v in counts.items() if k not in ("genuinely_slow", "no_reply", "needs_review"))
    stuck_amt = sum(i["amount"] - i["amount_paid"] for i, r in results
                    if r.label not in ("genuinely_slow", "no_reply", "needs_review"))
    print(f"\n{stuck}/{len(results)} overdue invoices look STUCK (a fixable blocker), "
          f"${stuck_amt:,.0f} open. Causes: {dict(counts)}")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("# Follow-up drafts (synthetic data, nothing sent)\n\n")
        for inv, r in results:
            d = draft(inv, r)
            f.write(f"## {inv['id']} - {inv['customer']} - cause: {r.label} ({r.confidence:.2f})\n\n")
            f.write("Why: " + "; ".join(r.evidence) + "\n\n")
            f.write(f"Next step: {d['next_step']}\n\n")
            f.write(f"Subject: {d['subject']}\n\n```\n{d['body']}\n```\n\n")
    print(f"Drafts written to {a.out}")


if __name__ == "__main__":
    main()
