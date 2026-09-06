"""Fetch Boris Chen draft boards -> data_private/borischen.json (free S3 CSVs, no key).

Boris Chen runs a Gaussian-mixture clustering over FantasyPros' Expert Consensus
Rankings (100+ analysts) to produce format-specific ranks + tiers, plus rank
dispersion (best/worst/std-dev). We fetch all three scoring formats. Keys use the
shared names.name_key() so they join cleanly onto data.json in build_data.py.

Run before build_data.py (or via refresh.py). Writes to the gitignored data_private/;
build_data.py bakes the ranks/tiers into the committed data.json. Skips DST/K (ECR adds
little there and name->team mapping is noisy; FFToday already covers them).
"""
import argparse, json, csv, io, urllib.request, pathlib, datetime

from names import name_key

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "data_private" / "borischen.json"
BASE = "https://s3-us-west-1.amazonaws.com/fftiers/out/"
FILES = {"std": "weekly-ALL.csv", "half": "weekly-ALL-HALF-PPR.csv", "ppr": "weekly-ALL-PPR.csv"}
KEEP = {"QB", "RB", "WR", "TE"}
# The S3 files are named weekly-* because after NFL week 1 they FLIP from preseason
# draft ranks to in-season weekly ranks. Weekly ranks would silently poison the
# board's x2-weighted consensus source, so refuse to fetch once the season starts.
SEASON_START = datetime.date(2026, 9, 10)  # 2026 opener

def season_started(today=None):
    return (today or datetime.date.today()) >= SEASON_START

def looks_like_draft_board(board):
    """Shape sanity: a draft board is deep (~180+ QB/RB/WR/TE) and QB-rich (~25).
    A thin or QB-poor parse means the source flipped to weekly mode or broke."""
    qbs = sum(1 for v in board.values() if v.get("p") == "QB")
    return len(board) >= 150 and qbs >= 20

def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "draft-board/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")

def _parse(text):
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row["Position"] not in KEEP:
            continue
        key = name_key(row["Player.Name"])
        if not key:
            continue
        out[key] = {
            "r": int(row["Rank"]),
            "t": int(row["Tier"]),
            "p": row["Position"],                 # kept for shape sanity; ignored by build_data
            "lo": int(float(row["Best.Rank"])),   # best (min) rank across experts
            "hi": int(float(row["Worst.Rank"])),  # worst (max) rank across experts
            "sd": round(float(row["Std.Dev"]), 2),
        }
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="fetch even after the season started (files may hold WEEKLY ranks, not draft ranks)")
    a = ap.parse_args()
    if season_started() and not a.force:
        raise SystemExit(f"borischen: refusing to fetch on/after {SEASON_START} — the weekly-* files "
                         f"flip to in-season weekly ranks and would poison the draft consensus. "
                         f"(--force to override; the previous borischen.json is left untouched.)")
    boards = {}
    for fmt, fname in FILES.items():
        try:
            b = _parse(_fetch(BASE + fname))
            if not looks_like_draft_board(b):
                print(f"borischen {fmt}: parse looks like a WEEKLY/broken list "
                      f"({len(b)} players) — skipping this format")
                continue
            boards[fmt] = b
            print(f"borischen {fmt}: {len(b)} QB/RB/WR/TE from {fname}")
        except Exception as e:
            print(f"borischen {fmt}: FAILED ({e!r}) — skipping this format")
    if not boards:
        raise SystemExit("borischen: no usable formats fetched; leaving previous borischen.json untouched")
    OUT.parent.mkdir(exist_ok=True)
    payload = {"fetched": datetime.date.today().isoformat(), "boards": boards}
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} (fetched {payload['fetched']})")

if __name__ == "__main__":
    main()
