"""Merge a SharePoint export (sent by the Power Automate flow) into data/events.json.

Payload shape (GitHub repository_dispatch client_payload):
  {"since": "YYYY-MM-DD",
   "rows": [[site, title, start, end, location, category, allday, uniqueId], ...]}

Events that start before `since` are kept from the stored history.
Everything from `since` onward is replaced by the payload, so edits,
new events and deletions on SharePoint all show up.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "events.json"


def norm_time(v):
    # SharePoint search returns e.g. 2026-11-05T18:00:00.0000000Z
    v = (v or "").strip()
    if not v:
        return ""
    return v[:19] + "Z"


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes")


def main(payload_path):
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    since = payload["since"]
    rows = payload.get("rows") or []
    if isinstance(rows, str):
        rows = json.loads(rows)

    incoming = []
    for r in rows:
        r = list(r) + [""] * (8 - len(r))
        site, title, start, end, loc, cat, allday, uid = r[:8]
        start = norm_time(start)
        if not title or not start:
            continue
        incoming.append({
            "site": (site or "").strip(),
            "title": title.strip(),
            "start": start,
            "end": norm_time(end) or start,
            "location": (loc or "").strip(),
            "category": (cat or "").strip(),
            "allday": truthy(allday),
            "id": (uid or "").strip("{} "),
        })

    if not incoming:
        # An empty export almost certainly means the query failed; keep what we have.
        print("Payload had no events; leaving data unchanged.")
        return

    stored = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []
    history = [e for e in stored if e["start"][:10] < since]
    merged = sorted(history + incoming, key=lambda e: (e["start"], e["site"], e["title"]))
    DATA.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Kept {len(history)} past events, got {len(incoming)} from SharePoint since {since}.")


if __name__ == "__main__":
    main(sys.argv[1])
