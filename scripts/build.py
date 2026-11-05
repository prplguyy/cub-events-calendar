"""Build the public site: one .ics feed per group and per club, plus calendars.json for the landing page."""
import hashlib
import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "events.json"
OUT = ROOT / "public"

# SharePoint site title -> group id. Any site not listed here is treated as a club.
GROUP_OF_SITE = {
    "Student Clubs": "campus",
    "TOS": "tos",
    "Student Sports @ Constructor": "sports",
    "Undergraduate Student Government": "usg",
    "Graduate Student Association": "usg",
    "RSA-DNA": "colleges",
    "Krupp Residential Support Assistants": "colleges",
    "College III - The place to be": "colleges",
    "Off Campus Student Hub": "colleges",
    "Pre-Degree Hub": "services",
    "telc at CU": "services",
    "CTL Hub": "services",
    "Program Services": "services",
    "E-Examination Resources": "services",
    "Admin & Faculty Communication": "services",
}
# Sites that should never be published.
SKIP_SITES = {"The test club"}

GROUPS = [
    ("campus", "Campus Events", "Official Student Life events from the Student Clubs site"),
    ("clubs", "All Clubs", "Every event posted by any student club"),
    ("tos", "TOS", "Bar nights and parties at The Other Side"),
    ("sports", "Student Sports", "Recreation Center and sports events"),
    ("usg", "Student Government", "USG and GSA events"),
    ("colleges", "Colleges & RSAs", "Residential college, RSA and off-campus hub events"),
    ("services", "Academic Services", "Pre-Degree Hub, telc and other university services"),
]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b = line.encode("utf-8")
    parts = []
    while len(b) > 75:
        i = 75
        while (b[i] & 0xC0) == 0x80:
            i -= 1
        parts.append(b[:i].decode("utf-8"))
        b = b" " + b[i:]
    parts.append(b.decode("utf-8"))
    return "\r\n".join(parts)


def ics_time(t):
    return t[:19].replace("-", "").replace(":", "") + "Z"


def vevent(e):
    uid = e.get("id") or hashlib.sha1(f'{e["site"]}|{e["title"]}|{e["start"]}'.encode()).hexdigest()[:20]
    lines = ["BEGIN:VEVENT", f"UID:{uid}@cub-events", "DTSTAMP:" + ics_time(e["start"])]
    if e.get("allday"):
        d0 = date.fromisoformat(e["start"][:10])
        d1 = max(date.fromisoformat(e["end"][:10]), d0) + timedelta(days=1)
        lines += [f"DTSTART;VALUE=DATE:{d0:%Y%m%d}", f"DTEND;VALUE=DATE:{d1:%Y%m%d}"]
    else:
        end = e["end"] if e["end"] > e["start"] else e["start"]
        lines += ["DTSTART:" + ics_time(e["start"]), "DTEND:" + ics_time(end)]
    title = e["title"]
    first_word = e["site"].lower().split()[0] if e["site"] else ""
    if e["site"] not in ("Student Clubs", "TOS") and first_word and first_word not in title.lower():
        title = f'{title} ({e["site"]})'
    lines.append("SUMMARY:" + esc(title))
    if e.get("location"):
        lines.append("LOCATION:" + esc(e["location"]))
    desc = f'Host: {e["site"]}'
    if e.get("category"):
        desc += f'\nCategory: {e["category"]}'
    desc += "\nSource: Student Clubs SharePoint"
    lines.append("DESCRIPTION:" + esc(desc))
    if "cancel" in e["title"].lower():
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def calendar(name, events):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CUB Events//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(f"CUB · {name}"), "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H",
    ]
    for e in events:
        lines += vevent(e)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main():
    events = [e for e in json.loads(DATA.read_text(encoding="utf-8")) if e["site"] not in SKIP_SITES]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "feeds").mkdir(parents=True)

    by_group, by_club = {}, {}
    for e in events:
        g = GROUP_OF_SITE.get(e["site"], "clubs")
        by_group.setdefault(g, []).append(e)
        if g == "clubs":
            by_club.setdefault(e["site"], []).append(e)

    today = date.today().isoformat()
    upcoming = lambda evs: sum(1 for e in evs if e["start"][:10] >= today)

    def write(fname, name, evs):
        (OUT / "feeds" / fname).write_text(calendar(name, evs), encoding="utf-8", newline="")

    manifest = {"updated": today, "everything": {"file": "feeds/all.ics", "upcoming": upcoming(events)},
                "groups": [], "clubs": []}
    write("all.ics", "Everything", events)
    for gid, name, blurb in GROUPS:
        evs = by_group.get(gid, [])
        write(f"{gid}.ics", name, evs)
        manifest["groups"].append({"id": gid, "name": name, "blurb": blurb,
                                   "file": f"feeds/{gid}.ics", "upcoming": upcoming(evs)})
    for club, evs in sorted(by_club.items(), key=lambda x: x[0].lower()):
        fname = f"club-{slug(club)}.ics"
        write(fname, club, evs)
        nxt = min((e for e in evs if e["start"][:10] >= today), key=lambda e: e["start"], default=None)
        manifest["clubs"].append({"name": club, "file": f"feeds/{fname}", "upcoming": upcoming(evs),
                                  "next": {"title": nxt["title"], "start": nxt["start"]} if nxt else None})

    (OUT / "calendars.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.copy(ROOT / "site" / "index.html", OUT / "index.html")
    (OUT / ".nojekyll").write_text("")
    print(f'{len(events)} events, {len(manifest["groups"])} groups, {len(manifest["clubs"])} clubs')


if __name__ == "__main__":
    main()
