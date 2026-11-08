"""Instagram insights snapshot for bkbfanssv (read-only: only GET calls).

Reads the account (followers, daily reach/views/visits) and every post/story published in the last DAYS days with its
insights, and writes one JSON snapshot. The repo is public, so the snapshot is never printed or committed here: with
INSIGHTS_PUBKEY set it is encrypted (AES-256 key wrapped with that RSA public key) and only the Mac that holds the
private key can read it (bkbfanssv-studio/stats/insights_pull.py).

  python3 publisher/insights.py --probe            # token permissions + metric names for one post, no numbers
  python3 publisher/insights.py --days 35 --out insights.json

Stories only expose insights while they are live (24 h), so the scheduled run is frequent enough to catch them.
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_TOKEN", "")

FEED_METRICS = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions", "follows", "profile_visits"]
REEL_METRICS = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions", "ig_reels_avg_watch_time"]
STORY_METRICS = ["reach", "views", "replies", "shares", "total_interactions", "follows", "profile_visits", "navigation"]
ACCOUNT_TOTAL = ["views", "accounts_engaged", "total_interactions", "profile_links_taps", "likes", "comments", "shares", "saves", "follows_and_unfollows"]

calls = 0


class ApiError(Exception):
    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body[:300]}")
        self.code, self.body = code, body


def get(path, **params):
    global calls
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        calls += 1
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code >= 500 and attempt < 2:
                time.sleep(3 * (attempt + 1)); continue
            if '"code":4,' in body or '"code":17,' in body or '"code":32,' in body:
                raise SystemExit(f"rate limited after {calls} calls: {body[:200]}")
            raise ApiError(e.code, body)
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(3); continue
            raise


def media_insights(m):
    kind = m.get("media_product_type") or "FEED"
    metrics = STORY_METRICS if kind == "STORY" else REEL_METRICS if kind == "REELS" else FEED_METRICS
    out, errors = {}, {}
    try:
        res = get(f"{m['id']}/insights", metric=",".join(metrics))
    except ApiError as e:
        # one unsupported metric fails the whole call: fall back to one metric per call
        res, errors["_all"] = {"data": []}, e.body[:200]
        for k in metrics:
            try:
                res["data"] += get(f"{m['id']}/insights", metric=k).get("data", [])
            except ApiError as e2:
                errors[k] = e2.body[:160]
        if len(errors) > 1:
            errors.pop("_all", None)
        else:
            errors = {}
    for d in res.get("data", []):
        if d["name"] == "navigation":
            out["navigation"] = {b["dimension_values"][0]: b["value"] for r in d.get("total_value", {}).get("breakdowns", [])
                                 for b in r.get("results", [])} or d.get("total_value", {}).get("value")
            continue
        v = d.get("values", [{}])[0].get("value") if d.get("values") else d.get("total_value", {}).get("value")
        out[d["name"]] = v
    return out, errors


def list_media(since):
    fields = "id,timestamp,media_type,media_product_type,permalink,caption,like_count,comments_count"
    items, page = [], get("me/media", fields=fields, limit=100)
    while True:
        for m in page.get("data", []):
            if m["timestamp"] < since:
                return items
            items.append(m)
        nxt = page.get("paging", {}).get("next")
        if not nxt:
            return items
        page = get("me/media", fields=fields, limit=100, after=page["paging"]["cursors"]["after"])


def list_stories():
    try:
        return get("me/stories", fields="id,timestamp,media_type,media_product_type,permalink,caption").get("data", [])
    except ApiError as e:
        print("stories list failed:", e.body[:200])
        return []


def account_daily(days):
    """Per-day account totals: followers gained (follower_count, last 30 days only), reach, and total_value metrics."""
    daily = {}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=min(days, 30))
    try:
        for d in get("me/insights", metric="follower_count,reach", period="day",
                     since=int(start.timestamp()), until=int(today.timestamp())).get("data", []):
            for v in d.get("values", []):
                daily.setdefault(v["end_time"][:10], {})[d["name"]] = v["value"]
    except ApiError as e:
        daily["_error_series"] = e.body[:200]
    day = start
    while day < today:
        nxt = day + timedelta(days=1)
        try:
            res = get("me/insights", metric=",".join(ACCOUNT_TOTAL), period="day", metric_type="total_value",
                      since=int(day.timestamp()), until=int(nxt.timestamp()))
            row = daily.setdefault(day.strftime("%Y-%m-%d"), {})
            for d in res.get("data", []):
                row[d["name"]] = d.get("total_value", {}).get("value")
        except ApiError as e:
            daily.setdefault("_error_total", e.body[:200])
        day = nxt
    return daily


def encrypt(data: bytes, pubkey_pem: str) -> dict:
    """AES-256-GCM with a random key, the key wrapped with RSA-OAEP (cryptography package)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import base64
    key, nonce = AESGCM.generate_key(256), os.urandom(12)
    pub = serialization.load_pem_public_key(pubkey_pem.encode())
    wrapped = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "key": b(wrapped), "nonce": b(nonce), "data": b(AESGCM(key).encrypt(nonce, data, None))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--out", default="insights.enc.json")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    if not TOKEN:
        sys.exit("IG_TOKEN missing")
    me = get("me", fields="username,followers_count,media_count")
    if a.probe:
        print("account:", me.get("username"))
        items = list_media((datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S+0000"))
        print("posts in the last 3 days:", len(items))
        for kind in ("FEED", "REELS"):
            m = next((x for x in items if (x.get("media_product_type") or "FEED") == kind), None)
            if m:
                ins, err = media_insights(m)
                print(kind, "metrics returned:", sorted(ins), "| errors:", {k: v[:120] for k, v in err.items()})
        st = list_stories()
        print("live stories:", len(st))
        if st:
            ins, err = media_insights(st[0])
            print("STORY metrics returned:", sorted(ins), "| errors:", {k: v[:120] for k, v in err.items()})
        d = account_daily(2)
        print("account daily keys:", {k: sorted(v) if isinstance(v, dict) else v[:150] for k, v in d.items()})
        print("calls:", calls)
        return
    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    media = list_media(since)
    ids = {m["id"] for m in media}
    media += [s for s in list_stories() if s["id"] not in ids]
    for m in media:
        m["insights"], m["insight_errors"] = media_insights(m)
        time.sleep(0.2)
    snap = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "account": me,
            "daily": account_daily(a.days), "media": media, "calls": calls}
    raw = json.dumps(snap, ensure_ascii=False).encode()
    pub = os.environ.get("INSIGHTS_PUBKEY", "")
    if not pub:
        sys.exit("INSIGHTS_PUBKEY missing: refusing to write unencrypted insights in a public repo")
    json.dump(encrypt(raw, pub), open(a.out, "w"))
    print(f"snapshot: {len(media)} media, {len(snap['daily'])} days, {calls} calls -> {a.out} (encrypted)")


if __name__ == "__main__":
    main()
