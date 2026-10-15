#!/usr/bin/env python3
"""Publish bkbfanssv leader stories (+ Dream Team) to Instagram via the Instagram API with Instagram Login,
with the team and player mentions set by the API.

usage:
  python3 publish_story.py out/u18f out/u18m            # real publish, women first (order = argument order)
  python3 publish_story.py out/u18f out/u18m --dry-run  # print what would be published, call nothing
  python3 publish_story.py out/u18m --only 01,08        # just some stories

Each folder holds NN-<cat>.mp4 plus tags.json written by build_leaders.py / build_dreamteam.py:
  {"01-points.mp4": {"handles": ["@team", ...], "players": ["@player"], ...}, "08-dreamteam.mp4": {...}}
Tags = team handles + player handles (confirmed only; they come from handles.md / the photo library).

env (never put the token in a file or a URL):
  IG_TOKEN        Instagram User access token (secret)
  IG_USER_ID      17841478415958357 (@bkbfanssv)
  MEDIA_BASE_URL  public base URL of the repo files (GitHub Pages), e.g. https://nelsonbolanos.github.io/bkbfanssv-publisher
                  The story video is <base>/<folder>/<file>. REQUIRED: Instagram Login stories reject the resumable
                  upload ("The parameter video_url is required", tested Oct 15 2026).
  IG_API_VERSION  optional, default v23.0

Safety:
  - published.json in each folder records what went out; reruns skip those files (no duplicate stories).
  - If creating a container fails because of a tag (e.g. a private account), it is recreated once WITHOUT
    tags (nothing was published yet, so that is safe) and the story is reported as "published without tags".
  - A container that reaches media_publish is never retried blindly.
"""
import json, os, sys, time, glob, urllib.parse, urllib.request, urllib.error

DRY = "--dry-run" in sys.argv
ONLY = None
argv = sys.argv[1:]
if "--only" in argv:
    i = argv.index("--only"); ONLY = set(argv[i + 1].split(",")); del argv[i:i + 2]
dirs = [a for a in argv if not a.startswith("--")]
if not dirs:
    sys.exit(__doc__)

VER = os.environ.get("IG_API_VERSION", "v23.0")
BASE = f"https://graph.instagram.com/{VER}"
UID = os.environ.get("IG_USER_ID", "")
TOKEN = os.environ.get("IG_TOKEN", "")
MEDIA = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")


class ApiError(Exception):
    def __init__(self, code, body): super().__init__(f"HTTP {code}: {body}"); self.code, self.body = code, body


def call(method, path, data=None, url=None, headers=None, raw=None):
    url = url or f"{BASE}/{path}"
    h = {"Authorization": f"Bearer {TOKEN}"}; h.update(headers or {})
    body = raw
    if method == "POST" and raw is None:
        body = urllib.parse.urlencode(data or {}).encode()
    elif method == "GET" and data:
        url += "?" + urllib.parse.urlencode(data)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < 3 and path != "media_publish":
                time.sleep(3 * (attempt + 1)); continue
            raise ApiError(e.code, msg)
        except urllib.error.URLError as e:
            if attempt < 3 and path != "media_publish":
                time.sleep(3 * (attempt + 1)); continue
            raise ApiError(0, str(e))


def wait_finished(cid, tries=60):
    for _ in range(tries):
        r = call("GET", cid, {"fields": "status_code,status"})
        st = r.get("status_code")
        if st == "FINISHED": return
        if st in ("ERROR", "EXPIRED"): raise ApiError(0, f"container {cid} {st}: {r}")
        time.sleep(5)
    raise ApiError(0, f"container {cid} not FINISHED after {tries * 5}s")


def tag_list(t):
    out = []
    for h in t.get("handles", []) + t.get("players", []):
        u = h.lstrip("@").lower()
        if u and u not in out: out.append(u)
    return out[:20]


def wait_public(url, tries=24):
    """GitHub Pages can take a minute or two to serve a new file; Instagram fails if it can't download it."""
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                if r.status == 200:
                    print(f"  public OK ({r.headers.get('Content-Type')}): {url}"); return
        except urllib.error.HTTPError:
            pass
        time.sleep(10)
    raise ApiError(0, f"video not publicly reachable: {url}")


def create(folder, mp4, tags):
    p = {"media_type": "STORIES"}
    if tags: p["user_tags"] = json.dumps([{"username": u} for u in tags])
    if MEDIA:
        p["video_url"] = f"{MEDIA}/{mp4.lstrip('./')}"
        wait_public(p["video_url"])
        return call("POST", f"{UID}/media", p)["id"]
    p["upload_type"] = "resumable"
    r = call("POST", f"{UID}/media", p)
    size = os.path.getsize(mp4)
    call("POST", None, url=r["uri"], raw=open(mp4, "rb").read(),
         headers={"Authorization": f"OAuth {TOKEN}", "offset": "0", "file_size": str(size)})
    return r["id"]


if not DRY and not (TOKEN and UID and MEDIA):
    sys.exit("IG_TOKEN, IG_USER_ID and MEDIA_BASE_URL must be set")

report = []
for folder in dirs:
    tp = os.path.join(folder, "tags.json")
    tags_all = json.load(open(tp, encoding="utf-8")) if os.path.exists(tp) else {}
    logp = os.path.join(folder, "published.json")
    done = json.load(open(logp)) if os.path.exists(logp) else {}
    files = sorted(f for f in glob.glob(os.path.join(folder, "[0-9][0-9]-*.mp4")) if ".silent" not in f and ".tmp" not in f)
    for mp4 in files:
        name = os.path.basename(mp4)
        if ONLY and name[:2] not in ONLY: continue
        if name in done:
            print(f"skip {folder}/{name} (already published {done[name]['at']})"); continue
        tags = tag_list(tags_all.get(name, {}))
        if DRY:
            print(f"DRY {folder}/{name}  {os.path.getsize(mp4) // 1024} KB  tags={['@' + t for t in tags]}"
                  f"  via={'video_url' if MEDIA else 'resumable upload'}")
            continue
        note = ""
        try:
            cid = create(folder, mp4, tags); wait_finished(cid)
        except ApiError as e:
            if not tags: raise
            if "video_url" in e.body or e.code >= 500 and "user" not in e.body.lower():
                raise  # not a tag problem: stop, nothing was published
            print(f"{name}: container failed with tags ({e}); retrying without tags")
            note = f"published WITHOUT tags (tag error: {str(e)[:200]})"
            cid = create(folder, mp4, []); wait_finished(cid)
        mid = call("POST", f"{UID}/media_publish", {"creation_id": cid})["id"]
        done[name] = {"media_id": mid, "tags": tags, "note": note, "at": time.strftime("%Y-%m-%d %H:%M")}
        json.dump(done, open(logp, "w"), indent=1)
        report.append((folder, name, tags, note))
        print(f"published {folder}/{name} media={mid} tags={len(tags)} {note}")
        time.sleep(3)

if report:
    print("\nSUMMARY")
    for f, n, t, note in report: print(f"  {f}/{n}: {len(t)} tags {note}")
