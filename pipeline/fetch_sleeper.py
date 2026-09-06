"""Fetch Sleeper player metadata -> data_private/sleeper.json (free API, no key).

Sleeper's /v1/players/nfl is a full player dump (~12k) with injury_status, team and
status. It has NO ADP, so this is not a ranking source — it feeds two things:
  1. an on-board injury badge (IR / SUS / OUT ...), attached in build_data.py
  2. season-ending scratch SUGGESTIONS printed for manual review (never auto-applied;
     real scratches still go in scratches.py so they're intentional and dated)

Keys use the shared names.name_key() so they join onto data.json. Run via refresh.py
(before build_data.py). Writes to the gitignored data_private/.
"""
import json, urllib.request, pathlib, datetime

from names import name_key

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "data_private" / "sleeper.json"
URL = "https://api.sleeper.app/v1/players/nfl"
KEEP = {"QB", "RB", "WR", "TE", "K", "DEF"}
# statuses that usually mean "won't help your fantasy team this season" -> scratch candidates
SEASON_ENDING = {"IR", "PUP", "Sus", "NFI", "DNR"}

def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "draft-board/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def main():
    raw = _fetch(URL)
    players = {}
    for p in raw.values():
        pos = p.get("position")
        if pos not in KEEP or not p.get("team"):  # skip free agents / non-fantasy
            continue
        nm = p.get("full_name") or ""
        if not nm:
            continue
        key = name_key(nm)
        rec = {"team": p.get("team"), "status": p.get("status")}
        if p.get("injury_status"):
            rec["inj"] = p["injury_status"]
        players[key] = rec
    OUT.parent.mkdir(exist_ok=True)
    payload = {"fetched": datetime.date.today().isoformat(), "players": players}
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"sleeper: {len(players)} players (fetched {payload['fetched']}) -> {OUT.name}")

    # scratch suggestions: season-ending status among players actually on the board
    data_path = HERE / "data.json"
    if data_path.exists():
        board = {p["id"] for p in json.loads(data_path.read_text(encoding="utf-8"))}
        sugg = [(k, players[k]["inj"]) for k in board
                if k in players and players[k].get("inj") in SEASON_ENDING]
        if sugg:
            print(f"scratch suggestions ({len(sugg)}) - review, then add to scratches.py if real:")
            for k, s in sorted(sugg):
                print(f"    {k:28} {s}")
        else:
            print("scratch suggestions: none among current board players")

if __name__ == "__main__":
    main()
