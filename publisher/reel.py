"""Reel support for publish.py (a posts/<slug>/manifest.json with "kind": "reel").

manifest.json:
{"kind": "reel",
 "video": "images/<slug>/reel.mp4",          # repo-relative, served by GitHub Pages (removed by cleanup-media)
 "caption": "...",
 "cover": "images/<slug>/cover.jpg",          # optional JPEG cover (cover_url); else thumb_offset_ms
 "thumb_offset_ms": 1500,                     # optional frame used as cover when there is no "cover"
 "share_to_feed": true,                       # optional, default true (reel also shows in the profile grid)
 "audio_name": "...",                         # optional name for the reel's original audio
 "tags": [{"username": "team"}],             # optional, public accounts only, max 20, no x/y for reels
 "collaborators": ["club"]}                   # optional Collab invite, max 3 usernames (no @); rules in collab.py
Music goes INSIDE the MP4 (the API has no music library). No location. Collaborators: confirmed handles only
(studio docs/handles.md), never on simulation posts; the club must accept the invite in the app; if Instagram
rejects the parameter, publish.py retries once without it.

Rules enforced: MP4 H.264 + AAC (audio required), 9:16, 3-90 s, 23-60 fps, <= 100 MB, cover JPEG.
The media check needs ffprobe; if it is missing (e.g. a runner without ffmpeg) only the size/extension are checked
and Instagram does the rest.
"""
import json, os, shutil, subprocess

import collab

MIN_S, MAX_S = 3.0, 90.0
MAX_MB = 100
ASPECT = 9 / 16


def is_reel(m):
    return m.get("kind") == "reel"


def check_manifest(m, root):
    """Errors in the manifest itself (list of strings, empty = ok)."""
    err = []
    v = m.get("video", "")
    if not v.lower().endswith(".mp4"):
        err.append(f"video must be an .mp4 file, got {v!r}")
    elif not os.path.isfile(os.path.join(root, v)):
        err.append(f"video not found: {v}")
    if not m.get("caption", "").strip():
        err.append("empty caption")
    elif len(m["caption"]) > 2200:
        err.append(f"caption longer than 2200 characters ({len(m['caption'])})")
    c = m.get("cover")
    if c:
        if not c.lower().endswith((".jpg", ".jpeg")):
            err.append(f"cover must be JPEG, got {c!r}")
        elif not os.path.isfile(os.path.join(root, c)):
            err.append(f"cover not found: {c}")
        if "thumb_offset_ms" in m:
            err.append("use either cover or thumb_offset_ms, not both")
    if "thumb_offset_ms" in m and not (isinstance(m["thumb_offset_ms"], int) and m["thumb_offset_ms"] >= 0):
        err.append("thumb_offset_ms must be a non-negative integer (milliseconds)")
    if "share_to_feed" in m and not isinstance(m["share_to_feed"], bool):
        err.append("share_to_feed must be true or false")
    if "collaborators" in m:
        err += collab.check(m["collaborators"])
    for k in ("slides", "location_id"):
        if k in m:
            err.append(f"{k!r} is not supported for reels here")
    tags = m.get("tags", [])
    if len(tags) > 20:
        err.append("more than 20 tags")
    seen = set()
    for t in tags:
        u = t.get("username", "").lstrip("@").lower()
        if not u:
            err.append(f"tag without username: {t}")
        if u in seen:
            err.append(f"duplicate tag {u}")
        seen.add(u)
    return err


def probe(path):
    """ffprobe summary of an MP4, or None when ffprobe is not installed."""
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                   "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,"
                                   "sample_rate,pix_fmt:stream_side_data=rotation", "-of", "json", path])
    return json.loads(out)


def _fps(s):
    n, _, d = (s or "0/1").partition("/")
    return float(n) / float(d or 1) if float(d or 1) else 0.0


def check_media(info, size_bytes):
    """Errors in the video file (list of strings). info = probe() output or None (size check only)."""
    err = []
    if size_bytes > MAX_MB * 1024 * 1024:
        err.append(f"video is {size_bytes / 1048576:.1f} MB, max {MAX_MB} MB")
    if info is None:
        return err
    if "mp4" not in info.get("format", {}).get("format_name", ""):
        err.append(f"container is {info.get('format', {}).get('format_name')}, need MP4")
    dur = float(info.get("format", {}).get("duration") or 0)
    if not MIN_S <= dur <= MAX_S:
        err.append(f"duration {dur:.1f} s, must be {MIN_S:.0f}-{MAX_S:.0f} s")
    vs = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    au = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(vs) != 1:
        err.append(f"need exactly 1 video stream, got {len(vs)}")
    else:
        v = vs[0]
        if v.get("codec_name") != "h264":
            err.append(f"video codec {v.get('codec_name')}, need h264")
        if v.get("pix_fmt") not in (None, "yuv420p", "yuvj420p"):
            err.append(f"pixel format {v.get('pix_fmt')}, need yuv420p")
        w, h = v.get("width") or 0, v.get("height") or 0
        rot = abs(int(((v.get("side_data_list") or [{}])[0]).get("rotation", 0) or 0))
        if rot in (90, 270):
            w, h = h, w
        if not h or abs(w / h - ASPECT) > 0.01:
            err.append(f"frame {w}x{h} is not 9:16 (use 1080x1920)")
        elif h < 960:
            err.append(f"frame {w}x{h} too small (use 1080x1920)")
        fps = _fps(v.get("avg_frame_rate"))
        if not 23 <= fps <= 60:
            err.append(f"frame rate {fps:.2f}, must be 23-60 fps")
    if not au:
        err.append("no audio stream: put the music inside the MP4 (studio carousel/slides_to_reel.sh or music/mux.py)")
    else:
        a = au[0]
        if a.get("codec_name") != "aac":
            err.append(f"audio codec {a.get('codec_name')}, need aac")
        if int(a.get("sample_rate") or 0) > 48000:
            err.append(f"audio sample rate {a.get('sample_rate')}, max 48000")
    return err


def summary(info, size_bytes):
    if info is None:
        return f"{size_bytes / 1048576:.1f} MB (ffprobe not available: codecs/duration not checked)"
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
    return (f"{float(info['format'].get('duration') or 0):.1f} s, {v.get('width')}x{v.get('height')} "
            f"{v.get('codec_name')} {_fps(v.get('avg_frame_rate')):.0f} fps, audio {a.get('codec_name') or 'none'} "
            f"{a.get('sample_rate') or ''} Hz, {size_bytes / 1048576:.1f} MB")


def payload(m, base):
    """Container payload for POST /{ig-user-id}/media."""
    p = {"media_type": "REELS", "video_url": f"{base}/{m['video']}", "caption": m["caption"],
         "share_to_feed": "true" if m.get("share_to_feed", True) else "false"}
    if m.get("cover"):
        p["cover_url"] = f"{base}/{m['cover']}"
    elif "thumb_offset_ms" in m:
        p["thumb_offset"] = str(m["thumb_offset_ms"])
    if m.get("audio_name"):
        p["audio_name"] = m["audio_name"]
    tags = [{"username": t["username"].lstrip("@")} for t in m.get("tags", [])]
    if tags:
        p["user_tags"] = json.dumps(tags)
    return collab.add(p, collab.names(m))
