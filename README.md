# CUB Events Calendar

Subscribable calendars for Constructor University campus, club, TOS and sports events, kept in sync with the
[Student Clubs SharePoint](https://constructoruniversity.sharepoint.com/sites/StudentClubs/_layouts/15/Events.aspx).

Students open the GitHub Pages site, which is the one link to share, and subscribe to everything, a category, or individual clubs.
Each subscription is its own calendar they can tick on and off. New and changed events flow in automatically.

## How the sync works

```
SharePoint (needs CUB login)
   │  Power Automate flow, every 3 hours, runs as a CUB account
   │  1. SharePoint search: all events from 30 days ago onward, across every club site
   │  2. GitHub "repository dispatch" with the events as JSON
   ▼
GitHub Actions (.github/workflows/sync.yml)
   │  scripts/sync.py   merge into data/events.json (past events kept as history)
   │  scripts/build.py  write public/feeds/*.ics + calendars.json
   ▼
GitHub Pages  →  students' Google / Apple / Outlook calendars refresh the feeds
```

SharePoint needs a university login, so the export runs in Power Automate, which is part of CUB's Microsoft 365.
Both connectors it uses (SharePoint, GitHub) are standard, so no premium licence is needed.

## Setting up the Power Automate flow

Go to [make.powerautomate.com](https://make.powerautomate.com), then **Create → Scheduled cloud flow**, and set it to repeat every **3 hours**.

**1. Send an HTTP request to SharePoint** (SharePoint connector)
- Site Address: `https://constructoruniversity.sharepoint.com/sites/StudentClubs`
- Method: `POST`
- Uri: `_api/search/postquery`
- Headers:
  - `Accept`: `application/json;odata=nometadata`
  - `Content-Type`: `application/json;odata=nometadata`
- Body (paste as-is; the part in `@{…}` becomes a dynamic expression):

```json
{
  "request": {
    "Querytext": "ContentTypeId:0x0102* EventDateOWSDATE>=@{formatDateTime(addDays(utcNow(),-30),'yyyy-MM-dd')}",
    "RowLimit": 500,
    "TrimDuplicates": false,
    "SelectProperties": ["SiteTitle","Title","EventDateOWSDATE","EndDateOWSDATE","LocationOWSTEXT","CategoryOWSCHCS","fAllDayEventOWSBOOL","UniqueId"]
  }
}
```

**2. Select** (Data Operation)
- From: `body('Send_an_HTTP_request_to_SharePoint')?['PrimaryQueryResult']?['RelevantResults']?['Table']?['Rows']`
- Switch Map to text mode and use:
  `createArray(item()?['Cells'][0]?['Value'], item()?['Cells'][1]?['Value'], item()?['Cells'][2]?['Value'], item()?['Cells'][3]?['Value'], item()?['Cells'][4]?['Value'], item()?['Cells'][5]?['Value'], item()?['Cells'][6]?['Value'], item()?['Cells'][7]?['Value'])`

  The cells come back in the same order as `SelectProperties` above. If you change that list, change this too.

**3. Compose**
```
{"since": "@{formatDateTime(addDays(utcNow(),-30),'yyyy-MM-dd')}", "rows": @{body('Select')}}
```

**4. Create a repository dispatch event** (GitHub connector, sign in with an account that can push to this repo)
- Repository owner / name: this repo
- event_type: `sharepoint-sync`
- client_payload: `json(outputs('Compose'))`

Save, then **Test → Manually**. A run of “Sync and publish” should appear under the repo's **Actions** tab.

## Grouping

`scripts/build.py` → `GROUP_OF_SITE` maps SharePoint site titles to categories (Campus, TOS, Sports, Student Government,
Colleges & RSAs, Academic Services). Any site not listed is treated as a club and gets its own calendar.
`SKIP_SITES` hides sites such as test clubs.

## Running locally

```
python scripts/build.py      # writes public/
python -m http.server -d public
```

## Handover

The flow runs as whoever created it. Before that person graduates, move it to the shared account
(Power Automate → flow → Share / Save As), and reconnect the SharePoint and GitHub connections there.
