#!/usr/bin/env python3
"""Split one league's weekly carousel into one carousel per group (Instagram API max = 10 slides).

usage: python3 split_groups.py <league_dir> [groups.json]
  league_dir has games.csv + meta.json (carousel-playbook format). groups.json maps "16M" -> {"A": [...], "B": [...]}.
  Writes <league_dir>-a, <league_dir>-b ... (games.csv + meta.json + img/ link), one per group, each with:
    cover stage "GRUPO A", game slide tag "GRUPO A · JORNADA N · FINAL", standings of that group only, slug <slug>-a.
  Standings: meta.json "standings" should list ALL teams of the league ([name, dif, pts]); teams missing from it
  are filled from this week's games (2 pts win, 1 pt loss). Sorted by pts, then dif.
  If the league code is not in groups.json it does nothing and prints NOGROUPS (then: if cover + games + standings
  > 10 slides, split the games in two posts "PARTE 1/2" by hand or ask Nelson).
Team matching is accent/case-insensitive, ignores the "16M" suffix, and accepts prefixes both ways
(e.g. "COL. SAN FCO DE ASÍS 16M" matches "COL. SAN FRANCISCO DE ASÍS" via ALIASES).
"""
import sys, os, re, json, unicodedata, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.abspath(sys.argv[1].rstrip("/"))
groups_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "groups.json")
G = json.load(open(groups_path, encoding="utf-8"))
meta = json.load(open(os.path.join(src, "meta.json"), encoding="utf-8"))
code = meta["code"]
ALIASES = {"col. san francisco de asis": "col. san fco de asis", "aguilas b.c.": "aguilas"}


def norm(x):
    x = "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn").strip()
    x = re.sub(r"\s+\d\d\s?[fm]$", "", x)
    return ALIASES.get(x, x)


if code not in G:
    print("NOGROUPS", code); sys.exit(0)
groups = {g: [norm(t) for t in teams] for g, teams in G[code].items() if not g.startswith("_")}


def group_of(team):
    t = norm(team)
    best = None
    for g, teams in groups.items():
        for gt in teams:
            if t == gt or t.startswith(gt + " ") or gt.startswith(t + " "):
                if best is None or len(gt) > best[1]:
                    best = (g, len(gt))
    return best[0] if best else None


rows = [l.rstrip("\n").split("|") for l in open(os.path.join(src, "games.csv"), encoding="utf-8") if l.strip()]
stand = {norm(n): [n, d, p] for n, d, p in meta.get("standings", [])}
unknown = set()
by_group = {g: [] for g in groups}
for r in rows:
    gh, ga = group_of(r[2]), group_of(r[3])
    if not gh: unknown.add(r[2])
    if not ga: unknown.add(r[3])
    if gh != ga and gh and ga:
        print(f"WARNING cross-group game {r[2]} vs {r[3]}: put in group {gh}")
    by_group.setdefault(gh or ga or "?", []).append(r)
    hs, as_ = [int(x) for x in r[4].split("-")]
    for team, f, a in ((r[2], hs, as_), (r[3], as_, hs)):
        k = norm(team)
        if k not in stand:  # fill from this week's games
            stand.setdefault("_new_" + k, [team, 0, 0])
            e = stand["_new_" + k]; e[1] += f - a; e[2] += 2 if f > a else 1
if unknown:
    sys.exit("TEAMS NOT IN ANY GROUP (fix groups.json, ask Nelson): " + ", ".join(sorted(unknown)))

slug = meta.get("slug", f"{meta['cat'].lower()}{code[-1].lower()}-j{meta.get('jornada', '')}")
for g, grows in by_group.items():
    if not grows:
        continue
    dst = f"{src}-{g.lower()}"
    os.makedirs(dst, exist_ok=True)
    for sub in ("img",):
        if os.path.isdir(os.path.join(src, sub)) and not os.path.exists(os.path.join(dst, sub)):
            shutil.copytree(os.path.join(src, sub), os.path.join(dst, sub))
    with open(os.path.join(dst, "games.csv"), "w", encoding="utf-8") as f:
        for r in grows:
            r = (r + [""] * 15)[:15]
            if not r[14]:
                r[14] = f"GRUPO {g} · JORNADA {meta.get('jornada', '')} · FINAL"
            f.write("|".join(r) + "\n")
    st = [v for k, v in stand.items() if group_of(v[0]) == g]
    st.sort(key=lambda x: (-x[2], -x[1]))
    m = dict(meta)
    m.update({"stage": f"GRUPO {g}", "slug": f"{slug}-{g.lower()}", "teams": len(groups[g]),
              "standings": st[:10], "standings_title": f"GRUPO {g} · JORNADA {meta.get('jornada', '')}"})
    json.dump(m, open(os.path.join(dst, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{dst}: {len(grows)} games -> {len(grows) + 2} slides, standings {len(st)} teams")
