#!/usr/bin/env python3
"""Compute Instagram tag coordinates from the rendered slide HTML and build manifest.json.

gen.py (patched with patch_gen.py) marks taggable elements:
  data-team="MASFERRER 16M"                      team names (game slides, standings rows)
  data-player="Jonathan Rodríguez|COJUTE 16M"    Jugador del Partido photo (only real photos)

usage: python3 tag_export.py <league_out_dir> <slug> <caption_file> <manifest_out> [--preview <dir>]
  league_out_dir has 01.html .. NN.html; slides are published as images/<slug>/<slug>-NN.jpg
  --preview writes NN-tags.png with red dots + usernames on top of each slide, to LOOK at before posting.
Coordinates = element centre / 1080x1350, clamped to 0.02..0.98. Same account twice on a slide keeps
the first element only. Player handles: handles.json "players", then the photo library index.json
(<scratchpad>/player-photos/index.json or PLAYER_LIB env) for confirmed handles.
"""
import sys, os, re, json, unicodedata, asyncio
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(os.path.join(HERE, "handles.json"), encoding="utf-8"))
W, HT = 1080, 1350
LIB = []
for p in [os.environ.get("PLAYER_LIB", ""), os.path.join(os.getcwd(), "player-photos", "index.json")]:
    if p and os.path.exists(p):
        LIB = json.load(open(p, encoding="utf-8")); break


def norm(x):
    return "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn").strip()


def base_team(t):
    return re.sub(r"\s+\d\d\s?[FM]$", "", t.strip())


def team_handles(team, code):
    t = norm(base_team(team))
    for k, byc in H["by_category"].items():
        if t.startswith(k) and code[:2] in byc:
            return byc[code[:2]]
    for k in sorted(H["teams"], key=len, reverse=True):
        if t.startswith(k):
            return H["teams"][k]
    return []


def player_handle(name, team, code):
    h = H["players"].get(f"{norm(name)}|{norm(base_team(team))}|{code}")
    if h:
        return h
    t = norm(base_team(team)); want = norm(name).split()
    for e in LIB:
        et = norm(e.get("team", ""))
        if e.get("cat") != code or not (t == et or t.startswith(et + " ")):
            continue
        toks = norm(e["name"]).split()
        if want and want[-1] in toks and toks[0][:1] == want[0][:1]:
            hd = e.get("handle") or ""
            return hd.lstrip("@") if hd.startswith("@") else None
    return None


def clamp(v):
    return max(0.02, min(0.98, v))


async def main(out_dir, slug, caption_file, manifest_out, preview=None):
    files = sorted(f for f in os.listdir(out_dir) if re.fullmatch(r"\d\d\.html", f))
    slides, missing = [], set()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": W, "height": HT})
        for f in files:
            n = f[:2]
            await pg.goto("file://" + os.path.abspath(os.path.join(out_dir, f)))
            await pg.evaluate("document.fonts.ready")
            els = await pg.evaluate("""() => [...document.querySelectorAll('[data-team],[data-player]')].map(e => {
                const r = e.getBoundingClientRect();
                return {team: e.dataset.team || null, player: e.dataset.player || null,
                        cx: r.x + r.width / 2, cy: r.y + r.height / 2};
            })""")
            tags, used = [], set()
            for e in els:
                label = e["team"] or e["player"].split("|")[1]
                m = re.search(r"(\d\d[FM])\s*$", label.strip())
                code = m.group(1) if m else ""
                if e["team"]:
                    hs = team_handles(e["team"], code)
                    if not hs:
                        missing.add(e["team"])
                else:
                    name, team = e["player"].split("|")
                    h = player_handle(name, team, code)
                    hs = [h] if h else []
                for i, h in enumerate(hs):
                    if h in used:
                        continue
                    used.add(h)
                    tags.append({"username": h, "x": round(clamp(e["cx"] / W), 4), "y": round(clamp((e["cy"] + i * 40) / HT), 4)})
            slides.append({"file": f"images/{slug}/{slug}-{n}.jpg", "tags": tags})
            if preview:
                os.makedirs(preview, exist_ok=True)
                js = "tags => { for (const t of tags) { const d = document.createElement('div'); d.textContent = '● @' + t.username;" \
                     " d.style.cssText = `position:fixed;left:${t.x*1080}px;top:${t.y*1350}px;transform:translate(-8px,-50%);" \
                     "background:#e00;color:#fff;font:600 22px sans-serif;padding:4px 10px;border-radius:8px;z-index:99`;" \
                     " document.body.appendChild(d);} }"
                await pg.evaluate(js, tags)
                await pg.screenshot(path=os.path.join(preview, f"{n}-tags.png"))
        await b.close()
    manifest = {"caption": open(caption_file, encoding="utf-8").read().strip(), "slides": slides}
    os.makedirs(os.path.dirname(os.path.abspath(manifest_out)), exist_ok=True)
    json.dump(manifest, open(manifest_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {manifest_out}: {len(slides)} slides, {sum(len(s['tags']) for s in slides)} tags")
    if missing:
        print("NO HANDLE (not tagged):", ", ".join(sorted(missing)))


a = sys.argv[1:]
pv = None
if "--preview" in a:
    i = a.index("--preview"); pv = a[i + 1]; del a[i:i + 2]
asyncio.run(main(*a[:4], preview=pv))
