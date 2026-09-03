"""Draft sync from Windows notification history (Chrome toasts from Yahoo).

Yahoo's draft room sends a browser notification for every pick
("<Player> drafted by <Manager>"), and Windows keeps Chrome's toasts in
%LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db. This reads
that database every few seconds (copying it first, WAL included, so the live
file is never touched), turns the draft toasts into picks, and serves them at
http://localhost:8737/drafted.json in the same shape yahoo_sync.py uses — so
the board's "Yahoo sync" button works unchanged.

    python3 pipeline/toast_sync.py --me "zach"      # substring of your Yahoo manager name

Requires: Chrome notifications allowed for football.fantasysports.yahoo.com
(they are, if you're seeing the toasts). Works on any Windows+WSL machine.
"""
import argparse, json, os, re, shutil, sqlite3, sys, threading, time, pathlib, glob
from http.server import HTTPServer, BaseHTTPRequestHandler

DEFAULT_DB = next(iter(glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/Windows/Notifications/wpndatabase.db")), "")
TMP = pathlib.Path("/tmp/toast_sync")
PORT = 8737
CITY = {"Arizona":"ARI","Atlanta":"ATL","Baltimore":"BAL","Buffalo":"BUF","Carolina":"CAR","Chicago":"CHI",
  "Cincinnati":"CIN","Cleveland":"CLE","Dallas":"DAL","Denver":"DEN","Detroit":"DET","Green Bay":"GB",
  "Houston":"HOU","Indianapolis":"IND","Jacksonville":"JAC","Kansas City":"KC","Las Vegas":"LV",
  "Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","LA Chargers":"LAC","LA Rams":"LAR","Miami":"MIA",
  "Minnesota":"MIN","New England":"NE","New Orleans":"NO","New York Giants":"NYG","New York Jets":"NYJ",
  "NY Giants":"NYG","NY Jets":"NYJ","Philadelphia":"PHI","Pittsburgh":"PIT","Seattle":"SEA",
  "San Francisco":"SF","Tampa Bay":"TB","Tennessee":"TEN","Washington":"WAS"}

def read_toasts(db):
    """Copy db (+wal/shm) and return [(id, arrival, title, body)] for Yahoo draft toasts."""
    TMP.mkdir(exist_ok=True)
    for suf in ("", "-wal", "-shm"):
        src = db + suf
        if os.path.exists(src): shutil.copy(src, TMP/("wpn.db"+suf))
        elif os.path.exists(TMP/("wpn.db"+suf)): os.remove(TMP/("wpn.db"+suf))
    con = sqlite3.connect(TMP/"wpn.db")
    rows = con.execute("select n.Id, n.ArrivalTime, n.Payload from Notification n "
                       "join NotificationHandler h on n.HandlerId=h.RecordId "
                       "where h.PrimaryId like '%Chrome%' and n.Type='toast' order by n.ArrivalTime").fetchall()
    con.close()
    out = []
    for nid, arr, payload in rows:
        p = payload.decode("utf-8", "ignore") if isinstance(payload, bytes) else str(payload or "")
        texts = re.findall(r"<text[^>]*>([^<]+)</text>", p)
        if len(texts) >= 2 and "fantasysports.yahoo.com" in p and " drafted by " in texts[1]:
            out.append((nid, arr, texts[0].strip(), texts[1].strip()))
    return out

state = {"picks": [], "league": "", "updated": 0, "managers": []}

def poll(db, me, seen):
    while True:
        try:
            toasts = read_toasts(db)
            managers = set()
            for nid, arr, title, body in toasts:
                m = re.match(r"(.+?) drafted by (.+)$", body)
                if not m: continue
                name, mgr = m.group(1).strip(), m.group(2).strip()
                managers.add(mgr)
                if nid in seen: continue
                seen[nid] = {"name": name, "mgr": mgr, "title": title, "arr": arr}
            # optional backfill for picks that expired from the toast history:
            # data_private/backfill.json = [{"name":..,"by":..}, ...] in draft order
            bf = pathlib.Path(__file__).parent.parent/"data_private"/"backfill.json"
            if bf.exists():
                try:
                    for i, rec in enumerate(json.load(open(bf))):
                        key = f"bf{i}"
                        if key not in seen:
                            seen[key] = {"name": rec["name"], "mgr": rec.get("by",""), "title": "", "arr": -1_000_000 + i}
                except Exception as e:
                    print("backfill error:", e, flush=True)
            picks = []
            for i, (nid, rec) in enumerate(sorted(seen.items(), key=lambda kv: kv[1]["arr"])):
                nm, pos, team = rec["name"], "", ""
                if nm in CITY: pos, team, nm = "DEF", CITY[nm], nm
                picks.append({"pick": i+1, "name": nm, "pos": pos, "team": team,
                              "mine": bool(me) and me.lower() in rec["mgr"].lower(), "by": rec["mgr"]})
            if picks and picks != state["picks"]:
                state["picks"] = picks
                state["league"] = next((r["title"].replace(" Draft","") for r in seen.values() if r.get("title")), "")
                state["updated"] = time.time()
                last = picks[-1]
                print(f"\n{time.strftime('%H:%M:%S')}  pick {last['pick']}: {last['name']} — {last['by']}"
                      f"{'  ★ MINE' if last['mine'] else ''}   ({len(picks)} total)", flush=True)
            state["managers"] = sorted(managers)
        except Exception as e:
            print("poll error:", e, flush=True)
        time.sleep(3)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path != "/drafted.json":
            self.send_response(404); self.end_headers(); return
        body = json.dumps(state).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--me", default="", help="substring of your Yahoo manager name (marks your picks ★)")
    a = ap.parse_args()
    if not a.db or not os.path.exists(a.db): sys.exit(f"notification db not found: {a.db!r}")
    seen = {}
    threading.Thread(target=poll, args=(a.db, a.me, seen), daemon=True).start()
    time.sleep(1.5)
    print(f"toast sync: {len(state['picks'])} picks so far; managers seen: {state['managers']}")
    print(f"serving http://localhost:{PORT}/drafted.json — click 'Yahoo sync' on the board", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
