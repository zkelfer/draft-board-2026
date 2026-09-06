# Draft Board 2026 — working notes for Claude Code

Single-file HTML fantasy draft dashboard plus a small Python data pipeline. Owner: Zach. Personal use only.

## Layout
- `pipeline/` — source lists (pasted text), merge/normalize script, HTML template, build script
- `dist/index.html` — the built app. Never hand-edit; rebuild from `pipeline/template.html`.

## Conventions
- Player identity key: lowercase name, periods/apostrophes stripped, Jr/Sr/II/III removed. Canonical logic lives in `pipeline/names.py` (`norm()`/`name_key()`), imported by `build_data.py` and `build_proj.py`; the client `nk()` in the template mirrors it exactly. Defenses key as `def_<TEAM>`. Team code `JAX` → `JAC`.
- Rank sources live in `p["r"]` keyed by source id: `fft_half`, `fft_ppr`, `fft_std`, `ffc`, `pp`, `yahoo`, `udog`.
- Adding a source: paste its list into a new constant, parse it in `build_data.py` with a new source id, add the id to `FMT_SOURCES` in the template, add a row to the README sources table.
- Consensus is a **power-curve mean**, not an ordinal mean: each source rank `r` is mapped to `r^-0.41`, those are averaged over the sources present for the selected format, then inverted back to a rank (`compute()` in the template). This averages a pick-value curve so one contrarian source can't drag a near-unanimous #1 down. Sources per format come from `FMT_SOURCES` (format FFToday + FFC + PrizePicks). Player identity is normalized by the shared `pipeline/names.py` (`norm`/`name_key`); the client `nk()` mirrors it exactly.
- "Value vs Yahoo" = `17·ln(yahooADP / expertRank)` — the gap priced in projected points on a log pick-value curve (positive = the room lets them fall). The raw `yahoo − consensusRank` survives only as the hover tooltip (`valPicks`).
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
