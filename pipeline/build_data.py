import re, json
from sources import FFTODAY_HALF, FFTODAY_PPR, FFTODAY_STD
from sources2 import ADP, FFC, PP

TEAM_FIX = {"JAX":"JAC"}
DEF_CITY = {"DEN":"Broncos","HOU":"Texans","SEA":"Seahawks","MIN":"Vikings","PIT":"Steelers","LAR":"Rams","LAC":"Chargers","PHI":"Eagles","NE":"Patriots","DET":"Lions","BUF":"Bills","JAC":"Jaguars","BAL":"Ravens","DAL":"Cowboys","GB":"Packers","KC":"Chiefs"}

def norm(name, pos, team):
    team = TEAM_FIX.get(team, team)
    if pos == "DEF":
        return f"def_{team}", f"{DEF_CITY.get(team, team)} D/ST"
    n = name.replace("’","'").replace("‘","'")
    disp = n
    k = n.lower().replace(".","").replace("'","")
    k = re.sub(r"\b(jr|sr|iii|ii)\b","",k)
    k = re.sub(r"\s+"," ",k).strip()
    k = {"kenny gainwell":"kenneth gainwell","dj moore":"d j moore","chig okonkwo":"chigoziem okonkwo",
         "tre harris":"tre harris"}.get(k,k)
    k = k.replace("d j moore","dj moore")
    return k, disp

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

# sanity: keys with same display but different key
out = []
for k,p in players.items():
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
