# bkbfanssv stats store

Local copy of every played FESABAL Liga de Desarrollo game (box scores from the Sportradar embed API that
powers fesabal.org's stats widget), so the weekly stories and carousels do not need the browser or many
calls to fesabal. Built Oct 15 2026 (Nelson: "datos fieles con menos llamadas").

## Layout
- `data/<season>/<code>/games/<fixture id>.json` one compact box score per game: date, venue, pool, teams
  (id, name, score, logo id), players (name, team id, bib, photo id, starter, played, minutes, pts, reb, ast,
  stl, blk, tpm/tpa, fgm/fga, ftm/fta, oreb/dreb, tov, pf, eff, plus-minus) and the API `state` to re-fetch it.
  `check` lists teams whose player points do not add up to the official score (fesabal capture errors).
- `data/<season>/<code>/standings.json` and `fesabal-leaders.json`: as published by fesabal (cross-check).
- `stats/sources.json`: per league the API endpoints (fixtures "All rounds", standings, leaders), captured once
  from the widget in the browser. They are public widget URLs, not secrets.

## Sync (GitHub Actions, no browser)
Workflow `sync-stats` runs Sunday 23:07 and Monday 07:07 El Salvador time, and on demand. It downloads only
games we don't have, plus games from the last 14 days again (fesabal corrections), then commits data/ and
logs/sync-<run>.txt. Manual run: dispatch with input recheck_days.

## Query (prints only the answer)
```
python3 stats/q.py jornadas 16M
python3 stats/q.py dreamteam 16M [-j N | --torneo] [--min-games K] [--data]
python3 stats/q.py sixth 18F [-j N | --torneo] [--data]
python3 stats/q.py leaders 18M [--torneo] [--data]          # 7 categories, totals
python3 stats/q.py standings 16M [--data]
python3 stats/q.py carousel 16M [-j N] --out <dir>          # games.csv + standings_full.json for gen.py
python3 stats/q.py player 16M valenzuela
```
`--data` prints the exact pipe lines read by build_leaders.py / build_sixth.py / build_dreamteam.py.
Jornada = Mon-Sun week with games, numbered in order (fesabal's "Ronda: N" numbers games, not jornadas).
Rules: Dream Team = top 5 EFF summed over the jornada; Sexto = same, only games off the bench
(starter false) and only players who did not start in that span; ties -> PTS, then REB+AST.

## When to fall back to the browser
- A league is missing from sources.json (new competition, e.g. U21 Clausura): capture its fixtures/standings/
  statistics_leaders URLs from the widget (performance entries after switching competition and view) and add it.
- sync fails with HTTP 400 on a league: its state URL changed; recapture it.
- Ingest from a browser dump: `python3 stats/ingest.py <dump.json>` (same format the sync builds).
