# bkbfanssv-publisher

Publisher for [@bkbfanssv](https://instagram.com/bkbfanssv) (FESABAL Liga de Desarrollo).
Everything here is already public on Instagram; no secrets live in this repo.

- `stories/<date>/<league>/` leader stories + Dream Team (MP4) and `tags.json` (confirmed handles only)
- `images/<slug>/` carousel JPEGs (served by GitHub Pages so Instagram can download them)
- `publisher/` scripts; `.github/workflows/` manual workflows, dry run by default

Secret `IG_TOKEN` (Instagram token) and variable `IG_USER_ID` are set in the repo settings, never in files.
