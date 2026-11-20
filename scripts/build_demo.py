"""Turn the labelled holdout set into an unlabelled 'AR aging export' + threads file for the demo."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cases = json.loads((ROOT / "data/holdout_set.json").read_text(encoding="utf-8"))
cols = ["id", "customer", "amount", "amount_paid", "due_date", "days_past_due",
        "promised_date", "contact_bounced", "contact_first_name"]

with open(ROOT / "data/demo_aging.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for c in cases:
        inv = c["invoice"]
        w.writerow({k: str(inv.get(k, "")).lower() if k == "contact_bounced" and k in inv
                    else inv.get(k, "") for k in cols})

threads = {c["invoice"]["id"]: c["thread"] for c in cases}
(ROOT / "data/demo_threads.json").write_text(json.dumps(threads, indent=1), encoding="utf-8")
print(f"wrote {len(cases)} invoices")
