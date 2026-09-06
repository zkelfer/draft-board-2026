"""Canonical player-identity normalization — one source of truth for the join key.

Ranks (build_data.py), projections (build_proj.py), live ADP and draft-sync all key
players by this. Previously three separate copies of this logic had drifted apart, which
silently dropped joins for names like "D J Moore". The client-side nk() in template.html
mirrors name_key() exactly — keep the two in sync if you change the rules here.
"""
import re

TEAM_FIX = {"JAX": "JAC"}
DEF_CITY = {"DEN":"Broncos","HOU":"Texans","SEA":"Seahawks","MIN":"Vikings","PIT":"Steelers",
  "LAR":"Rams","LAC":"Chargers","PHI":"Eagles","NE":"Patriots","DET":"Lions","BUF":"Bills",
  "JAC":"Jaguars","BAL":"Ravens","DAL":"Cowboys","GB":"Packers","KC":"Chiefs"}

# Name variants that must collapse to one key. The "dj moore" two-step below lets
# "DJ Moore", "D.J. Moore", and "D J Moore" all resolve to the single key "dj moore".
_ALIAS = {"kenny gainwell":"kenneth gainwell", "dj moore":"d j moore",
          "chig okonkwo":"chigoziem okonkwo"}

def name_key(name):
    """Normalize a player NAME to its canonical join key (no pos/team handling)."""
    n = name.replace("’","'").replace("‘","'")
    k = n.lower().replace(".","").replace("'","")
    k = re.sub(r"\b(jr|sr|iii|ii)\b","",k)
    k = re.sub(r"\s+"," ",k).strip()
    k = _ALIAS.get(k, k)
    return k.replace("d j moore","dj moore")

def norm(name, pos, team):
    """Return (key, display). DEF keys as def_<TEAM>; everyone else uses name_key()."""
    team = TEAM_FIX.get(team, team)
    if pos == "DEF":
        return f"def_{team}", f"{DEF_CITY.get(team, team)} D/ST"
    disp = name.replace("’","'").replace("‘","'")
    return name_key(name), disp
