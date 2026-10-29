"""Pick the best tracks of each sub-style so they can be auditioned by ear.

Reads catalog/tracks.csv, keeps v3+ tracks and, per style, the highest quality scores.
Writes the list of file names to stdout (one per line), `name<TAB>style<TAB>score<TAB>title`.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

PER_STYLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2

rows = [r for r in csv.DictReader(open("catalog/tracks.csv", encoding="utf-8")) if r["file"].startswith(("fc3-", "fc4-"))]
by: dict[str, list[dict[str, str]]] = defaultdict(list)
for r in rows:
    by[r["style"]].append(r)
for style, items in sorted(by.items()):
    items.sort(key=lambda r: float(r["quality_score"] or 0), reverse=True)
    for r in items[:PER_STYLE]:
        print(f"{r['file']}\t{style}\t{r['quality_score']}\t{r['title']}\t{r['bpm']}")
