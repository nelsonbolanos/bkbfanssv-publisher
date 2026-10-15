#!/usr/bin/env python3
"""Query the local fesabal stats store (data/<season>/<code>/games/*.json). Prints ONLY the answer, small.

usage: python3 stats/q.py <command> <code> [options]        code = 14F 14M 16F 16M 18F 18M ...
  jornadas   <code>                         list jornadas (weekends with games) and dates
  games      <code> [-j N]                  results
  dreamteam  <code> [-j N | --torneo] [--min-games K]   top 5 by EFF (sum), ties -> PTS
  sixth      <code> [-j N | --torneo] [--min-games K]   top 5 by EFF from the bench (starter false)
  leaders    <code> [-j N | --torneo] [--top 5]         pts reb ast stl tpm blk eff (totals)
  standings  <code> [--group A]             2 pts win, 1 loss; pts, then point difference
  player     <code> <name part>             a player's games
options: --season clausura-2026 (default) · --data  (prints the pipe lines the story/carousel builders read)
Jornada = a weekend (Mon-Sun week) with games, numbered in order; default = the latest one.
"""
import sys, os, json, glob, re, unicodedata
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
a = sys.argv[1:]
if len(a) < 2:
    sys.exit(__doc__)
cmd, code = a[0], a[1].upper()
rest = a[2:]


def opt(name, default=None, cast=str):
    if name in rest:
        i = rest.index(name); v = rest[i + 1]; del rest[i:i + 2]; return cast(v)
    return default


def flag(name):
    if name in rest:
        rest.remove(name); return True
    return False


season = opt("--season", "clausura-2026")
jn = opt("-j", None, int)
torneo = flag("--torneo")
min_games = opt("--min-games", 1, int)
top = opt("--top", 5, int)
group = opt("--group", None)
as_data = flag("--data")

G = [json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(ROOT, "data", season, code.lower(), "games", "*.json"))]
if not G:
    sys.exit(f"no games stored for {code} ({season})")
G.sort(key=lambda g: g["date"])


def week(g):
    y, w, _ = date.fromisoformat(g["date"][:10]).isocalendar()
    return (y, w)


weeks = sorted({week(g) for g in G})
for g in G:
    g["j"] = weeks.index(week(g)) + 1
J = jn or len(weeks)
team = {t["id"]: t for g in G for t in g["teams"]}


def sel():
    return G if torneo else [g for g in G if g["j"] == J]


def label():
    return "TORNEO" if torneo else f"JORNADA {J}"


def agg(games, bench_only=False):
    P = {}
    for g in games:
        for p in g["players"]:
            if not p.get("played") or (bench_only and p.get("starter")):
                continue
            k = p.get("id") or (p["name"] + p["team"])
            r = P.setdefault(k, {"name": p["name"], "team": p["team"], "bib": p.get("bib"), "img": p.get("img"),
                                 "g": 0, "starts": 0, "min": 0.0, **{s: 0 for s in ("pts", "reb", "ast", "stl", "blk", "tpm", "eff")}})
            r["g"] += 1; r["starts"] += 1 if p.get("starter") else 0; r["min"] += p.get("min", 0)
            for s in ("pts", "reb", "ast", "stl", "blk", "tpm", "eff"):
                r[s] += p.get(s, 0) or 0
            if p.get("img"):
                r["img"] = p["img"]
    return list(P.values())


def tname(tid):
    return team.get(tid, {}).get("name", "?")


def tlogo(tid):
    return team.get(tid, {}).get("logo") or ""


def line(i, r, extra=""):
    return f"{i}. {r['name']} ({tname(r['team'])}) EFF {r['eff']} · {r['pts']} PTS {r['reb']} REB {r['ast']} AST · {r['g']} PJ {round(r['min'])} MIN{extra}"


if cmd == "jornadas":
    for i, w in enumerate(weeks, 1):
        ds = sorted({g["date"][:10] for g in G if week(g) == w})
        print(f"J{i}: {', '.join(ds)} · {sum(1 for g in G if week(g) == w)} games")

elif cmd == "games":
    for g in sel():
        h, v = sorted(g["teams"], key=lambda t: not t["home"])
        chk = "  [CHECK: " + "; ".join(g["check"]) + "]" if g.get("check") else ""
        print(f"{g['date'][:10]} {g.get('pool') or ''} {h['name']} {h['score']}-{v['score']} {v['name']}{chk}")

elif cmd in ("dreamteam", "sixth"):
    rows = [r for r in agg(sel(), bench_only=(cmd == "sixth")) if r["g"] >= min_games]
    if cmd == "sixth":
        rows = [r for r in rows if r["starts"] == 0]  # only games off the bench were counted
    rows.sort(key=lambda r: (-r["eff"], -r["pts"], -(r["reb"] + r["ast"])))
    if as_data:
        for r in rows[:top + (1 if cmd == "sixth" else 0)]:
            base = f"{r['name']}|{tname(r['team'])}|{r['eff']}|{r['pts']}|{r['reb']}|{r['ast']}|{r['g']}|{r['bib'] or ''}|{r['img'] or ''}|{tlogo(r['team'])}"
            print(base + (f"|{round(r['min'])}" if cmd == "sixth" else ""))
    else:
        print(f"{'SEXTO' if cmd == 'sixth' else 'DREAM TEAM'} {code} · {label()}")
        for i, r in enumerate(rows[:top], 1):
            print(line(i, r))

elif cmd == "leaders":
    rows = agg(sel())
    cats = [("points", "pts"), ("rebounds", "reb"), ("assists", "ast"), ("steals", "stl"),
            ("pointsThreeMade", "tpm"), ("blocks", "blk"), ("efficiency", "eff")]
    for cat, k in cats:
        rs = sorted([r for r in rows if r["g"] >= min_games], key=lambda r: (-r[k], -r["eff"]))[:top]
        if as_data:
            for i, r in enumerate(rs, 1):
                ab = r["name"].split(" ")[0][0] + ". " + " ".join(r["name"].split(" ")[1:])
                if i == 1:
                    print(f"{cat}|1|{ab}|{r['name']}|{tname(r['team'])}|{r[k]}|{r['img'] or ''}|{tlogo(r['team'])}")
                else:
                    print(f"{cat}|{i}|{ab}|{tname(r['team'])}|{r[k]}")
        else:
            print(f"{cat}: " + " · ".join(f"{r['name']} ({tname(r['team'])}) {r[k]}" for r in rs))

elif cmd == "standings":
    tab = {}
    for g in G:
        if group and (g.get("pool") or "").strip().upper()[-1:] != group.upper():
            continue
        h, v = g["teams"]
        for me, ot in ((h, v), (v, h)):
            r = tab.setdefault(me["id"], {"name": me["name"], "pool": g.get("pool"), "pj": 0, "w": 0, "l": 0, "pts": 0, "dif": 0})
            r["pj"] += 1; r["dif"] += me["score"] - ot["score"]
            if me["score"] > ot["score"]:
                r["w"] += 1; r["pts"] += 2
            else:
                r["l"] += 1; r["pts"] += 1
    rows = sorted(tab.values(), key=lambda r: (-r["pts"], -r["dif"]))
    if as_data:
        print(json.dumps([[r["name"], r["dif"], r["pts"]] for r in rows], ensure_ascii=False))
    else:
        for i, r in enumerate(rows, 1):
            print(f"{i}. {r['name']} {r['pool'] or ''} PJ {r['pj']} G {r['w']} P {r['l']} PTS {r['pts']} DIF {r['dif']:+d}")

elif cmd == "player":
    want = " ".join(rest).lower()
    norm = lambda x: "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn")
    for g in G:
        for p in g["players"]:
            if norm(want) in norm(p["name"]) and p.get("played"):
                print(f"J{g['j']} {g['date'][:10]} {p['name']} ({tname(p['team'])}) {'TIT' if p.get('starter') else 'BANCA'} "
                      f"{round(p.get('min', 0))} MIN · {p.get('pts', 0)} PTS {p.get('reb', 0)} REB {p.get('ast', 0)} AST EFF {p.get('eff', 0)}")
else:
    sys.exit(__doc__)
