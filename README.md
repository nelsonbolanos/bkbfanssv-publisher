# bkbfanssv-publisher (public)

Only what Instagram needs at posting time: the final images/videos (served by GitHub Pages), the tag manifest
of each post, and the publish workflows (IG_TOKEN is a repo secret, never in files).
Everything that MAKES the content (stats, renderers, handles, player photos) lives in the private repo
nelsonbolanos/bkbfanssv-studio.

- `stories/<date>/<league>/NN-*.mp4` + `tags.json` -> workflow publish-story
- `images/<slug>/*.jpg` + `posts/<slug>/manifest.json` -> workflow publish-carousel
- `published.json` next to each batch records what went out (reruns never duplicate)
- media is removed 1 day after publishing (7 days if never published) by workflow cleanup-media
