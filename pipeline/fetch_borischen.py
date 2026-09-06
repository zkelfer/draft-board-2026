"""Fetch Boris Chen draft boards -> data_private/borischen.json (free S3 CSVs, no key).

Boris Chen runs a Gaussian-mixture clustering over FantasyPros' Expert Consensus
Rankings (100+ analysts) to produce format-specific ranks + tiers, plus rank
dispersion (best/worst/std-dev). We fetch all three scoring formats. Keys use the
shared names.name_key() so they join cleanly onto data.json in build_data.py.

Run before build_data.py (or via refresh.py). Writes to the gitignored data_private/;
build_data.py bakes the ranks/tiers into the committed data.json. Skips DST/K (ECR adds
little there and name->team mapping is noisy; FFToday already covers them).
"""
import json, csv, io, urllib.request, pathlib, datetime

from names import name_key

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "data_private" / "borischen.json"
BASE = "https://s3-us-west-1.amazonaws.com/fftiers/out/"
FILES = {"std": "weekly-ALL.csv", "half": "weekly-ALL-HALF-PPR.csv", "ppr": "weekly-ALL-PPR.csv"}
KEEP = {"QB", "RB", "WR", "TE"}

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
            "lo": int(float(row["Best.Rank"])),   # best (min) rank across experts
            "hi": int(float(row["Worst.Rank"])),  # worst (max) rank across experts
            "sd": round(float(row["Std.Dev"]), 2),
        }
    return out

def main():
    boards = {}
    for fmt, fname in FILES.items():
        try:
            boards[fmt] = _parse(_fetch(BASE + fname))
            print(f"borischen {fmt}: {len(boards[fmt])} QB/RB/WR/TE from {fname}")
        except Exception as e:
            print(f"borischen {fmt}: FAILED ({e!r}) — skipping this format")
    if not boards:
        raise SystemExit("borischen: no formats fetched; leaving previous borischen.json untouched")
    OUT.parent.mkdir(exist_ok=True)
    payload = {"fetched": datetime.date.today().isoformat(), "boards": boards}
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} (fetched {payload['fetched']})")

if __name__ == "__main__":
    main()
