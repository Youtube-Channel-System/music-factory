"""Keep catalog/tracks.json and catalog/tracks.csv in sync with the library release.

The catalog is the master list for every track the factory has kept: title, BPM, key,
length, the exact prompt and seed that made it, quality stats, and the fields a
distributor (DistroKid and similar) asks for when releasing to Spotify. Rows are never
removed; release fields (ISRC, release date, status) are filled in by hand later and kept.

    python catalog.py manifests/        # folder with tracks-*.json from the release
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "catalog"
ARTIST = "FOCUS & CO"
AI_NOTE = (
    "Instrumental generated with ACE-Step 1.5 (open-source, MIT) from text prompts written "
    "by FOCUS & CO; selected, titled and mastered by FOCUS & CO. No samples, no vocals, "
    "no imitation of any artist."
)
CSV_FIELDS = [
    "track_id", "title", "artist", "genre", "subgenre", "bpm", "key", "duration",
    "file", "style", "created_at", "release_status", "release_date", "isrc", "upc",
    "album", "explicit", "language", "ai_disclosure", "model", "seed", "caption",
]  # fmt: skip
MANUAL = ("release_status", "release_date", "isrc", "upc", "album")


def mmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _from_tags(t: dict) -> tuple[str, str]:
    """Older manifests keep BPM and key only in the tags."""
    bpm, key = str(t.get("bpm", "")), t.get("key", "")
    for tag in t.get("tags", []):
        if tag.endswith(" bpm") and not bpm:
            bpm = tag.split()[0]
        if tag.endswith(("minor", "major")) and not key:
            key = tag
    return bpm, key


def row(t: dict) -> dict:
    bpm, key = _from_tags(t)
    return {
        "track_id": Path(t["file"]).stem,
        "title": t["title"],
        "artist": ARTIST,
        "genre": "Electronic",
        "subgenre": "Deep House",
        "bpm": bpm,
        "key": key,
        "duration": mmss(float(t.get("duration_s", 0))),
        "file": t["file"],
        "style": t.get("style", "v1"),
        "created_at": t.get("created_at", ""),
        "release_status": "unreleased",
        "release_date": "",
        "isrc": "",
        "upc": "",
        "album": "",
        "explicit": "no",
        "language": "instrumental",
        "ai_disclosure": AI_NOTE,
        "model": t.get("model", ""),
        "seed": t.get("seed", ""),
        "caption": t.get("caption", ""),
    }


def main(folder: str) -> int:
    ROOT.mkdir(exist_ok=True)
    path = ROOT / "tracks.json"
    existing = {r["track_id"]: r for r in json.loads(path.read_text())} if path.exists() else {}
    added = 0
    for f in sorted(Path(folder).glob("tracks-*.json")):
        for t in json.loads(f.read_text()):
            r = row(t)
            if r["track_id"] in existing:
                for k in MANUAL:  # hand-filled release data always wins
                    r[k] = existing[r["track_id"]].get(k, r[k])
            else:
                added += 1
            existing[r["track_id"]] = r
    rows = sorted(existing.values(), key=lambda r: (r["created_at"], r["track_id"]))
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    with (ROOT / "tracks.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"catalog: {len(rows)} tracks ({added} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "manifests"))
