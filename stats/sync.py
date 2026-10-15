#!/usr/bin/env python3
"""Sync the stats store straight from the Sportradar embed API behind fesabal.org (no browser needed).

usage: python3 stats/sync.py [--recheck-days 14] [--only 16M,16F]
Reads stats/sources.json (per league: fixtures_url "All rounds", standings_url, leaders_url; captured once
from the fesabal widget). For every played fixture: downloads its box score if we don't have it yet, or if
it is recent (re-checked for --recheck-days in case fesabal corrects it). Saves standings + leaders as
published by fesabal. Then calls the same ingest as the browser dump, so files stay identical in format.
Prints a short report only.
"""
import sys, os, json, time, urllib.request, urllib.parse, re
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = "https://embed-api.eui.connect.sportradar.com/v1/embed/13/"
SRC = json.load(open(os.path.join(HERE, "sources.json"), encoding="utf-8"))
recheck = int(sys.argv[sys.argv.index("--recheck-days") + 1]) if "--recheck-days" in sys.argv else 14
only = set(sys.argv[sys.argv.index("--only") + 1].upper().split(",")) if "--only" in sys.argv else None
season = SRC.get("season", "clausura-2026")


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bkbfanssv-sync"}), timeout=40) as r:
                return json.load(r)
        except Exception as e:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def state_of(link):
    s = link.split("~w=", 1)[1] if "~w=" in link else link
    s = urllib.parse.unquote(s.split("&")[0])
    return re.sub(r"^[a-z]~", "", s)


def players_of(data):
    out, seen = [], set()
    def walk(o):
        if isinstance(o, dict):
            if "personName" in o and "statistics" in o and "starter" in o:
                k = o.get("personId") or (o["personName"] + str(o.get("entityId")))
                if k not in seen:
                    seen.add(k)
                    out.append({"id": o.get("personId"), "n": o["personName"], "t": o.get("entityId"), "bib": o.get("bib"),
                                "img": (o.get("personImage") or "").split("/")[-1].split("?")[0], "pos": o.get("position"),
                                "st": bool(o.get("starter")), "p": bool(o.get("participated")),
                                "dnp": o.get("didNotPlayReason"), "s": o.get("statistics") or {}})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return out


now = datetime.now(timezone.utc)
dump = {"leagues": {}, "fetched_at": now.isoformat()}
report = []
for code, L in SRC["leagues"].items():
    if only and code not in only:
        continue
    gdir = os.path.join(ROOT, "data", season, code.lower(), "games")
    have = {f[:-5] for f in os.listdir(gdir)} if os.path.isdir(gdir) else set()
    fl = get(L["fixtures_url"])["data"]
    games, skipped = [], 0
    for f in fl.get("fixtures", []):
        if not all(str(c.get("score", "")).strip() not in ("", "None") for c in f["competitors"]):
            continue  # not played yet
        fid = f.get("fixtureId")
        when = None
        if fid in have:
            old = json.load(open(os.path.join(gdir, fid + ".json"), encoding="utf-8"))
            when = datetime.fromisoformat(old["date"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone(timedelta(hours=-6)))  # fesabal times are El Salvador local
            if when < now - timedelta(days=recheck):
                skipped += 1; continue
        st = state_of(f["link"])
        d = get(API + "fixture_detail?state=" + urllib.parse.quote(st))["data"]
        fx = d["banner"]["fixture"]
        games.append({"id": fx["id"], "state": st, "date": fx["startDateTime"], "status": fx.get("status"),
                      "pool": fx.get("poolName") or f.get("pool") or None, "round": f.get("round"),
                      "venue": (fx.get("venue") or {}).get("name") if isinstance(fx.get("venue"), dict) else fx.get("venue"),
                      "teams": [{"id": c["entityId"], "name": c["name"], "code": c.get("code"), "home": c.get("isHome"),
                                 "score": c.get("score"), "logo": (c.get("logo") or "").split("/")[-1].split("?")[0]} for c in fx["competitors"]],
                      "players": players_of(d)})
        time.sleep(0.5)
    standings = leaders = None
    try:
        standings = get(L["standings_url"])["data"]
        leaders = get(L["leaders_url"])["data"]
    except Exception as e:
        report.append(f"{code}: standings/leaders failed: {e}")
    dump["leagues"][code] = {"competition": L["competition"], "games": games, "standings": standings}
    ldir = os.path.join(ROOT, "data", season, code.lower()); os.makedirs(ldir, exist_ok=True)
    if leaders is not None:
        json.dump(leaders.get("statistics", leaders), open(os.path.join(ldir, "fesabal-leaders.json"), "w", encoding="utf-8"), ensure_ascii=False)
    report.append(f"{code}: {len(games)} fetched, {skipped} stored and final")

tmp = os.path.join(ROOT, "logs", "last-sync-dump.json")
os.makedirs(os.path.dirname(tmp), exist_ok=True)
json.dump(dump, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
print("\n".join(report))
os.execvp(sys.executable, [sys.executable, os.path.join(HERE, "ingest.py"), tmp, "--season", season])
