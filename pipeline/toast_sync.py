"""Draft sync from Windows notification history (Chrome toasts from Yahoo).

Yahoo's draft room sends a browser notification for every pick
("<Player> drafted by <Manager>"), and Windows keeps Chrome's toasts in
%LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db. This reads
that database every few seconds (copying it first, WAL included, so the live
file is never touched), turns the draft toasts into picks, and serves the board
plus a pick feed at http://127.0.0.1:8737/ (/drafted.json, liveness at /health).

    python pipeline/toast_sync.py --me "zach"       # substring of your Yahoo manager name
    python pipeline/toast_sync.py --me "zach" --reset   # ignore all pre-existing toasts
    (use python/py on Windows — the python3 alias there is a Store stub)

Requires: Chrome notifications allowed for football.fantasysports.yahoo.com
(they are, if you're seeing the toasts). Runs on Windows (native python or WSL).
On a Mac there is no toast database: use the browser extension + the hosted board instead.
"""
import argparse, json, os, re, shutil, socket, sqlite3, sys, threading, time, pathlib, glob
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

def _find_db():
    # native Windows python, then WSL
    la = os.environ.get("LOCALAPPDATA")
    cands = ([os.path.join(la, "Microsoft", "Windows", "Notifications", "wpndatabase.db")] if la else []) + \
            glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/Windows/Notifications/wpndatabase.db")
    return next((c for c in cands if os.path.exists(c)), "")
DEFAULT_DB = _find_db()
import tempfile
# per-process temp dir: two toast_sync processes (or reset_cache.py alongside a running
# helper) must never share sqlite copies — that contention corrupts the -wal/-shm reads
TMP = pathlib.Path(tempfile.gettempdir())/f"toast_sync_{os.getpid()}"
PORT = 8737
CITY = {"Arizona":"ARI","Atlanta":"ATL","Baltimore":"BAL","Buffalo":"BUF","Carolina":"CAR","Chicago":"CHI",
  "Cincinnati":"CIN","Cleveland":"CLE","Dallas":"DAL","Denver":"DEN","Detroit":"DET","Green Bay":"GB",
  "Houston":"HOU","Indianapolis":"IND","Jacksonville":"JAC","Kansas City":"KC","Las Vegas":"LV",
  "Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","LA Chargers":"LAC","LA Rams":"LAR","Miami":"MIA",
  "Minnesota":"MIN","New England":"NE","New Orleans":"NO","New York Giants":"NYG","New York Jets":"NYJ",
  "NY Giants":"NYG","NY Jets":"NYJ","Philadelphia":"PHI","Pittsburgh":"PIT","Seattle":"SEA",
  "San Francisco":"SF","Tampa Bay":"TB","Tennessee":"TEN","Washington":"WAS"}
# Yahoo toasts name a defense by nickname only ("Rams drafted by …")
NICK = {"Cardinals":"ARI","Falcons":"ATL","Ravens":"BAL","Bills":"BUF","Panthers":"CAR","Bears":"CHI","Bengals":"CIN",
  "Browns":"CLE","Cowboys":"DAL","Broncos":"DEN","Lions":"DET","Packers":"GB","Texans":"HOU","Colts":"IND",
  "Jaguars":"JAC","Chiefs":"KC","Raiders":"LV","Chargers":"LAC","Rams":"LAR","Dolphins":"MIA","Vikings":"MIN",
  "Patriots":"NE","Saints":"NO","Giants":"NYG","Jets":"NYJ","Eagles":"PHI","Steelers":"PIT","Seahawks":"SEA",
  "49ers":"SF","Buccaneers":"TB","Titans":"TEN","Commanders":"WAS"}
def def_team(nm):
    w = nm.split()
    if nm in CITY: return CITY[nm]
    if nm in NICK: return NICK[nm]
    if w and w[-1] in NICK and " ".join(w[:-1]) in CITY: return NICK[w[-1]]
    return None

def read_toasts(db):
    """Copy db (+wal/shm) and return [(id, arrival, title, body)] for Yahoo draft toasts."""
    TMP.mkdir(exist_ok=True)
    # Copy only the main db and its -wal (the real data). The -shm is a transient
    # shared-memory index for WAL mode; on Windows copying it can fail with
    # [Errno 22] Invalid argument, and it is not needed — SQLite rebuilds it from the
    # -wal on open. So never copy -shm; drop any stale copy so SQLite regenerates it.
    for suf in ("", "-wal"):
        src = db + suf
        if os.path.exists(src): shutil.copy(src, TMP/("wpn.db"+suf))
        elif os.path.exists(TMP/("wpn.db"+suf)): os.remove(TMP/("wpn.db"+suf))
    shm = TMP/"wpn.db-shm"
    if shm.exists(): shm.unlink()
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

state = {"picks": [], "league": "", "leagues": {}, "newest": "", "updated": 0, "managers": []}
state_lock = threading.Lock()  # poll() writes, request threads serialize — never race
ignore = set()  # notification IDs to skip — a baseline written by --reset / reset_cache.py so
                # stale toasts still in Windows' history don't reappear as picks
# read-health: the board can't tell a live-but-broken helper from a healthy idle one
# by looking at /drafted.json (it just goes stale). /health exposes this instead.
health = {"lastReadOk": None, "lastReadAt": 0, "errors": 0, "lastError": ""}

def poll(db, me, seen):
    last_beat = time.time(); last_err_print = 0.0
    while True:
        try:
            toasts = read_toasts(db)
            health["lastReadOk"] = True; health["lastReadAt"] = time.time()
            managers = set()
            for nid, arr, title, body in toasts:
                m = re.match(r"(.+?) drafted by (.+)$", body)
                if not m: continue
                name, mgr = m.group(1).strip(), m.group(2).strip()
                nid = str(nid)
                if nid in ignore: continue  # baseline reset: skip toasts that existed at reset time
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
                            first_title = next((r["title"] for r in seen.values() if r.get("title")), "")
                            seen[key] = {"name": rec["name"], "mgr": rec.get("by",""), "title": rec.get("title") or first_title, "arr": -1_000_000 + i}
                except Exception as e:
                    print("backfill error:", e, flush=True)
            # one pick list per league (toast title = "<League> Draft"); several drafts can run at once
            leagues = {}
            for nid, rec in sorted(seen.items(), key=lambda kv: kv[1]["arr"]):
                lg = (rec.get("title") or "?").replace(" Draft", "")
                nm, pos, team = rec["name"], "", ""
                dt = def_team(nm)
                if dt: pos, team = "DEF", dt
                lst = leagues.setdefault(lg, [])
                lst.append({"pick": len(lst)+1, "name": nm, "pos": pos, "team": team,
                            "mine": bool(me) and me.lower() in rec["mgr"].lower(), "by": rec["mgr"]})
            if leagues and leagues != state.get("leagues"):
                newest = max(leagues, key=lambda k: max(r["arr"] for r in seen.values() if (r.get("title") or "?").replace(" Draft","")==k))
                with state_lock:
                    state["leagues"] = leagues; state["newest"] = newest
                    state["picks"] = leagues[newest]; state["league"] = newest
                    state["updated"] = time.time()
                last = leagues[newest][-1]
                print(f"\n{time.strftime('%H:%M:%S')}  [{newest}] pick {last['pick']}: {last['name']} — {last['by']}"
                      f"{'  ★ MINE' if last['mine'] else ''}   ({len(leagues[newest])} total)", flush=True)
            with state_lock:
                state["managers"] = sorted(managers)
        except Exception as e:
            health["lastReadOk"] = False; health["errors"] += 1; health["lastError"] = str(e)
            if time.time() - last_err_print > 30:  # rate-limit: same failure shouldn't spam the console
                print(f"{time.strftime('%H:%M:%S')}  poll error ({health['errors']} total): {e}", flush=True)
                last_err_print = time.time()
        # ~30s heartbeat so a quiet console still proves the reader is alive
        if time.time() - last_beat >= 30:
            ok = "reads OK" if health["lastReadOk"] else f"READS FAILING ({health['lastError']})"
            print(f"{time.strftime('%H:%M:%S')}  heartbeat — {ok}; {len(state['picks'])} picks"
                  f"{' ['+state['league']+']' if state['league'] else ''}, {len(state['managers'])} managers", flush=True)
            last_beat = time.time()
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self):  # Chrome local-network-access preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            # serve the board itself, same origin as the feed: no browser permission prompts
            page = pathlib.Path(__file__).parent.parent/"dist"/"index.html"
            body = page.read_bytes() if page.exists() else b"dist/index.html not built"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(body); return
        if self.path == "/health":
            with state_lock:
                body = json.dumps({"ok": health["lastReadOk"] is not False,
                                   "lastReadOk": health["lastReadOk"], "lastReadAt": health["lastReadAt"],
                                   "errors": health["errors"], "lastError": health["lastError"],
                                   "picks": len(state["picks"]), "league": state["league"],
                                   "leagues": len(state["leagues"]), "managers": len(state["managers"]),
                                   "updated": state["updated"], "baselined": len(ignore),
                                   "pid": os.getpid()}).encode()
        elif self.path == "/drafted.json":
            with state_lock:
                body = json.dumps(state).encode()
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--me", default="", help="substring of your Yahoo manager name (marks your picks ★)")
    ap.add_argument("--reset", action="store_true",
                    help="start fresh: baseline every draft toast currently in Windows' history so it is ignored; only new picks will appear")
    a = ap.parse_args()
    if not a.db or not os.path.exists(a.db): sys.exit(f"notification db not found: {a.db!r}")
    PRIV = pathlib.Path(__file__).parent.parent/"data_private"
    PRIV.mkdir(exist_ok=True)  # fresh clones don't have it; persist would error every 5s
    SEEN_FILE = PRIV/"toast_seen.json"
    BASELINE_FILE = PRIV/"toast_baseline.json"
    if a.reset:
        # Windows keeps old draft toasts in its history and we re-read them on every start —
        # deleting toast_seen.json alone never helped. Baseline them instead: every draft
        # toast that exists right now becomes invisible; only genuinely new picks show up.
        ids = [str(nid) for nid, *_ in read_toasts(a.db)]
        json.dump(ids, open(BASELINE_FILE, "w"))
        if SEEN_FILE.exists(): SEEN_FILE.unlink()
        print(f"reset: baselined {len(ids)} old draft toasts; starting with an empty feed", flush=True)
    if BASELINE_FILE.exists():
        try: ignore.update(json.load(open(BASELINE_FILE)))
        except Exception as e: print("baseline load error:", e, flush=True)
    seen = json.load(open(SEEN_FILE)) if SEEN_FILE.exists() else {}
    # drop anything baselined out (covers a baseline written while an old helper was running)
    seen = {k: v for k, v in seen.items() if k not in ignore}
    def persist():
        while True:
            time.sleep(5)
            try: json.dump(seen, open(SEEN_FILE, "w"))
            except Exception as e: print("persist error:", e, flush=True)
    threading.Thread(target=persist, daemon=True).start()
    threading.Thread(target=poll, args=(a.db, a.me, seen), daemon=True).start()
    time.sleep(1.5)
    print(f"toast sync: {len(state['picks'])} picks so far; managers seen: {state['managers']}")
    print(f"open the board at http://127.0.0.1:{PORT}/  (feed: /drafted.json, liveness: /health)", flush=True)
    # ThreadingHTTPServer: serve concurrent pollers (board + extension + any watcher)
    # without stalling; single-threaded HTTPServer would serialize and time out under load.
    class Server(ThreadingHTTPServer):
        # HTTPServer defaults allow_reuse_address=1; on Windows SO_REUSEADDR lets a SECOND
        # process "successfully" bind a live port, so the in-use case never raised. Disable
        # it and also probe-connect first for a clear message.
        allow_reuse_address = False
    _probe = socket.socket(); _probe.settimeout(1)
    _in_use = _probe.connect_ex(("127.0.0.1", PORT)) == 0
    _probe.close()
    if _in_use:
        sys.exit(f"port {PORT} is already serving — a helper is running.\n"
                 f"Open the board at http://127.0.0.1:{PORT}/ or stop the other instance first "
                 f"(only ever run ONE helper).")
    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        sys.exit(f"could not bind port {PORT} (in use or blocked) — stop the other instance and retry.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.", flush=True)
