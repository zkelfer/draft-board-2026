# Draft Board 2026 — working notes for Claude Code

Single-file HTML fantasy draft dashboard plus a small Python data pipeline. Owner: Zach. Personal use only.

## Layout
- `pipeline/` — source lists (pasted text), merge/normalize script, HTML template, build script
- `dist/index.html` — the built app. Never hand-edit; rebuild from `pipeline/template.html`.

## Conventions
- Player identity key: lowercase name, periods/apostrophes stripped, Jr/Sr/II/III removed. See `norm()` in `build_data.py`. Defenses key as `def_<TEAM>`. Team code `JAX` → `JAC`.
- Rank sources live in `p["r"]` keyed by source id: `fft_half`, `fft_ppr`, `fft_std`, `ffc`, `pp`, `yahoo`, `udog`.
- Adding a source: paste its list into a new constant, parse it in `build_data.py` with a new source id, add the id to `FMT_SOURCES` in the template, add a row to the README sources table.
- Consensus = mean of expert/market sources present for the selected format. Value = Yahoo ADP − consensus rank.
- `sd` (subvertadown) and VAL are display-only: neither feeds the consensus. VAL is computed client-side from `proj.json` (raw stat projections from `data_private/DraftSheets_2026.xlsx` via `build_proj.py`) using the league settings behind the League button; settings persist per draft slot in `state.league`. Baseline formulas are documented in README and `computeVBD()` in the template.
- Scratched players (suspensions etc.) go in `pipeline/scratches.py` by norm() key, with the dated reason.
- Build order matters: `build_proj.py` → `build_data.py` → `build.py`. Both proj and subvertadown steps degrade gracefully if `data_private/` is missing (VAL/SubD columns just go empty).
- Persistence uses `window.storage` (Claude artifact API). For standalone hosting, swap to `localStorage` behind the same `get/set` calls in `loadSlot()` / `save()`.

## Build
```
cd pipeline && python3 build_data.py && python3 build.py
```
No dependencies beyond Python 3 stdlib.

## Planned
- Yahoo Fantasy Sports API (read-only, OAuth2) once approved: `draft_analysis` for live ADP, league settings for format auto-select, draft results for auto-marking. Keep a `pipeline/yahoo.py` fetch step that writes into `data.json` under `r.yahoo` so the template doesn't change.
- Merge JJ Zachariason / Ringer lists if Zach pastes them.
