#!/usr/bin/env python3
"""
Week 7 placeholder: load golden examples and report structure checks.
Full DSPy / LLM-as-judge scoring is implemented in Week 7.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    path = root / "golden_examples.json"
    if not path.exists():
        print(f"Missing {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("golden_examples.json must be a JSON array", file=sys.stderr)
        return 1
    print(f"Loaded {len(data)} golden examples from {path.name}")
    for ex in data:
        eid = ex.get("id", "?")
        inp = ex.get("input") or {}
        if not inp.get("url") or not inp.get("title"):
            print(f"  [warn] {eid}: missing url/title")
    print("Scaffold OK. Wire to live pipeline + judges in Week 7.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
