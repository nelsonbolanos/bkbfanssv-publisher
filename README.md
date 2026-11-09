# bkbfanssv-publisher (public)

Only what Instagram needs at posting time: the final images/videos (served by GitHub Pages), the tag manifest
of each post, and the publish workflows (IG_TOKEN is a repo secret, never in files).
Everything that MAKES the content (stats, renderers, handles, player photos) lives in the private repo
nelsonbolanos/bkbfanssv-studio.

- `stories/<date>/<league>/NN-*.mp4` + `tags.json` -> workflow publish-story
- `images/<slug>/*.jpg` + `posts/<slug>/manifest.json` -> workflow publish-carousel
- reels go the same way: `images/<slug>/reel.mp4` (music inside the MP4) + `posts/<slug>/manifest.json` with
  `"kind": "reel"` -> workflow publish-carousel (publish.py hands it to publisher/reel.py). Manifest:
  `{"kind": "reel", "video": "images/<slug>/reel.mp4", "caption": "...", "cover": "images/<slug>/cover.jpg" | "thumb_offset_ms": 1500,
  "share_to_feed": true, "audio_name": "...", "tags": [{"username": "..."}]}` (cover, thumb, audio_name, tags optional).
  Checked before any API call: MP4 H.264 + AAC, 9:16, 3-90 s, 23-60 fps, <= 100 MB. `python3 publisher/publish.py
  posts/<slug>/manifest.json --dry-run` prints the container payload; tests: `python3 -m unittest discover tests`
- a `READY` file in a batch folder marks it as reviewed: pushing it starts the publish workflow (backup crons: stories
  18:07, carousels 09:07 El Salvador). `publisher/pending.py` lists what is READY and not yet published.
- `published.json` next to each batch records what went out (reruns never duplicate)
- media is removed 1 day after publishing (7 days if never published) by workflow cleanup-media
