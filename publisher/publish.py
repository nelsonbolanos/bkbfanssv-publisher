#!/usr/bin/env python3
"""Publish an Instagram carousel (with per-slide user tags) via the Instagram API with Instagram Login.

usage:
  python3 publish.py manifest.json            # real post
  python3 publish.py manifest.json --dry-run  # print payloads, call nothing

env (never put the token in a file or a URL):
  IG_TOKEN        Instagram User access token (GitHub secret)
  IG_USER_ID      Instagram account id (17841478415958357 for @bkbfanssv)
  IMAGE_BASE_URL  public base URL of the repo (GitHub Pages); slide "file" paths are relative to it
  IG_API_VERSION  optional, default v23.0

manifest.json:
{"caption": "...", "slides": [{"file": "u16m-01.jpg", "tags": [{"username": "goriladeportess", "x": 0.31, "y": 0.22}]}, ...],
 "collaborators": ["club"]}   # optional Collab invite on the carousel (parent container only), max 3, see collab.py
Rules enforced here: 2-10 slides, JPEG only, tag x/y within 0..1, max 20 tags per slide, no collaborators on a slide.
If Instagram rejects the collaborators (any 4xx on the container request that carried them), the container is
retried once without them and published.json records "collaborators_dropped".

Reels: a manifest with "kind": "reel" is published as a reel (video with its music inside the MP4); format and
rules in publisher/reel.py. Same READY / published.json flow as a carousel.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collab, reel

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
    if "collaborators" in m:
        err = collab.check(m["collaborators"])
        if err:
            sys.exit("collaborators:\n  " + "\n  ".join(err))
    for s in slides:
        if "collaborators" in s:
            sys.exit(f"{s['file']}: collaborators go on the carousel (manifest top level), not on a slide")
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


RATE_CODES = ('"code":4,', '"code":17,', '"code":32,', '"code":613,', '"error_subcode":2207051')
RATE_WAITS = [60, 120, 240, 480, 600]   # up to ~25 min of back-off per request (Oct 16 2026: hit code 4 with stories)


def rate_limited(body):
    """Instagram/Meta rate limit. The request was rejected, nothing happened, so retrying is safe."""
    b = (body or "").replace(" ", "")
    return "requestlimit" in b.lower() or any(c in b for c in RATE_CODES)


CALLS = 0   # API calls made by this run (printed at the end; the app limit is ~200/hour in development mode)


def call(method, path, data=None, soft=False):
    """Token goes in the Authorization header, never the URL.
    soft=True: a non-rate-limit HTTP error returns {"_error": body} instead of stopping the run."""
    global CALLS
    url = f"{BASE}/{path}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = None
    if method == "POST":
        body = urllib.parse.urlencode(data or {}).encode()
    elif data:
        url += "?" + urllib.parse.urlencode(data)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    attempt = rate = 0
    while True:
        CALLS += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if rate_limited(msg) and rate < len(RATE_WAITS):
                print(f"  rate limit, waiting {RATE_WAITS[rate]} s"); time.sleep(RATE_WAITS[rate]); rate += 1; continue
            if e.code >= 500 and attempt < 3 and "media_publish" not in path:
                attempt += 1; time.sleep(3 * attempt); continue
            if soft:
                return {"_error": f"HTTP {e.code}: {msg}"}
            sys.exit(f"HTTP {e.code} on {method} {path}: {msg}")
        except urllib.error.URLError as e:
            if attempt < 3 and "media_publish" not in path:
                attempt += 1; time.sleep(3 * attempt); continue
            sys.exit(f"network error on {path}: {e}")


def http_code(err):
    """HTTP status of a soft call() error ("HTTP 400: ..."), 0 when unknown."""
    try:
        return int(err.split(":", 1)[0].split()[1])
    except (IndexError, ValueError):
        return 0


COLLAB_NOTE = ""   # set when Instagram rejected the collaborators and the container went out without them


def create_container(p):
    """POST /{ig-user-id}/media for a parent/reel container. With collaborators: a 4xx (not a rate limit) is retried
    once without them. Returns call()'s dict ({"_error": ...} only when soft errors are left to the caller)."""
    global COLLAB_NOTE
    r = call("POST", f"{UID}/media", p, soft=True)
    if "_error" in r and collab.should_retry(p, http_code(r["_error"])) and not rate_limited(r["_error"]):
        COLLAB_NOTE = collab.warn(r["_error"])
        p.pop("collaborators")
        r = call("POST", f"{UID}/media", p, soft=True)
    return r


def collab_log(p):
    """published.json fields about collaborators (empty when the manifest had none)."""
    if COLLAB_NOTE:
        return {"collaborators": [], "collaborators_dropped": COLLAB_NOTE}
    if "collaborators" in p:
        return {"collaborators": json.loads(p["collaborators"])}
    return {}


def wait_finished(cid, tries=30, first_wait=0):
    if first_wait:
        time.sleep(first_wait)   # the carousel container is never ready at once: polling right away wastes a call
    for _ in range(tries):
        r = call("GET", cid, {"fields": "status_code"})
        st = r.get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"container {cid} status {st}: {r}")
        time.sleep(10)   # was 4 s: fewer status calls, the hourly API limit is shared by all posts
    sys.exit(f"container {cid} not FINISHED after waiting")


def wait_public(url, tries=24):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                if r.status == 200:
                    return
        except urllib.error.HTTPError:
            pass
        time.sleep(10)
    sys.exit(f"image not publicly reachable: {url}")


LOG = os.path.join(os.path.dirname(os.path.abspath(args[0])), "published.json")
if os.path.exists(LOG) and not DRY:
    sys.exit(f"already published: {open(LOG).read()} (delete published.json only if you are sure it is not on Instagram)")


def publish_reel(m):
    # repo root: posts/<slug>/manifest.json -> ../.. ; media paths in the manifest are relative to it (as for slides)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(args[0]))))
    err = reel.check_manifest(m, root)
    if err:
        sys.exit("reel manifest:\n  " + "\n  ".join(err))
    video = os.path.join(root, m["video"])
    info, size = reel.probe(video), os.path.getsize(video)
    err = reel.check_media(info, size)
    if err:
        sys.exit(f"{m['video']}:\n  " + "\n  ".join(err))
    p = reel.payload(m, IMG or "(IMAGE_BASE_URL)")
    if DRY:
        print(f"DRY RUN reel. account={UID or '(IG_USER_ID unset)'} api={VER}")
        print("video:", reel.summary(info, size))
        print("POST /{ig-user-id}/media", json.dumps({k: v for k, v in p.items() if k != "caption"}, ensure_ascii=False))
        print("then: wait status_code FINISHED, POST /{ig-user-id}/media_publish creation_id=<container>")
        print("published.json:", "exists (a real run would stop)" if os.path.exists(LOG) else "none yet")
        print("caption:\n" + m["caption"])
        sys.exit(0)
    if not (TOKEN and UID and IMG):
        sys.exit("IG_TOKEN, IG_USER_ID and IMAGE_BASE_URL must be set")
    print("video:", reel.summary(info, size))
    wait_public(p["video_url"])
    if "cover_url" in p:
        wait_public(p["cover_url"])
    print("reel media publicly reachable")
    r = create_container(p)
    if "_error" in r:
        sys.exit(f"reel container failed: {r['_error']}")
    cid = r["id"]
    print("reel container created" + (f", collaborators invited: {p['collaborators']}" if "collaborators" in p else "")
          + ", waiting for Instagram to process the video")
    wait_finished(cid, tries=60, first_wait=20)   # video processing: up to ~10 min, polled every 10 s
    media = call("POST", f"{UID}/media_publish", {"creation_id": cid})["id"]
    print("published reel media id:", media)
    json.dump({"media_id": media, "kind": "reel", "at": time.strftime("%Y-%m-%d %H:%M"), "tags": len(m.get("tags", [])),
               **collab_log(p)}, open(LOG, "w"), indent=1)
    if COLLAB_NOTE:
        print(f"SUMMARY: reel published WITHOUT collaborators ({COLLAB_NOTE})")
    print(f"API calls used: {CALLS}")
    sys.exit(0)


if reel.is_reel(manifest):
    publish_reel(manifest)
validate(manifest)
children_payloads = []
for s in manifest["slides"]:
    p = {"image_url": f"{IMG}/{s['file']}", "is_carousel_item": "true"}
    tags = [{"username": t["username"].lstrip("@"), "x": round(t["x"], 4), "y": round(t["y"], 4)}
            for t in s.get("tags", [])]
    if tags:
        p["user_tags"] = json.dumps(tags)
    children_payloads.append(p)   # never collaborators here: Instagram only takes them on the carousel container
COLLABS = collab.names(manifest)

if DRY:
    print(f"DRY RUN. account={UID or '(IG_USER_ID unset)'} api={VER}")
    for i, p in enumerate(children_payloads, 1):
        print(f"slide {i}:", json.dumps(p, ensure_ascii=False))
    print("carousel:", json.dumps(collab.add({"media_type": "CAROUSEL", "children": "<slide ids>"}, COLLABS),
                                  ensure_ascii=False))
    print("caption:\n" + manifest["caption"])
    sys.exit(0)

if not (TOKEN and UID and IMG):
    sys.exit("IG_TOKEN, IG_USER_ID and IMAGE_BASE_URL must be set")

for p in children_payloads:
    wait_public(p["image_url"])
print("all slides publicly reachable")
# Oct 26 2026 (Nelson: fix the 2 biggest API consumers): image containers are ready almost at once, so the slides
# are NOT polled one by one any more (that was ~1 status call per slide). The carousel container is created right
# after; only if Instagram rejects it (a slide not ready yet) the slides are polled as before and it is retried once.
ids = []
for i, p in enumerate(children_payloads, 1):
    ids.append(call("POST", f"{UID}/media", p)["id"])
    print(f"slide {i}/{len(children_payloads)} created")
time.sleep(5)
parent_data = collab.add({"media_type": "CAROUSEL", "children": ",".join(ids), "caption": manifest["caption"]}, COLLABS)
r = create_container(parent_data)   # a collaborators rejection is retried once without them in there
if "_error" in r:
    print(f"carousel container rejected ({r['_error'][:300]}); checking each slide and retrying once")
    for i, cid in enumerate(ids, 1):
        wait_finished(cid)
        print(f"slide {i}/{len(ids)} ready")
    r = call("POST", f"{UID}/media", parent_data)
parent = r["id"]
wait_finished(parent, first_wait=10)
media = call("POST", f"{UID}/media_publish", {"creation_id": parent})["id"]
print("published media id:", media)
json.dump({"media_id": media, "at": time.strftime("%Y-%m-%d %H:%M"), "tags": sum(len(s.get("tags", [])) for s in manifest["slides"]),
           **collab_log(parent_data)}, open(LOG, "w"), indent=1)
if COLLAB_NOTE:
    print(f"SUMMARY: carousel published WITHOUT collaborators ({COLLAB_NOTE})")
elif "collaborators" in parent_data:
    print(f"collaborators invited: {parent_data['collaborators']} (each club must accept in the app)")
# (the permalink GET after publishing was dropped Oct 26 2026 to save a call per carousel; media_id is enough)
print(f"API calls used: {CALLS}")
