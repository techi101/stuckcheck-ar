"""Accuracy + confusion on a labelled synthetic set.

Usage: python -m stuckcheck.evaluate data/dev_set.json [data/holdout_set.json ...]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date

from .classifier import classify

TODAY = date(2026, 11, 20)  # fixed so results are reproducible


def evaluate(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    misses, confusion = [], Counter()
    for c in cases:
        r = classify(c["invoice"], c["thread"], today=TODAY)
        confusion[(c["label"], r.label)] += 1
        if r.label != c["label"]:
            misses.append((c["invoice"]["id"], c["label"], r.label))
    n = len(cases)
    correct = n - len(misses)
    return {"path": path, "n": n, "correct": correct, "accuracy": correct / n, "misses": misses}


def main(argv: list[str]) -> None:
    for path in argv or ["data/dev_set.json", "data/holdout_set.json"]:
        res = evaluate(path)
        print(f"{res['path']}: {res['correct']}/{res['n']} correct = {res['accuracy']:.0%}")
        for inv, gold, pred in res["misses"]:
            print(f"   miss {inv}: gold={gold:16s} pred={pred}")


if __name__ == "__main__":
    main(sys.argv[1:])
