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
    "Krupp Residential Support Assistants": "colleges",
    "College III - The place to be": "colleges",
    "Off-Campus Student Hub": "campus",
    "Off Campus Student Hub": "campus",
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
    ("usg", "Student Government", "USG and GSA events (coming soon)"),
    ("colleges", "Residential Colleges", "College and RSA events (coming soon)"),
    ("services", "Academic Services", "Pre-Degree Hub, telc and other university services"),
]


# CSS colour names (RFC 7986 COLOR needs a CSS3 name) with their hex for Apple's calendar colour.
PALETTE = [
    ("crimson", "#DC143C"), ("darkorange", "#FF8C00"), ("goldenrod", "#DAA520"), ("seagreen", "#2E8B57"),
    ("teal", "#008080"), ("dodgerblue", "#1E90FF"), ("royalblue", "#4169E1"), ("slateblue", "#6A5ACD"),
    ("darkviolet", "#9400D3"), ("mediumvioletred", "#C71585"), ("hotpink", "#FF69B4"), ("sienna", "#A0522D"),
    ("olivedrab", "#6B8E23"), ("darkcyan", "#008B8B"), ("steelblue", "#4682B4"), ("indianred", "#CD5C5C"),
    ("chocolate", "#D2691E"), ("mediumseagreen", "#3CB371"), ("darkslateblue", "#483D8B"), ("orchid", "#DA70D6"),
]
GROUP_COLOR = {"campus": ("royalblue", "#4169E1"), "clubs": ("seagreen", "#2E8B57"), "tos": ("darkviolet", "#9400D3"),
               "sports": ("darkorange", "#FF8C00"), "usg": ("crimson", "#DC143C"), "colleges": ("teal", "#008080"),
               "services": ("slategray", "#708090")}


COLORS_FILE = ROOT / "data" / "colors.json"
_club_colors = json.loads(COLORS_FILE.read_text(encoding="utf-8")) if COLORS_FILE.exists() else {}


def color_for(site):
    """Groups have fixed colours. Each club gets the least-used palette colour the first
    time it appears; the choice is saved in data/colors.json so it never changes."""
    g = GROUP_OF_SITE.get(site)
    if g:
        return GROUP_COLOR[g]
    if site not in _club_colors:
        used = [list(_club_colors.values()).count(i) for i in range(len(PALETTE))]
        _club_colors[site] = used.index(min(used))
    return PALETTE[_club_colors[site]]


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
    parts = []
    if e.get("description"):
        parts.append(e["description"])
    info = f'Host: {e["site"]}'
    if e.get("category"):
        info += f'\nCategory: {e["category"]}'
    parts.append(info)
    if e.get("url"):
        parts.append(f'Event page with picture and details (CUB login): {e["url"]}')
    else:
        parts.append("Source: Student Clubs SharePoint")
    lines.append("DESCRIPTION:" + esc("\n\n".join(parts)))
    if e.get("url"):
        lines.append("URL:" + e["url"])
    lines.append("COLOR:" + color_for(e["site"])[0])
    if "cancel" in e["title"].lower():
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def calendar(name, events, color):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CUB Events//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:" + esc(f"CUB · {name}"), "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H",
        "COLOR:" + color[0], "X-APPLE-CALENDAR-COLOR:" + color[1],
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

    # Every known club gets a calendar, even before it posts its first event, so a
    # student who adds everything today also gets clubs that start posting later.
    known = json.loads((ROOT / "data" / "clubs.json").read_text(encoding="utf-8"))
    by_group, by_club = {}, {c: [] for c in known if c not in SKIP_SITES}
    for e in events:
        g = GROUP_OF_SITE.get(e["site"], "clubs")
        by_group.setdefault(g, []).append(e)
        if g == "clubs":
            by_club.setdefault(e["site"], []).append(e)

    today = date.today().isoformat()
    upcoming = lambda evs: sum(1 for e in evs if e["start"][:10] >= today)

    def write(fname, name, evs, color):
        (OUT / "feeds" / fname).write_text(calendar(name, evs, color), encoding="utf-8", newline="")

    manifest = {"updated": today, "everything": {"file": "feeds/all.ics", "upcoming": upcoming(events)},
                "groups": [], "clubs": []}
    write("all.ics", "Everything", events, ("darkslategray", "#2F4F4F"))
    for gid, name, blurb in GROUPS:
        evs = by_group.get(gid, [])
        write(f"{gid}.ics", name, evs, GROUP_COLOR[gid])
        if gid == "clubs":
            continue  # still published for existing subscribers, but the page adds each club separately
        manifest["groups"].append({"id": gid, "name": name, "blurb": blurb, "color": GROUP_COLOR[gid][1],
                                   "file": f"feeds/{gid}.ics", "upcoming": upcoming(evs)})
    for club, evs in sorted(by_club.items(), key=lambda x: x[0].lower()):
        fname = f"club-{slug(club)}.ics"
        write(fname, club, evs, color_for(club))
        nxt = min((e for e in evs if e["start"][:10] >= today), key=lambda e: e["start"], default=None)
        manifest["clubs"].append({"name": club, "file": f"feeds/{fname}", "color": color_for(club)[1], "upcoming": upcoming(evs),
                                  "next": {"title": nxt["title"], "start": nxt["start"]} if nxt else None})

    COLORS_FILE.write_text(json.dumps(_club_colors, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "calendars.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.copy(ROOT / "site" / "index.html", OUT / "index.html")
    (OUT / ".nojekyll").write_text("")
    print(f'{len(events)} events, {len(manifest["groups"])} groups, {len(manifest["clubs"])} clubs')


if __name__ == "__main__":
    main()
