"""Draft-day companion: mirror Yahoo draft picks to the dashboard.

Run this on the machine you draft from, alongside the board (hosted or local):

    python3 pipeline/yahoo_sync.py

It authenticates with the Yahoo Fantasy Sports API (one-time OAuth, tokens
cached in data_private/), polls the league's draft results, and serves them at
http://localhost:8737/drafted.json with CORS. The board's "Yahoo sync" button
polls that URL and marks players drafted (star for your team's picks).

One-time setup (5 minutes):
 1. Create an app at https://developer.yahoo.com/apps/create/
    - Application type: Installed Application
    - API permissions: Fantasy Sports (Read)
    - Redirect URI: leave default / use oob
 2. Write data_private/yahoo_app.json:
       {"client_id": "...", "client_secret": "..."}
 3. Run this script; it prints an auth URL, you approve in a browser and
    paste the code back. Tokens refresh automatically after that.

Stdlib only. Yahoo API JSON is deeply nested; parsing here is defensive.
"""
import json, re, sys, time, base64, pathlib, threading, urllib.parse, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = pathlib.Path(__file__).parent
PRIV = HERE.parent/"data_private"
APP_FILE, TOK_FILE = PRIV/"yahoo_app.json", PRIV/"yahoo_token.json"
AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API = "https://fantasysports.yahooapis.com/fantasy/v2"
PORT = 8737
POLL_SECONDS = 12

def die(msg):
    print(msg); sys.exit(1)

def load_app():
    if not APP_FILE.exists():
        die(f"Missing {APP_FILE}. Create a Yahoo app (see docstring) and write\n"
            '{"client_id": "...", "client_secret": "..."} to that path.')
    return json.load(open(APP_FILE))

def token_request(data):
    app = load_app()
    basic = base64.b64encode(f"{app['client_id']}:{app['client_secret']}".encode()).decode()
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    tok = json.load(urllib.request.urlopen(req, timeout=30))
    tok["obtained_at"] = time.time()
    PRIV.mkdir(exist_ok=True)
    json.dump(tok, open(TOK_FILE, "w"))
    return tok

def authorize():
    app = load_app()
    redirect = app.get("redirect_uri", "oob")
    url = AUTH_URL + "?" + urllib.parse.urlencode(
        {"client_id": app["client_id"], "redirect_uri": redirect, "response_type": "code"})
    print("\nOpen this URL, approve access, and paste the code shown:\n\n  " + url + "\n")
    code = input("Code: ").strip()
    return token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect})

def get_token():
    if TOK_FILE.exists():
        tok = json.load(open(TOK_FILE))
        if time.time() - tok.get("obtained_at", 0) > tok.get("expires_in", 3600) - 120:
            try:
                tok = token_request({"grant_type": "refresh_token",
                                     "refresh_token": tok["refresh_token"], "redirect_uri": "oob"})
            except Exception as e:
                print("token refresh failed:", e); return authorize()
        return tok
    return authorize()

def api_get(path):
    tok = get_token()
    req = urllib.request.Request(f"{API}{path}?format=json",
        headers={"Authorization": f"Bearer {tok['access_token']}"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def walk(obj, key):
    """Yield every value of `key` anywhere in Yahoo's nested lists/dicts."""
    if isinstance(obj, dict):
        if key in obj: yield obj[key]
        for v in obj.values(): yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj: yield from walk(v, key)

def league_key_from_id(league_id):
    """Bare numeric id (e.g. a mock draft's 626029) -> current NFL game's league key."""
    j = api_get("/game/nfl")
    gk = next(walk(j, "game_key"))
    return f"{gk}.l.{league_id}"

def league_name(league_key):
    try:
        j = api_get(f"/league/{league_key}")
        return next(walk(j, "name"))
    except Exception:
        return league_key

def pick_league():
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        lk = league_key_from_id(sys.argv[1])
        return lk, league_name(lk)
    j = api_get("/users;use_login=1/games;game_keys=nfl/leagues")
    leagues = []
    for lg in walk(j, "league"):
        flat = {}
        for item in (lg if isinstance(lg, list) else [lg]):
            if isinstance(item, dict): flat.update(item)
        if "league_key" in flat:
            leagues.append((flat["league_key"], flat.get("name", "?"), flat.get("draft_status", "?")))
    if not leagues: die("No NFL leagues found on this Yahoo account.")
    if len(sys.argv) > 1:
        want = sys.argv[1]
        for k, n, s in leagues:
            if want in (k, n): return k, n
        die(f"League '{want}' not found. Available: {[(k,n) for k,n,_ in leagues]}")
    print("\nLeagues:")
    for i, (k, n, s) in enumerate(leagues, 1):
        print(f"  {i}. {n}  ({k}, draft {s})")
    sel = leagues[int(input("Pick #: ")) - 1]
    return sel[0], sel[1]

def my_team_key(league_key):
    j = api_get("/users;use_login=1/games;game_keys=nfl/teams")
    for tk in walk(j, "team_key"):
        if tk.startswith(league_key + ".t."): return tk
    return None

_cache = {"players": {}}  # player_key -> {name,pos,team}
def resolve_players(league_key, keys):
    missing = [k for k in keys if k not in _cache["players"]]
    for i in range(0, len(missing), 25):
        batch = ",".join(missing[i:i+25])
        j = api_get(f"/league/{league_key}/players;player_keys={batch}")
        for pl in walk(j, "player"):
            flat = {}
            def flatten(x):
                if isinstance(x, dict): flat.update({k: v for k, v in x.items() if not isinstance(v, (dict, list))}); [flatten(v) for v in x.values() if isinstance(v, (dict, list))]
                elif isinstance(x, list): [flatten(v) for v in x]
            flatten(pl)
            name = flat.get("full") or flat.get("name")
            if flat.get("player_key") and name:
                _cache["players"][flat["player_key"]] = {
                    "name": name,
                    "pos": flat.get("display_position", ""),
                    "team": (flat.get("editorial_team_abbr") or "").upper()}
    return _cache["players"]

state = {"picks": [], "league": "", "updated": 0}

def poll_loop(league_key, my_key):
    while True:
        try:
            j = api_get(f"/league/{league_key}/draftresults")
            results = []
            for dr in walk(j, "draft_result"):
                flat = {}
                for item in (dr if isinstance(dr, list) else [dr]):
                    if isinstance(item, dict): flat.update(item)
                if flat.get("player_key"):
                    results.append(flat)
            players = resolve_players(league_key, [r["player_key"] for r in results])
            state["picks"] = [{
                "pick": int(r.get("pick", 0)),
                "name": players.get(r["player_key"], {}).get("name", ""),
                "pos": players.get(r["player_key"], {}).get("pos", ""),
                "team": players.get(r["player_key"], {}).get("team", ""),
                "mine": r.get("team_key") == my_key,
            } for r in results]
            state["updated"] = time.time()
            print(f"\r{time.strftime('%H:%M:%S')}  {len(state['picks'])} picks "
                  f"({sum(1 for p in state['picks'] if p['mine'])} mine)  ", end="", flush=True)
        except Exception as e:
            print(f"\npoll error: {e}")
        time.sleep(POLL_SECONDS)

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
        if self.path != "/drafted.json":
            self.send_response(404); self.end_headers(); return
        body = json.dumps(state).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    # non-interactive auth helpers: --auth-url prints the approval URL;
    # --code <code> exchanges it for tokens and exits
    if "--auth-url" in sys.argv:
        app = load_app()
        redirect = app.get("redirect_uri", "oob")
        print(AUTH_URL + "?" + urllib.parse.urlencode(
            {"client_id": app["client_id"], "redirect_uri": redirect, "response_type": "code"}))
        sys.exit(0)
    if "--code" in sys.argv:
        code = sys.argv[sys.argv.index("--code")+1].strip()
        redirect = load_app().get("redirect_uri", "oob")
        token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect})
        print("Tokens saved to", TOK_FILE)
        sys.exit(0)
    league_key, lname = pick_league()
    mine = my_team_key(league_key)
    state["league"] = lname
    print(f"\nSyncing '{lname}' ({league_key}); my team: {mine or 'unknown'}")
    print(f"Serving http://localhost:{PORT}/drafted.json — click 'Yahoo sync' on the board.\n")
    threading.Thread(target=poll_loop, args=(league_key, mine), daemon=True).start()
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
