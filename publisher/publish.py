#!/usr/bin/env python3
"""Publish an Instagram carousel (with per-slide user tags) via the Instagram API with Instagram Login.

usage:
  python3 publish.py manifest.json            # real post
  python3 publish.py manifest.json --dry-run  # print payloads, call nothing

env (never put the token in a file or a URL):
  IG_TOKEN        Instagram User access token (GitHub secret)
  IG_USER_ID      Instagram account id (17841478415958357 for @bkbfanssv)
  IMAGE_BASE_URL  public base URL where the JPEGs are hosted, no trailing slash
  IG_API_VERSION  optional, default v23.0

manifest.json:
{"caption": "...", "slides": [{"file": "u16m-01.jpg", "tags": [{"username": "goriladeportess", "x": 0.31, "y": 0.22}]}, ...]}
Rules enforced here: 2-10 slides, JPEG only, tag x/y within 0..1, max 20 tags per slide.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

DRY = "--dry-run" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)

manifest = json.load(open(args[0], encoding="utf-8"))
VER = os.environ.get("IG_API_VERSION", "v23.0")
BASE = f"https://graph.instagram.com/{VER}"
UID = os.environ.get("IG_USER_ID", "")
IMG = os.environ.get("IMAGE_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("IG_TOKEN", "")


def validate(m):
    slides = m["slides"]
    if not 2 <= len(slides) <= 10:
        sys.exit(f"carousel needs 2-10 slides, got {len(slides)}")
    if not m.get("caption", "").strip():
        sys.exit("empty caption")
    for s in slides:
        if not s["file"].lower().endswith((".jpg", ".jpeg")):
            sys.exit(f"{s['file']}: Instagram needs JPEG")
        tags = s.get("tags", [])
        if len(tags) > 20:
            sys.exit(f"{s['file']}: more than 20 tags")
        seen = set()
        for t in tags:
            if not (0 <= t["x"] <= 1 and 0 <= t["y"] <= 1):
                sys.exit(f"{s['file']}: tag {t['username']} outside 0..1")
            u = t["username"].lstrip("@").lower()
            if u in seen:
                sys.exit(f"{s['file']}: duplicate tag {u}")
            seen.add(u)


def call(method, path, data=None):
    """Token goes in the Authorization header, never the URL."""
    url = f"{BASE}/{path}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = None
    if method == "POST":
        body = urllib.parse.urlencode(data or {}).encode()
    elif data:
        url += "?" + urllib.parse.urlencode(data)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < 3 and "media_publish" not in path:
                time.sleep(3 * (attempt + 1)); continue
            sys.exit(f"HTTP {e.code} on {method} {path}: {msg}")
        except urllib.error.URLError as e:
            if attempt < 3 and "media_publish" not in path:
                time.sleep(3 * (attempt + 1)); continue
            sys.exit(f"network error on {path}: {e}")


def wait_finished(cid, tries=30):
    for _ in range(tries):
        r = call("GET", cid, {"fields": "status_code"})
        st = r.get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"container {cid} status {st}: {r}")
        time.sleep(4)
    sys.exit(f"container {cid} not FINISHED after waiting")


validate(manifest)
children_payloads = []
for s in manifest["slides"]:
    p = {"image_url": f"{IMG}/{s['file']}", "is_carousel_item": "true"}
    tags = [{"username": t["username"].lstrip("@"), "x": round(t["x"], 4), "y": round(t["y"], 4)}
            for t in s.get("tags", [])]
    if tags:
        p["user_tags"] = json.dumps(tags)
    children_payloads.append(p)

if DRY:
    print(f"DRY RUN. account={UID or '(IG_USER_ID unset)'} api={VER}")
    for i, p in enumerate(children_payloads, 1):
        print(f"slide {i}:", json.dumps(p, ensure_ascii=False))
    print("caption:\n" + manifest["caption"])
    sys.exit(0)

if not (TOKEN and UID and IMG):
    sys.exit("IG_TOKEN, IG_USER_ID and IMAGE_BASE_URL must be set")

ids = []
for i, p in enumerate(children_payloads, 1):
    cid = call("POST", f"{UID}/media", p)["id"]
    wait_finished(cid)
    ids.append(cid)
    print(f"slide {i}/{len(children_payloads)} ready")

parent = call("POST", f"{UID}/media", {
    "media_type": "CAROUSEL", "children": ",".join(ids), "caption": manifest["caption"]})["id"]
wait_finished(parent)
media = call("POST", f"{UID}/media_publish", {"creation_id": parent})["id"]
print("published media id:", media)
try:
    pl = call("GET", media, {"fields": "permalink"})
    print("permalink:", pl.get("permalink"))
except SystemExit:
    pass
