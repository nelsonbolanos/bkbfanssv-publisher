"""Instagram collaborators (Collab posts) for publish.py, reel.py and publish_story.py.

"collaborators": ["club_a", "club_b"]   optional, up to 3 usernames (no @), unique, never bkbfanssv itself.
Supported on the carousel PARENT container, a feed image post (tags.json "kind": "post") and a reel. Never on carousel
slides (is_carousel_item) or stories. Sent like user_tags: a JSON-encoded list of usernames. Each invited account gets
the invite in the app and must accept it; until then the post shows only on @bkbfanssv.

It is not proven that the Instagram API with Instagram Login (graph.instagram.com) accepts the parameter, so a 4xx on a
container request that carried collaborators is retried ONCE without them (nothing was published yet, so that is safe)
and the run logs "collaborators rejected: <error>; retrying without". The post is never lost because of it.
Exception: when the error names only tagged users as inaccessible (a private player account), the collaborators stay
and the caller drops just that tag.
"""
import json, re

MAX = 3
OWN = "bkbfanssv"
_USER = re.compile(r"^[a-z0-9._]{1,30}$")


def check(value):
    """Errors in a "collaborators" value (list of strings, empty = ok)."""
    if not isinstance(value, list):
        return [f"collaborators must be a list of usernames, got {value!r}"]
    err = []
    if len(value) > MAX:
        err.append(f"at most {MAX} collaborators, got {len(value)}")
    seen = set()
    for u in value:
        if not isinstance(u, str) or not u.strip():
            err.append(f"collaborator must be a non-empty username, got {u!r}"); continue
        if u.startswith("@"):
            err.append(f"collaborator {u!r}: write the username without @"); continue
        low = u.lower()
        if not _USER.match(low):
            err.append(f"collaborator {u!r} is not a valid Instagram username"); continue
        if low == OWN:
            err.append(f"collaborator {u!r} is our own account")
        if low in seen:
            err.append(f"duplicate collaborator {u}")
        seen.add(low)
    return err


def names(m):
    """Collaborator usernames of a manifest/spec (lowercase), [] when absent."""
    return [u.lower() for u in (m or {}).get("collaborators") or []]


def add(p, users):
    """Put collaborators into a container payload (in place) when there are any; returns p."""
    if users:
        p["collaborators"] = json.dumps(list(users))
    return p


def without(p):
    """Copy of a payload without collaborators."""
    return {k: v for k, v in p.items() if k != "collaborators"}


_BLOCKED = re.compile(r"cannot be accessed:\s*([a-z0-9._,\s]+)", re.I)


def blocked(body):
    """Usernames Instagram names as inaccessible (private/invalid) in an error body, [] when it names none."""
    m = _BLOCKED.search(str(body or ""))
    return [u.strip().lower() for u in m.group(1).split(",") if u.strip()] if m else []


def should_retry(p, code, body=""):
    """True when a failed container request carried collaborators and failed with a client error (4xx).
    False when the error names inaccessible users and none of them is a collaborator: that is a user_tags problem
    (e.g. a private player account), so the caller drops that tag and keeps the club."""
    if "collaborators" not in p or not 400 <= int(code or 0) < 500:
        return False
    bad = blocked(body)
    return not bad or any(u in json.loads(p["collaborators"]) for u in bad)


def warn(err):
    msg = f"collaborators rejected: {str(err)[:300]}; retrying without"
    print(f"WARNING {msg}")
    return msg
