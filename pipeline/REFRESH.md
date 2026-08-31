# Daily refresh runbook

Used by the scheduled cloud routine (and by hand when needed). Regenerates the
git-ignored `data_private/` inputs, rebuilds, and ships. Never commit anything
under `data_private/`.

1. **DraftSheets workbook** — download Drive file `1De-LEk2Moq8vQpgKBw6XKL0xOGTxQqvL`
   (`DraftSheets_2026.xlsx`, shared by Aaron) via the Google Drive connector,
   base64-decode to `data_private/DraftSheets_2026.xlsx`.
2. **Subvertadown board** — `python3 pipeline/fetch_subvertadown.py`
   (one fetch; if it fails or the parse guard trips, continue without it —
   build_data carries the last-known SubD ranks forward from the previous
   data.json, so a blocked fetch goes stale rather than blank). The draft URL changes if league settings
   are edited in TapThatDraft; update `DRAFT_URL` in the script when it does.
3. **News sweep** — search NFL news from the last 24h for players in the top ~150
   of `pipeline/data.json` consensus. Add a `pipeline/scratches.py` entry ONLY for
   an indefinite suspension or season-ending injury confirmed by 2+ outlets, with
   a dated reason comment. Day-to-day / questionable / "expected back" news never
   scratches anyone.
4. **Rebuild** — `pip install openpyxl` if missing, then
   `cd pipeline && python3 build_proj.py && python3 build_data.py && python3 build.py`.
   All three must exit 0; the data.json player count should stay within ±15 of the
   previous build (a bigger swing means a parse broke — stop and report, don't ship).
5. **Ship** — commit `dist/index.html`, `pipeline/proj.json`, `pipeline/data.json`,
   and any `scratches.py` change to `main` ("Daily data refresh YYYY-MM-DD: summary");
   push (Pages deploys automatically). If push is rejected, open a PR. If nothing
   changed, don't commit.

Out of scope for the routine: `template.html`, build scripts, ranking logic, and
the pasted `sources*.py` lists (those update by hand when new boards are pasted).
