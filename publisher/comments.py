"""Dump all comments (and replies) of one post, encrypted like insights.py (public repo: nothing readable is printed).
  python3 publisher/comments.py <media_id> --out comments.enc.json   (decrypt on the Mac with studio stats/insights_pull.decrypt)"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insights import get, encrypt, TOKEN  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("media"); ap.add_argument("--out", default="comments.enc.json")
a = ap.parse_args()
if not TOKEN:
    sys.exit("IG_TOKEN missing")
m = get(a.media, fields="media_type,media_product_type,comments_count,timestamp")
print("media:", m.get("media_type"), m.get("media_product_type"), "comments_count:", m.get("comments_count"), m.get("timestamp"))
out, after = [], None
while True:
    kw = dict(fields="id,username,text,timestamp,replies{username,text,timestamp}", limit=50)
    if after:
        kw["after"] = after
    r = get(f"{a.media}/comments", **kw)
    out += r.get("data", [])
    after = r.get("paging", {}).get("cursors", {}).get("after") if r.get("paging", {}).get("next") else None
    if not after:
        break
print("comments:", len(out))
json.dump(encrypt(json.dumps(out).encode(), os.environ["INSIGHTS_PUBKEY"]), open(a.out, "w"))
