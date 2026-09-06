import re, json
from names import norm, TEAM_FIX  # canonical shared normalizer
from sources import FFTODAY_HALF, FFTODAY_PPR, FFTODAY_STD
from sources2 import ADP, FFC, PP
from scratches import SCRATCHED

players = {}  # key -> dict
def ensure(key, disp, pos, team, bye=None):
    team = TEAM_FIX.get(team, team)
    p = players.setdefault(key, {"name":disp,"pos":pos,"team":team,"bye":bye,"r":{}})
    if bye and not p["bye"]: p["bye"]=bye
    if team and team!="FA" and p["team"] in (None,"FA"): p["team"]=team
    return p

def load_fft(text, tag):
    for line in text.strip().splitlines():
        m = re.match(r"(\d+)\s+(QB|RB|WR|TE|K|DEF)\s+(.+?)\s+([A-Z]{2,3})\s+(\d+)$", line.strip())
        rk,pos,name,team,bye = m.groups()
        key,disp = norm(name,pos,team)
        p = ensure(key,disp,pos,team,int(bye))
        p["r"][tag]=int(rk)

load_fft(FFTODAY_HALF,"fft_half"); load_fft(FFTODAY_PPR,"fft_ppr"); load_fft(FFTODAY_STD,"fft_std")

for line in ADP.strip().splitlines():
    rk,name,pos,team,ud,y = line.split("|")
    key,disp = norm(name,pos,team)
    p = ensure(key,disp,pos,team)
    if ud: p["r"]["udog"]=int(ud)
    if y: p["r"]["yahoo"]=int(y)

for line in FFC.strip().splitlines():
    rk,name,team,pos = line.split("|")
    if pos=="DEF": key,disp = norm("",pos,team)
    else: key,disp = norm(name,pos,team)
    p = ensure(key,disp,pos,team)
    p["r"]["ffc"]=int(rk)

for line in PP.strip().splitlines():
    rk,name,pos,team = line.split("|")
    key,disp = norm(name,pos,team)
    p = ensure(key,disp,pos,team)
    p["r"]["pp"]=int(rk)

# subvertadown TapThatDraft board (scraped, personal): display-only column, not in consensus
import pathlib, csv
_sd = pathlib.Path(__file__).parent.parent/"data_private"/"subvertadown_board.csv"
if _sd.exists():
    n = 0
    for row in csv.DictReader(open(_sd)):
        key,disp = norm(row["name"], row["pos"], row["team"])
        if key in players:
            players[key]["r"]["sd"] = int(row["overall"]); n += 1
    print(f"subvertadown: {n} matched")
else:
    # csv unavailable (e.g. cloud refresh can't reach subvertadown): keep last-known ranks
    try:
        prev = {p["id"]: p["r"].get("sd") for p in json.load(open(pathlib.Path(__file__).parent/"data.json"))}
        n = 0
        for k,p in players.items():
            if prev.get(k) is not None: p["r"]["sd"] = prev[k]; n += 1
        print(f"subvertadown: csv missing, carried {n} ranks from previous build")
    except FileNotFoundError:
        print("subvertadown: csv missing, no previous build to carry from")

# Boris Chen (FantasyPros ECR + Gaussian-mixture tiers), per format: feeds consensus.
# fetch_borischen.py writes data_private/borischen.json; ranks go into r.bc_<fmt> so
# FMT_SOURCES/compute() can weight them; tiers + dispersion (lo/hi/sd) ride along in
# p["bc"][fmt] for the tier badges and the source-spread whisker viz.
_bc = pathlib.Path(__file__).parent.parent/"data_private"/"borischen.json"
if _bc.exists():
    bc = json.loads(_bc.read_text(encoding="utf-8"))
    n = 0
    for fmt, board in bc.get("boards", {}).items():
        for key, rec in board.items():
            if key in players:
                players[key]["r"]["bc_"+fmt] = rec["r"]
                players[key].setdefault("bc", {})[fmt] = {"t":rec["t"],"lo":rec["lo"],"hi":rec["hi"],"sd":rec["sd"]}
                n += 1
    print(f"borischen: {n} format-rows merged (fetched {bc.get('fetched','?')})")
else:
    # not fetched here (e.g. secondary machine): carry last-known bc ranks/tiers from previous build
    try:
        prev = {p["id"]: (p.get("bc"), {k:v for k,v in p["r"].items() if k.startswith("bc_")})
                for p in json.load(open(pathlib.Path(__file__).parent/"data.json"))}
        n = 0
        for k,p in players.items():
            pb, pr = prev.get(k, (None, {}))
            if pr: p["r"].update(pr); n += 1
            if pb: p["bc"] = pb
        print(f"borischen: json missing, carried {n} players' ranks from previous build")
    except FileNotFoundError:
        print("borischen: json missing, no previous build to carry from")

# Sleeper injury flags (season-affecting only: IR/PUP/Sus/NFI/DNR) for an on-board badge.
# fetch_sleeper.py writes data_private/sleeper.json; Questionable/week-to-week is skipped
# as noise for a draft board. Carried forward from the prior build if not fetched here.
_INJ = {"IR","PUP","Sus","NFI","DNR"}
_slp = pathlib.Path(__file__).parent.parent/"data_private"/"sleeper.json"
if _slp.exists():
    slp = json.loads(_slp.read_text(encoding="utf-8")).get("players", {})
    n = 0
    for key, p in players.items():
        s = slp.get(key, {})
        if s.get("inj") in _INJ: p["inj"] = s["inj"]; n += 1
    print(f"sleeper: {n} board players flagged with a season-affecting injury")
else:
    try:
        prev = {p["id"]: p.get("inj") for p in json.load(open(pathlib.Path(__file__).parent/"data.json"))}
        n = 0
        for k,p in players.items():
            if prev.get(k): p["inj"] = prev[k]; n += 1
        print(f"sleeper: json missing, carried {n} injury flags from previous build")
    except FileNotFoundError:
        print("sleeper: json missing, no previous build to carry from")

# sanity: keys with same display but different key
out = []
for k,p in players.items():
    if k in SCRATCHED: continue
    out.append({"id":k,**p})
print(len(out),"players")
# check suspicious near-dupes
names = {}
for p in out:
    last = p["name"].split()[-1].lower()
    names.setdefault(last,[]).append(p["name"])
for last,ns in names.items():
    if len(set(ns))>1 and len(ns)>1:
        pass
# players present in only one expert source among fft/ffc/pp, with a rank <=130
lonely = [p["name"] for p in out if sum(1 for t in ("fft_half","ffc","pp") if t in p["r"])==1 and min(p["r"].get(t,999) for t in ("fft_half","ffc","pp"))<=120]
print("single-source top120:", lonely)
json.dump(out, open("data.json","w"))

# per-source freshness dates -> pipeline/dates.json (committed, so dates travel to other
# machines even when the fetch jsons in data_private/ aren't present). Static snapshot dates
# for the pasted sources; live 'fetched' dates for the API sources, carried forward if absent.
# _STATIC: snapshot dates of the PASTED sources — update these by hand whenever a
# sources*.py list is re-pasted (they cannot be detected automatically).
_STATIC = {"fft":"2026-08-31","ffc":"2026-08-31","pp":"2026-08-29","adp":"2026-08-24"}
def _fetched(fname):
    f = pathlib.Path(__file__).parent.parent/"data_private"/fname
    try: return json.loads(f.read_text(encoding="utf-8")).get("fetched") if f.exists() else None
    except Exception: return None
_dpath = pathlib.Path(__file__).parent/"dates.json"
_prev = {}
if _dpath.exists():
    try: _prev = json.loads(_dpath.read_text(encoding="utf-8"))
    except Exception: _prev = {}
dates = dict(_STATIC)
dates["bc"]  = _fetched("borischen.json") or _prev.get("bc")
dates["slp"] = _fetched("sleeper.json")   or _prev.get("slp")
# subvertadown csv has no embedded date; use the file's mtime when present
import datetime as _dt
if _sd.exists():
    dates["sd"] = _dt.date.fromtimestamp(_sd.stat().st_mtime).isoformat()
else:
    dates["sd"] = _prev.get("sd")
dates = {k:v for k,v in dates.items() if v}
_dpath.write_text(json.dumps(dates), encoding="utf-8")
print("source dates:", dates)
