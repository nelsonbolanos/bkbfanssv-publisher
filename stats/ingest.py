#!/usr/bin/env python3
"""Ingest a fesabal dump (made in the browser, see README) into the local stats store.

usage: python3 stats/ingest.py <dump.json> [--season clausura-2026]
Writes data/<season>/<code>/games/<fixture id>.json (one compact box score per game, overwritten only if it
changed) and data/<season>/<code>/standings.json (fesabal standings as published). Then rebuilds the index.
Validation per game: sum of player points per team must equal the team score, else the game is flagged.
"""
import sys, os, json, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
season = "clausura-2026"
if "--season" in sys.argv:
    season = sys.argv[sys.argv.index("--season") + 1]
dump = json.load(open(args[0], encoding="utf-8"))

KEEP = {"points": "pts", "rebounds": "reb", "assists": "ast", "steals": "stl", "blocks": "blk",
        "efficiency": "eff", "turnovers": "tov", "foulsPersonal": "pf", "plusMinus": "pm",
        "fieldGoalsMade": "fgm", "fieldGoalsAttempted": "fga", "pointsThreeMade": "tpm",
        "pointsThreeAttempted": "tpa", "freeThrowsMade": "ftm", "freeThrowsAttempted": "fta",
        "reboundsOffensive": "oreb", "reboundsDefensive": "dreb"}


def minutes(v):
    if not v or not isinstance(v, str) or not v.startswith("PT"):
        return 0.0
    m = s = 0.0
    x = v[2:]
    if "M" in x:
        a, x = x.split("M", 1); m = float(a or 0)
    if "S" in x:
        s = float(x.split("S")[0] or 0)
    return round(m + s / 60, 2)


def num(v):
    try:
        return float(v) if "." in str(v) else int(v)
    except (TypeError, ValueError):
        return 0


report = {"new": 0, "changed": 0, "same": 0, "flagged": []}
for code, L in dump["leagues"].items():
    gdir = os.path.join(ROOT, "data", season, code.lower(), "games")
    os.makedirs(gdir, exist_ok=True)
    for g in L["games"]:
        if str(g.get("status", "")).upper() not in ("", "CONFIRMED", "FINISHED", "FINAL", "OFFICIAL", "ENDED", "COMPLETE", "COMPLETED") \
                and not all(t.get("score") not in (None, "") for t in g["teams"]):
            continue
        players = []
        for p in g["players"]:
            s = p.get("s") or {}
            rec = {"id": p.get("id"), "name": p["n"], "team": p["t"], "bib": p.get("bib"), "img": p.get("img") or None,
                   "starter": bool(p.get("st")), "played": bool(p.get("p")), "min": minutes(s.get("minutes"))}
            for k, short in KEEP.items():
                if k in s:
                    rec[short] = num(s[k])
            players.append(rec)
        teams = [{"id": t["id"], "name": t["name"], "code": t.get("code"), "home": bool(t.get("home")),
                  "score": num(t.get("score")), "logo": t.get("logo") or None} for t in g["teams"]]
        game = {"id": g["id"], "date": g["date"], "pool": g.get("pool"), "venue": g.get("venue"), "status": g.get("status"),
                "teams": teams, "players": players, "state": g.get("state")}
        # validation: player points add up to the score
        bad = []
        for t in teams:
            tot = sum(p.get("pts", 0) for p in players if p["team"] == t["id"])
            if tot != t["score"]:
                bad.append(f"{t['name']} players {tot} vs score {t['score']}")
        if bad:
            game["check"] = bad
            report["flagged"].append(f"{code} {g['date'][:10]} {' / '.join(bad)}")
        path = os.path.join(gdir, f"{g['id']}.json")
        body = json.dumps(game, ensure_ascii=False, sort_keys=True)
        if os.path.exists(path):
            old = open(path, encoding="utf-8").read()
            if hashlib.md5(old.encode()).hexdigest() == hashlib.md5(body.encode()).hexdigest():
                report["same"] += 1; continue
            report["changed"] += 1
        else:
            report["new"] += 1
        open(path, "w", encoding="utf-8").write(body)
    if L.get("standings") is not None:
        json.dump({"competition": L.get("competition"), "data": L["standings"]},
                  open(os.path.join(ROOT, "data", season, code.lower(), "standings.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
print(json.dumps(report, ensure_ascii=False, indent=1))
