#!/usr/bin/env python3
"""Split a league carousel into one carousel PER GROUP (Instagram API: max 10 slides per carousel).

usage: python3 split_groups.py <league_dir> [groups.json]
  <league_dir> has games.csv + meta.json (gen.py format). Writes <league_dir>-a, <league_dir>-b, ...
  each with its own games.csv and meta.json (cover says "JORNADA N · GRUPO A", standings = that group only,
  slug <slug>-a). Then render each with gen.py as usual.
Standings: meta["standings_full"] ([[team, dif, pts], ...] for ALL teams, cumulative, e.g. from fesabal Standings)
is filtered per group when present; otherwise standings are computed from this games.csv
(2 pts win, 1 pt loss; rank by pts then dif), listing every group team (0 if not played yet).
A game between two different groups is reported and kept in the home team's group.
Leagues without groups in groups.json are left alone (exit code 3 = no groups, render as one carousel).
"""
import sys, os, re, json, unicodedata, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ld = os.path.abspath(sys.argv[1].rstrip("/"))
G = json.load(open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "groups.json"), encoding="utf-8"))
meta = json.load(open(os.path.join(ld, "meta.json"), encoding="utf-8"))
code = meta["code"]
if code not in G:
    print(f"{code}: no groups defined, keep one carousel"); sys.exit(3)


def norm(x):
    x = "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn")
    x = re.sub(r"\s+\d\d\s?[fm]$", "", re.sub(r"\s+", " ", x.strip()))
    return G.get("aliases", {}).get(x, x)


groups = {g: [norm(t) for t in ts] for g, ts in G[code].items()}


def group_of(team):
    t = norm(team); best = (None, -1)
    for g, ts in groups.items():
        for k in ts:
            if (t == k or t.startswith(k + " ")) and len(k) > best[1]:
                best = (g, len(k))
    return best[0]


rows = [l.rstrip("\n").split("|") for l in open(os.path.join(ld, "games.csv"), encoding="utf-8") if l.strip()]
by = {g: [] for g in groups}
problems = []
for r in rows:
    gh, ga = group_of(r[2]), group_of(r[3])
    if gh is None or ga is None:
        problems.append(f"team not in any group: {r[2] if gh is None else r[3]}")
    if gh and ga and gh != ga:
        problems.append(f"cross-group game kept in group {gh}: {r[2]} vs {r[3]}")
    by[gh or ga or sorted(groups)[0]].append(r)

slug = meta.get("slug", f"{meta['cat'].lower()}{code[-1].lower()}-j{meta.get('jornada', 1)}")
for g, grows in by.items():
    if not grows:
        print(f"group {g}: no games, skipped"); continue
    names = {}
    for r in grows:
        for t in (r[2], r[3]):
            names[norm(t)] = t
    if meta.get("standings_full"):
        st = [s for s in meta["standings_full"] if group_of(s[0]) == g]
    else:
        tab = {}
        for raw in G[code][g]:
            k = norm(raw)
            full = next((v for n, v in names.items() if n == k or n.startswith(k + " ")), f"{raw} {code}")
            tab[full] = [0, 0]
        for r in grows:
            hs, as_ = (int(x) for x in r[4].split("-"))
            for team, me, other in ((r[2], hs, as_), (r[3], as_, hs)):
                key = next((k for k in tab if norm(k) == norm(team)), team)
                tab.setdefault(key, [0, 0])
                tab[key][0] += me - other
                tab[key][1] += 2 if me > other else 1
        st = sorted(([k, v[0], v[1]] for k, v in tab.items()), key=lambda s: (-s[2], -s[1]))
    m = dict(meta)
    m.pop("standings_full", None)
    m.update({"stage": f"JORNADA {meta.get('jornada', '')} · GRUPO {g}", "stage_size": 80,
              "standings": st, "standings_title": f"GRUPO {g} · JORNADA {meta.get('jornada', '')}",
              "teams": len(G[code][g]), "slug": f"{slug}-{g.lower()}", "group": g})
    out = f"{ld}-{g.lower()}"
    os.makedirs(out, exist_ok=True)
    if os.path.isdir(os.path.join(ld, "img")) and not os.path.exists(os.path.join(out, "img")):
        shutil.copytree(os.path.join(ld, "img"), os.path.join(out, "img"))
    open(os.path.join(out, "games.csv"), "w", encoding="utf-8").write("".join("|".join(r) + "\n" for r in grows))
    json.dump(m, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"group {g}: {len(grows)} games -> {out} ({len(grows) + 2} slides), standings {len(st)} teams")
for p in problems:
    print("WARNING:", p)
