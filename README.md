# Draft Board 2026

A single-file, personal fantasy football draft dashboard. Aggregates public expert
rankings into a consensus, compares it against Yahoo ADP to find draft-day value,
and tracks drafted players live across multiple leagues.

**Personal, non-commercial, single user.** Built for my own Yahoo Fantasy Football
leagues. Nothing is redistributed or served to anyone else.

## What it does

- Standard / Half-PPR / PPR toggle that swaps format-specific ranking boards
- Consensus rank, average, high/low, and spread across sources
- **Value vs Yahoo**: Yahoo ADP minus consensus rank — who the room lets fall, who it reaches on
- Five independent draft slots; mark players drafted (✕) or drafted by me (★), persisted
- "On the clock" strip: best available, best value, next up at each position
- Roster tracker with starter needs and bye-week stacking warnings
- Optional live ADP refresh from FantasyFootballCalculator's public feed

## Run it

Open `dist/index.html` in a browser. No server needed.

How to test: `pytest tests/test_build.py` — checks `pipeline/data.json` and
`pipeline/proj.json` parse and rebuilds `dist/index.html` to confirm no
template placeholders are left behind.

## Data pipeline

```
pipeline/
  sources.py      FFToday Std / Half / PPR boards (pasted, dated)
  sources2.py     Yahoo + Underdog ADP table, FFC market ranks, PrizePicks top-200
  scratches.py    manual scratches (suspensions etc.) dropped from the board
  build_proj.py   data_private/DraftSheets_2026.xlsx → proj.json (raw stat projections)
  build_data.py   normalizes names, merges sources → data.json
  template.html   the app; __DATA__, __PROJ__ and __ASOF__ are injected at build
  build.py        template + data.json + proj.json → dist/index.html
```

Refresh cycle: update the pasted lists in `sources*.py`, then

```
cd pipeline && python3 build_proj.py && python3 build_data.py && python3 build.py
```

`data_private/` is git-ignored (shared/scraped source material, not redistributable).
`build_proj.py` and the subvertadown merge skip cleanly when it's absent.

## VAL column (league-adjusted value over replacement)

The **League** button on the board sets team count, roster slots, superflex, pass-TD/INT
scoring and auction budget per draft slot. VAL = projected points above the positional
baseline for those settings; hover a value for its auction dollar estimate. Projections
come from a friend's DraftSheets workbook (raw stat lines, low/avg/high, projected missed
games); the baseline math follows its VBD model: starters × league size (QB ×1.17,
RB ×1.267, WR ×1.23, TE ×1.0) plus each position's share of the flex pool, with
projections discounted ×(16 − missed games)/17. Reception scoring follows the
Std / Half / PPR toggle.

## Sources (as of Aug 31, 2026)

| Source | Type | Formats | Date |
|---|---|---|---|
| FFToday (Mike Krueger) | Expert | Std, Half, PPR (separate boards) | 8/30 |
| PrizePicks (Christian Hardy) | Expert | PPR | 8/29 |
| FantasyFootballCalculator | Market (mock drafts) | Half-PPR | 8/31 |
| Yahoo ADP, Underdog ADP | Market | Half-PPR | 8/24 (via FFToday) |
| DraftSheets workbook (shared) | Projections (VAL column) | Any (recomputed) | 8/30 |
| Subvertadown TapThatDraft | Value board (SubD column) | 1.0 PPR, 12-team | 8/31 |

## Set up on another computer

```
git clone https://github.com/zkelfer/draft-board-2026.git
cd draft-board-2026
```
Nothing to build — `dist/index.html` is committed and the hosted copy is at
https://zkelfer.github.io/draft-board-2026/. Python 3 (stdlib only) is the only
requirement for the draft-day helper. `data_private/` is not in the repo and is not
needed on draft day (it only feeds the daily rebuild).

**Install the browser extension (once, any OS):** Chrome → `chrome://extensions` →
Developer mode → *Load unpacked* → pick the `extension/` folder. It reads the Yahoo
draft room's "Round R, Pick P / Last: …" lines and pushes every pick — yours
included — into the board tab.

**Move your prep over:** on the old machine, board → League → *Copy state*; on the
new one, *Paste state*. All five slots (marks, names, league settings) come across.

## Draft day

**Windows (native Python or WSL):**
```
python3 pipeline/toast_sync.py --me "<your Yahoo manager name>"
```
then open **http://127.0.0.1:8737/** — the board served locally on the same origin
as the pick feed, so the browser never asks for permissions. Set the slot's
League → Teams and Pick. Sync is on by default and stays on. Picks arrive from
Windows' notification history of Yahoo's Chrome toasts (everyone's picks but your
own) plus the extension (every pick, with its real number; yours are ★'d by pick
number).

**Mac / anything else:** just the extension + the hosted board — no helper needed.
The extension is the complete feed; the hosted board accepts it directly.

Never change the running setup during a live draft. Do a Yahoo mock first and
confirm the status line reads "Sync — room: N picks …" (or "helper: N picks").

## Yahoo Fantasy Sports API (planned, read-only)

Pending API approval, the hardcoded Yahoo ADP snapshot will be replaced with live data:

- `player` resource with `draft_analysis` — ADP, average round, percent drafted
- `league` settings for leagues I'm in — auto-select scoring format
- `draft_results` for my leagues — auto-mark drafted players during the draft

Access limited to leagues where I am a member. Low volume: a few calls per draft.

## Not a product

No accounts, no analytics, no monetization. One user, five leagues, one season.
