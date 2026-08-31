"""Scrape the subvertadown TapThatDraft board -> data_private/subvertadown_board.csv.

The page is Laravel Livewire: the initial HTML is a lazy placeholder, and the
board arrives from a follow-up XHR. We replay it: GET the page for the session
cookie, CSRF token, component snapshot and __lazyLoad payload, then POST them
to /livewire/update and parse the rendered rows out of the returned fragment.

Personal use, one fetch per run. Stdlib only.
"""
import re, csv, html, json, pathlib, urllib.request, http.cookiejar

DRAFT_URL = "https://subvertadown.com/tap-that-draft/84610fff-3dbc-4299-9708-a8a45d9cb17f?show_adp=true"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OUT = pathlib.Path(__file__).parent.parent/"data_private"/"subvertadown_board.csv"

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA)]

page = op.open(DRAFT_URL, timeout=30).read().decode()
csrf = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
snap = html.unescape(re.search(r'wire:snapshot="([^"]*)"', page).group(1))
lazy = re.search(r"__lazyLoad\('([^']+)'\)", html.unescape(page))
params = [lazy.group(1)] if lazy else []

body = json.dumps({"_token": csrf, "components": [{"snapshot": snap, "updates": {},
    "calls": [{"path": "", "method": "__lazyLoad", "params": params}]}]}).encode()
req = urllib.request.Request("https://subvertadown.com/livewire/update", data=body, headers={
    "Content-Type": "application/json", "X-Livewire": "true", "Accept": "application/json",
    "User-Agent": UA, "Referer": DRAFT_URL, "Origin": "https://subvertadown.com"})
resp = json.loads(op.open(req, timeout=30).read().decode())
board = resp["components"][0]["effects"]["html"]

starts = [m.start() for m in re.finditer(r'wire:key="player-\d+-', board)] + [len(board)]
rows = []
for a, b in zip(starts, starts[1:]):
    chunk = board[a:min(b, a+8000)]
    pid = re.search(r'player-(\d+)-', chunk).group(1)
    text = re.sub(r'<!\[CDATA\[.*?\]\]>', '', chunk, flags=re.S)
    text = re.sub(r'<[^>]+>', '|', text)
    text = re.sub(r'\s*\|\s*', '|', text)
    text = re.sub(r'\|+', '|', text)
    f = [x.strip() for x in text.split('|')
         if x.strip() and len(x) < 60 and not x.startswith(('wire:','class=','style=','x-','$','<'))]
    pick, overall, posrank, adpd, name = f[0], f[1], f[2], f[3], html.unescape(f[4])
    team, tier = f[5].rsplit('-', 1)
    bye = f[8]
    val = f[-1] if re.match(r'^-?\d+(\.\d+)?$', f[-1]) else ''
    pos = re.match(r'[A-Z]+', posrank).group(0)
    rows.append([overall, pick, pos, posrank, name, team, tier, bye, val, adpd, pid])

if len(rows) < 150:
    raise SystemExit(f"only {len(rows)} rows parsed - page layout may have changed, refusing to write")
OUT.parent.mkdir(exist_ok=True)
w = csv.writer(open(OUT, "w"))
w.writerow(["overall","pick","pos","pos_rank","name","team","tier","bye","val","adp_delta","sd_player_id"])
w.writerows(rows)
print(f"wrote {OUT} ({len(rows)} players)")
