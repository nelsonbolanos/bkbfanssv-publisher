#!/usr/bin/env python3
"""List what the scheduled publish runs should post (used by publish-story / publish-carousel on schedule).

usage:
  python3 publisher/pending.py stories     # -> "stories/2026-10-15/u18f stories/2026-10-15/u18m" (women first)
  python3 publisher/pending.py carousels   # -> "posts/u16m-j1/manifest.json ..."

A batch is published by the schedule only when someone marked it ready:
  stories/<date>/<league>/READY     (all NN-*.mp4 + tags.json already committed)
  posts/<slug>/READY                (manifest.json + images/<slug>/*.jpg already committed; first line = YYYY-MM-DD)
and it still has something missing from published.json. Batches older than MAX_AGE days are ignored (a late
story is worse than no story); they stay for a manual run until cleanup-media removes them.
"""
import datetime, glob, json, os, re, sys

MAX_AGE = 2
today = datetime.datetime.utcnow().date()


def fresh(day):
    return today - datetime.timedelta(days=MAX_AGE) <= day <= today + datetime.timedelta(days=1)


def stories():
    out = []
    for ready in glob.glob("stories/*/*/READY"):
        folder = os.path.dirname(ready)
        d = folder.split("/")[1]
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", d) or not fresh(datetime.date.fromisoformat(d)):
            print(f"skip {folder}: date {d} too old or invalid", file=sys.stderr); continue
        mp4s = {os.path.basename(f) for f in glob.glob(f"{folder}/[0-9][0-9]-*.mp4")
                if ".silent" not in f and ".tmp" not in f}
        pub = os.path.join(folder, "published.json")
        done = set(json.load(open(pub))) if os.path.exists(pub) else set()
        if mp4s - done:
            out.append(folder)
    # date, then league, then women before men (u18f before u18m, lmbf before lmb)
    def key(f):
        lg = f.split("/")[2]
        women = lg.endswith("f")
        base = lg[:-1] if lg[-1:] in ("f", "m") else lg   # u18f/u18m -> u18, lmbf/lmb -> lmb
        return (f.split("/")[1], base, not women, f)
    return sorted(out, key=key)


def carousels():
    out = []
    for ready in sorted(glob.glob("posts/*/READY")):
        folder = os.path.dirname(ready)
        first = (open(ready).read().strip().splitlines() or [""])[0].strip()
        try:
            day = datetime.date.fromisoformat(first)
        except ValueError:
            print(f"skip {folder}: READY must start with YYYY-MM-DD", file=sys.stderr); continue
        if not fresh(day):
            print(f"skip {folder}: ready date {day} too old", file=sys.stderr); continue
        if os.path.exists(f"{folder}/manifest.json") and not os.path.exists(f"{folder}/published.json"):
            out.append(f"{folder}/manifest.json")
    return out


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in ("stories", "carousels"):
        sys.exit(__doc__)
    print(" ".join(stories() if kind == "stories" else carousels()))
