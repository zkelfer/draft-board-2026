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

## Data pipeline

```
pipeline/
  sources.py      FFToday Std / Half / PPR boards (pasted, dated)
  sources2.py     Yahoo + Underdog ADP table, FFC market ranks, PrizePicks top-200
  build_data.py   normalizes names, merges sources → data.json
  template.html   the app; __DATA__ and __ASOF__ are injected at build
  build.py        template + data.json → dist/index.html
```

Refresh cycle: update the pasted lists in `sources*.py`, then

```
cd pipeline && python3 build_data.py && python3 build.py
```

## Sources (as of Aug 31, 2026)

| Source | Type | Formats | Date |
|---|---|---|---|
| FFToday (Mike Krueger) | Expert | Std, Half, PPR (separate boards) | 8/30 |
| PrizePicks (Christian Hardy) | Expert | PPR | 8/29 |
| FantasyFootballCalculator | Market (mock drafts) | Half-PPR | 8/31 |
| Yahoo ADP, Underdog ADP | Market | Half-PPR | 8/24 (via FFToday) |

## Yahoo Fantasy Sports API (planned, read-only)

Pending API approval, the hardcoded Yahoo ADP snapshot will be replaced with live data:

- `player` resource with `draft_analysis` — ADP, average round, percent drafted
- `league` settings for leagues I'm in — auto-select scoring format
- `draft_results` for my leagues — auto-mark drafted players during the draft

Access limited to leagues where I am a member. Low volume: a few calls per draft.

## Not a product

No accounts, no analytics, no monetization. One user, five leagues, one season.
