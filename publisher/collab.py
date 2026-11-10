"""Instagram collaborators (Collab posts) for publish.py, reel.py and publish_story.py.

"collaborators": ["club_a", "club_b"]   optional, up to 3 usernames (no @), unique, never bkbfanssv itself.
Supported on the carousel PARENT container, a feed image post (tags.json "kind": "post") and a reel. Never on carousel
slides (is_carousel_item) or stories. Sent like user_tags: a JSON-encoded list of usernames. Each invited account gets
the invite in the app and must accept it; until then the post shows only on @bkbfanssv.

It is not proven that the Instagram API with Instagram Login (graph.instagram.com) accepts the parameter, so a 4xx on a
container request that carried collaborators is retried ONCE without them (nothing was published yet, so that is safe)
and the run logs "collaborators rejected: <error>; retrying without". The post is never lost because of it.
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


def should_retry(p, code):
    """True when a failed container request carried collaborators and failed with a client error (4xx)."""
    return "collaborators" in p and 400 <= int(code or 0) < 500


def warn(err):
    msg = f"collaborators rejected: {str(err)[:300]}; retrying without"
    print(f"WARNING {msg}")
    return msg
