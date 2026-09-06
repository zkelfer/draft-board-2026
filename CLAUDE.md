# Draft Board 2026 — working notes for Claude Code

Single-file HTML fantasy draft dashboard plus a small Python data pipeline. Owner: Zach. Personal use only.

## Layout
- `pipeline/` — source lists (pasted text), merge/normalize script, HTML template, build script
- `dist/index.html` — the built app. Never hand-edit; rebuild from `pipeline/template.html`.

## Conventions
- Player identity key: lowercase name, periods/apostrophes stripped, Jr/Sr/II/III removed. Canonical logic lives in `pipeline/names.py` (`norm()`/`name_key()`), imported by `build_data.py` and `build_proj.py`; the client `nk()` in the template mirrors it exactly. Defenses key as `def_<TEAM>`. Team code `JAX` → `JAC`.
- Rank sources live in `p["r"]` keyed by source id: `fft_half`, `fft_ppr`, `fft_std`, `bc_half`, `bc_ppr`, `bc_std` (Boris Chen ECR, fetched), `ffc`, `pp`, `yahoo`, `udog`, `sd`. Boris Chen tiers/dispersion ride along in `p["bc"][fmt]`; Sleeper injury flags in `p["inj"]`.
- Adding a source: pasted lists go in a new constant parsed by `build_data.py`; fetched sources get a `fetch_*.py` writing to `data_private/` and a merge block in `build_data.py` (with a carry-forward fallback). Then add `[id, weight]` to `FMT_SOURCES` in the template, a date entry in `build_data.py`'s dates block, and a row to the README sources table.
- Consensus is a **weighted power-curve mean**, not an ordinal mean: each source rank `r` is mapped to `r^-0.41`, weight-averaged over the sources present for the selected format, then inverted back to a rank (`compute()` in the template). `FMT_SOURCES` is a list of `[sourceKey, weight]` pairs per format — Boris Chen (an aggregate of 100+ analysts, format-native) carries ×2; FFToday/FFC/PrizePicks ×1. One contrarian source can't drag a near-unanimous #1 down.
- "Value vs Yahoo" = `17·ln(ADP / expertRank)` — the gap priced in projected points on a log pick-value curve (positive = the room lets them fall). Anchored on the freshest market ADP (live FFC once refreshed, else the embedded Yahoo snapshot). The raw `yahoo − consensusRank` survives only as the hover tooltip (`valPicks`).
- Tabs beyond the board: Values vs Yahoo, My team, My picks (survival-% candidates), Tiers (cliff ladder with a "gone by your pick #N" line), Value map (rank-vs-ADP scatter with draft-now rings). The **draft-now engine** (`computeRecs()` in the template) arms when League → Pick is set: regret-minimization score = (value − expected best at position at your next pick) × need weight − risk − bye penalty; survival from run-adjusted ADP with σ from Boris Chen stddev.
- Sync behavior: on by default; **"Clear this draft" turns Sync off** (gates both the helper poll and extension posts via `syncPaused`) and wipes the extension's cached room; it stays off until clicked back on.
- `sd` (subvertadown) and VAL are display-only: neither feeds the consensus. VAL is computed client-side from `proj.json` (raw stat projections from `data_private/DraftSheets_2026.xlsx` via `build_proj.py`) using the league settings behind the League button; settings persist per draft slot in `state.league`. Baseline formulas are documented in README and `computeVBD()` in the template.
- Scratched players (suspensions etc.) go in `pipeline/scratches.py` by norm() key, with the dated reason.
- Build order matters: fetchers → `build_proj.py` → `build_data.py` → `build.py`; `pipeline/refresh.py` runs the whole chain with best-effort fetches. Everything degrades gracefully when `data_private/` inputs are missing (carry-forward from the previous data.json; VAL goes empty only if proj.json is null).
- Persistence uses `window.storage` (Claude artifact API). For standalone hosting, swap to `localStorage` behind the same `get/set` calls in `loadSlot()` / `save()`.

## Build
```
python pipeline/refresh.py     # full refresh (python3 on Linux/cloud)
cd pipeline && python build_data.py && python build.py   # rebuild only
```
On Windows use `python`/`py` — the `python3` alias is a Microsoft Store stub.
Runtime is Python 3 stdlib only (`openpyxl` needed just for `build_proj.py`; pytest just for tests).

## Planned
- Yahoo Fantasy Sports API (read-only, OAuth2) once approved: `draft_analysis` for live ADP, league settings for format auto-select, draft results for auto-marking. Keep a `pipeline/yahoo.py` fetch step that writes into `data.json` under `r.yahoo` so the template doesn't change.
- Merge JJ Zachariason / Ringer lists if Zach pastes them.
