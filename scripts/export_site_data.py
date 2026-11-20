"""Export the real stuckcheck output to site/data.json for the static demo page.

Usage: python scripts/export_site_data.py
Runs the same classifier + drafter as the CLI on data/demo_aging.csv and
data/demo_threads.json (synthetic), plus the evaluation on dev + holdout.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stuckcheck.classifier import classify  # noqa: E402
from stuckcheck.cli import TODAY, load_aging  # noqa: E402
from stuckcheck.drafter import draft  # noqa: E402
from stuckcheck.evaluate import evaluate  # noqa: E402

NOT_STUCK = ("genuinely_slow", "no_reply", "needs_review")


def main() -> None:
    invoices = load_aging(os.path.join(ROOT, "data", "demo_aging.csv"))
    with open(os.path.join(ROOT, "data", "demo_threads.json"), encoding="utf-8") as f:
        threads = json.load(f)
    with open(os.path.join(ROOT, "data", "holdout_set.json"), encoding="utf-8") as f:
        gold = {c["invoice"]["id"]: c["label"] for c in json.load(f)}

    rows = []
    for inv in invoices:
        thread = threads.get(inv["id"], [])
        r = classify(inv, thread, today=TODAY)
        d = draft(inv, r)
        rows.append({
            "id": inv["id"],
            "customer": inv["customer"],
            "amount": inv["amount"],
            "amount_paid": inv["amount_paid"],
            "open": inv["amount"] - inv["amount_paid"],
            "due_date": inv["due_date"],
            "days_past_due": inv["days_past_due"],
            "promised_date": inv["promised_date"],
            "contact_bounced": inv["contact_bounced"],
            "cause": r.label,
            "confidence": r.confidence,
            "stuck": r.label not in NOT_STUCK,
            "evidence": r.evidence,
            "hand_label": gold.get(inv["id"]),
            "thread": sorted(thread, key=lambda m: -m.get("days_ago", 0)),  # oldest first
            "draft": d,
        })

    counts = Counter(r["cause"] for r in rows)
    evals = [evaluate(os.path.join(ROOT, "data", p)) for p in ("dev_set.json", "holdout_set.json")]
    out = {
        "as_of": TODAY.isoformat(),
        "synthetic": True,
        "summary": {
            "invoices": len(rows),
            "open_total": sum(r["open"] for r in rows),
            "stuck_count": sum(r["stuck"] for r in rows),
            "stuck_open": sum(r["open"] for r in rows if r["stuck"]),
            "needs_review": counts.get("needs_review", 0),
            "cause_counts": dict(counts),
        },
        "evaluation": [
            {"set": os.path.basename(e["path"]), "n": e["n"], "correct": e["correct"],
             "misses": [{"id": i, "gold": g, "pred": p} for i, g, p in e["misses"]]}
            for e in evals
        ],
        "invoices": rows,
    }
    dest = os.path.join(ROOT, "site", "data.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    s = out["summary"]
    print(f"wrote {dest}: {s['invoices']} invoices, {s['stuck_count']} stuck, ${s['stuck_open']:,.0f} stuck open")


if __name__ == "__main__":
    main()
