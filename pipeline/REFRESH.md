# Daily refresh runbook

Used by the scheduled cloud routine (and by hand when needed). Regenerates the
git-ignored `data_private/` inputs, rebuilds, and ships. Never commit anything
under `data_private/`.

Interpreter note: `python3` on the cloud/Linux; on Windows use `python` or `py`
(the `python3` alias there is a Microsoft Store stub).

1. **DraftSheets workbook** — download Drive file `1De-LEk2Moq8vQpgKBw6XKL0xOGTxQqvL`
   (`DraftSheets_2026.xlsx`, shared by Aaron) via the Google Drive connector,
   base64-decode to `data_private/DraftSheets_2026.xlsx`. (`pip install openpyxl`
   if missing.)
2. **Fetch + rebuild, one command** — `python3 pipeline/refresh.py`
   This runs, in order: `fetch_borischen.py` (Boris Chen ECR ranks + tiers, all
   three formats — a weighted consensus input, so this matters daily),
   `fetch_sleeper.py` (injury flags + scratch *suggestions*),
   `fetch_subvertadown.py` (SubD board; its `DRAFT_URL` changes if league
   settings are edited in TapThatDraft), then `build_proj.py` → `build_data.py`
   → `build.py`. Every fetch step is best-effort: on failure build_data carries
   the last-known values forward (stale beats blank) — but report which fetches
   failed in the commit summary. The two build steps must exit 0.
   Sanity: the data.json player count should stay within ±15 of the previous
   build (a bigger swing means a parse broke — stop and report, don't ship).
   Note: `fetch_borischen.py` refuses to run once the NFL season starts (its
   source files flip from draft ranks to weekly in-season ranks); that refusal
   is correct — don't override it with `--force` in the routine.
3. **News sweep + scratch suggestions** — `fetch_sleeper.py` prints
   season-ending-status suggestions (IR/PUP/Sus). Treat them as leads, not
   truth: add a `pipeline/scratches.py` entry ONLY for an indefinite suspension
   or season-ending injury confirmed by 2+ outlets, with a dated reason comment.
   Day-to-day / questionable / "expected back" news never scratches anyone.
   Also search NFL news from the last 24h for players in the top ~150 of
   `pipeline/data.json` consensus. If scratches.py changed, re-run step 2.
4. **Ship** — commit `dist/index.html`, `pipeline/proj.json`, `pipeline/data.json`,
   `pipeline/dates.json`, and any `scratches.py` change to `main`
   ("Daily data refresh YYYY-MM-DD: summary — note any fetch that failed/carried");
   push (Pages deploys automatically). If push is rejected, pull/merge first
   (generated files: prefer regenerating over hand-merging), then push; if still
   blocked, open a PR. If nothing changed, don't commit.

Out of scope for the routine: `template.html`, build scripts, ranking logic, and
the pasted `sources*.py` lists (those update by hand when new boards are pasted —
when re-pasting, also update the matching date in `_STATIC` in `build_data.py`).
