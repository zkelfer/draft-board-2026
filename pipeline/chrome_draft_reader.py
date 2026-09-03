"""FALLBACK draft sync: scrape the live Yahoo draft room out of Chrome via CDP.

Use this when the Yahoo Fantasy API can't see the draft (e.g. mock drafts).
It attaches to the user's already-running Chrome through the Chrome DevTools
Protocol, runs a scraping JS expression in the draft-room tab every 10s, and
serves the picks at http://127.0.0.1:8737/drafted.json with CORS — the exact
same shape yahoo_sync.py serves, so the board's "Yahoo sync" button works
unchanged:

    {"picks":[{"pick":int,"name":str,"pos":str,"team":str,"mine":bool}],
     "league":str, "updated":ts}

Setup on this machine (WSL2 + Windows Chrome, mirrored networking — verified):

 1. On WINDOWS, quit Chrome fully, then start it with the debug port
    (PowerShell; the separate --user-data-dir is required by modern Chrome
    for remote debugging, and you must log in to Yahoo in that profile):

      & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
        --remote-debugging-port=9222 `
        --user-data-dir="$env:LOCALAPPDATA\\ChromeDebugProfile"

 2. Open the Yahoo draft room in that Chrome window.

 3. In WSL:  python3 pipeline/chrome_draft_reader.py
    (mirrored networking means WSL's 127.0.0.1 reaches Windows loopback,
    where Chrome binds the port; no portproxy needed on this box).

IMPORTANT — UNTESTED AGAINST THE LIVE DRAFT DOM. Yahoo's draft-room markup
is unknown, so the scraping JS (SCRAPE_JS below) uses several defensive
strategies: player-page links (/nfl/players/), "Pick N" text, position
abbreviations (QB|RB|WR|TE|K|DEF) and NFL team codes, and "mine" detection
via row classes/data attributes matching mine|owner|self|you|my-team.
Before trusting it, run once with --probe while the draft room is open:

    python3 pipeline/chrome_draft_reader.py --probe

That prints the page's visible text (first 4000 chars) and the 30 most
repeated CSS class names — enough to see what the real rows look like and
adjust SCRAPE_JS (the row selectors and the "mine" regex) in minutes.

Stdlib only: includes a minimal RFC 6455 websocket client (text frames,
client-side masking, ping/pong) sufficient for CDP Runtime.evaluate.
"""
import argparse, base64, json, os, socket, struct, sys, threading, time
import urllib.parse, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

SERVE_HOST, SERVE_PORT = "127.0.0.1", 8737
DEFAULT_INTERVAL = 10


# ---------------------------------------------------------------- websocket
class WebSocket:
    """Minimal RFC 6455 client: enough to talk CDP on localhost.

    Sends masked text frames; reassembles fragmented incoming messages;
    answers pings with pongs; raises ConnectionError on close/EOF.
    """

    def __init__(self, url, timeout=60):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "ws":
            raise ValueError(f"expected ws:// url, got {url}")
        host, port = u.hostname, u.port or 80
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (("?" + u.query) if u.query else "")
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake: connection closed")
            resp += chunk
        head, _, leftover = resp.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 101" not in status:
            raise ConnectionError("websocket handshake failed: "
                                  + status.decode(errors="replace"))
        self.buf = leftover  # bytes past the handshake are frame data

    def _read_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket: connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 1 << 16:
            header.append(0x80 | 126); header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127); header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header)
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_text(self, text):
        self._send_frame(0x1, text.encode())

    def recv_text(self):
        message = b""
        while True:
            b1, b2 = self._read_exact(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            masked, ln = b2 & 0x80, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(ln)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:                       # close
                raise ConnectionError("websocket closed by peer")
            if opcode == 0x9:                       # ping -> pong
                self._send_frame(0xA, payload); continue
            if opcode == 0xA:                       # pong
                continue
            if opcode in (0x0, 0x1, 0x2):           # data / continuation
                message += payload
                if fin:
                    return message.decode("utf-8", errors="replace")

    def close(self):
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------- CDP
_msg_id = 0

def cdp_eval(ws, expression, timeout=30):
    """Run Runtime.evaluate(returnByValue) and return the JS value."""
    global _msg_id
    _msg_id += 1
    ws.send_text(json.dumps({"id": _msg_id, "method": "Runtime.evaluate",
                             "params": {"expression": expression,
                                        "returnByValue": True}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = json.loads(ws.recv_text())
        if msg.get("id") != _msg_id:
            continue                                # stray CDP event
        if "error" in msg:
            raise RuntimeError(f"CDP error: {msg['error']}")
        res = msg.get("result", {})
        if res.get("exceptionDetails"):
            raise RuntimeError("page JS threw: "
                               + json.dumps(res["exceptionDetails"])[:600])
        return res.get("result", {}).get("value")
    raise TimeoutError("no CDP response")


def list_targets(host, port):
    url = f"http://{host}:{port}/json"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def find_draft_target(targets):
    for t in targets:
        url = (t.get("url") or "").lower()
        if (t.get("type") == "page" and "fantasysports.yahoo.com" in url
                and "draft" in url):
            return t
    return None


# --------------------------------------------------------------- scraping JS
# UNTESTED against the live draft room — refine with --probe (see docstring).
SCRAPE_JS = r"""
(() => {
  const POS   = /\b(QB|RB|WR|TE|K|DEF|DST)\b/;
  const TEAMS = /\b(ARI|ATL|BAL|BUF|CAR|CHI|CIN|CLE|DAL|DEN|DET|GB|HOU|IND|JAX|JAC|KC|LAC|LAR|LV|MIA|MIN|NE|NO|NYG|NYJ|PHI|PIT|SEA|SF|TB|TEN|WAS|WSH)\b/;
  const MINE  = /(^|[\s_-])(mine|owner|self|you|yours|my-?team)([\s_-]|$)/i;
  const cls = (el) => (el && el.getAttribute && el.getAttribute('class')) || '';

  const rowOf = (el) => {
    let n = el;
    for (let i = 0; n && n !== document.body && i < 8; i++) {
      if (n.tagName === 'TR' || n.tagName === 'LI') return n;
      if (/(^|[\s_-])(pick|player|row|result|selection)/i.test(cls(n))) return n;
      n = n.parentElement;
    }
    n = el;  // fallback: first ancestor that is one of several siblings
    for (let i = 0; n && n.parentElement && n.parentElement !== document.body && i < 8; i++) {
      if (n.parentElement.children.length >= 3) return n;
      n = n.parentElement;
    }
    return el.parentElement || el;
  };

  const isMine = (row) => {
    let n = row;
    for (let i = 0; n && i < 4; i++) {
      if (MINE.test(cls(n))) return true;
      if (n.attributes)
        for (const a of n.attributes)
          if (MINE.test(a.name) || (a.name.indexOf('data-') === 0 && MINE.test(a.value)))
            return true;
      n = n.parentElement;
    }
    if (row.querySelectorAll)
      for (const el of row.querySelectorAll('[class]'))
        if (MINE.test(cls(el))) return true;
    return false;
  };

  const parse = (row, name) => {
    const text = ((row.innerText || row.textContent) || '').replace(/\s+/g, ' ').trim();
    let pick = 0, pos = '', team = '', m;
    m = text.match(/(?:Pick|#)\s*0*(\d{1,3})\b/i) || text.match(/^0*(\d{1,3})[.):\s]/);
    if (m) pick = parseInt(m[1], 10);
    m = text.match(/\b([A-Za-z]{2,3})\s*[-\u2013\u2014]\s*(QB|RB|WR|TE|K|DEF|DST)\b/i);
    if (m) { team = m[1]; pos = m[2]; }
    if (!pos) {
      m = text.match(/\b(QB|RB|WR|TE|K|DEF|DST)\s*[-\u2013\u2014]\s*([A-Za-z]{2,3})\b/i);
      if (m) { pos = m[1]; team = m[2]; }
    }
    if (!pos)  { m = text.match(POS);   if (m) pos = m[1]; }
    if (!team) { m = text.match(TEAMS); if (m) team = m[1]; }
    pos = pos.toUpperCase().replace('DST', 'DEF');
    return { pick: pick, name: name, pos: pos, team: team.toUpperCase(),
             mine: isMine(row) };
  };

  const picks = [], seen = new Set();
  const add = (rec) => {
    const k = rec.name.toLowerCase();
    if (rec.name && !seen.has(k)) { seen.add(k); picks.push(rec); }
  };

  // Strategy 1: links to player pages are the most reliable anchor.
  for (const a of document.querySelectorAll('a[href*="/nfl/players/"]')) {
    const name = ((a.innerText || a.textContent) || '').replace(/\s+/g, ' ').trim();
    if (name.length < 3 || name.length > 40 || !/[A-Za-z]{2}/.test(name)) continue;
    add(parse(rowOf(a), name));
  }

  // Strategy 2: pick/result-ish rows containing a position abbreviation.
  if (picks.length === 0) {
    const rows = document.querySelectorAll(
      "[class*='pick' i], [class*='result' i], [class*='selection' i], li, tr");
    for (const row of rows) {
      const text = ((row.innerText || '') + '').replace(/\s+/g, ' ').trim();
      if (!text || text.length > 160 || !POS.test(text)) continue;
      if (row.querySelector && row.querySelector('li, tr')) continue; // leaves only
      const m = text.match(/([A-Z][\w.'-]+(?: [A-Z][\w.'-]+){1,2})/);
      if (!m) continue;
      add(parse(row, m[1]));
    }
  }

  const numbered = picks.filter(p => p.pick > 0).length;
  if (numbered >= picks.length / 2)
    picks.sort((a, b) => (a.pick || 9999) - (b.pick || 9999));
  picks.forEach((p, i) => { if (!p.pick) p.pick = i + 1; });

  let league = '';
  const lg = document.querySelector(
    "[class*='league' i] h1, [class*='league' i] h2, [class*='leaguename' i], header h1");
  if (lg) league = (lg.innerText || '').trim();
  if (!league)
    league = (document.title || '').replace(/ [|\u2013-] Yahoo.*$/i, '').trim();
  return { picks: picks, league: league };
})()
"""

PROBE_JS = r"""
(() => {
  const counts = {};
  for (const el of document.querySelectorAll('*')) {
    const cn = (el.getAttribute && el.getAttribute('class')) || '';
    for (const c of cn.split(/\s+/)) if (c) counts[c] = (counts[c] || 0) + 1;
  }
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 30);
  return { url: location.href, title: document.title, topClasses: top,
           text: ((document.body && document.body.innerText) || '').slice(0, 4000) };
})()
"""


# ------------------------------------------------------------------- server
state = {"picks": [], "league": "", "updated": 0}

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
        self.end_headers()
        self.wfile.write(body)


# --------------------------------------------------------------------- main
def connect_to_draft(host, port):
    """Find the draft tab and return an attached WebSocket (or raise)."""
    targets = list_targets(host, port)
    t = find_draft_target(targets)
    if not t:
        pages = [x.get("url", "?") for x in targets if x.get("type") == "page"]
        raise LookupError(
            "no tab with fantasysports.yahoo.com + 'draft' in its URL.\n"
            "Open tabs:\n  " + ("\n  ".join(pages) or "(none)"))
    print(f"attached to: {t.get('title', '?')!r}  {t.get('url', '?')}")
    return WebSocket(t["webSocketDebuggerUrl"])


def normalize(value):
    picks = []
    for p in (value or {}).get("picks", []):
        try:
            picks.append({"pick": int(p.get("pick", 0)),
                          "name": str(p.get("name", "")).strip(),
                          "pos": str(p.get("pos", "")).strip(),
                          "team": str(p.get("team", "")).strip(),
                          "mine": bool(p.get("mine", False))})
        except (TypeError, ValueError):
            continue
    return picks, str((value or {}).get("league", "")).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--host", default="127.0.0.1",
                    help="Chrome debug host (default 127.0.0.1; on mirrored-"
                         "networking WSL2 this reaches Windows Chrome)")
    ap.add_argument("--port", type=int, default=9222,
                    help="Chrome --remote-debugging-port (default 9222)")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help=f"seconds between scrapes (default {DEFAULT_INTERVAL})")
    ap.add_argument("--probe", action="store_true",
                    help="dump page text + top 30 CSS classes once, then exit "
                         "(use this to adapt SCRAPE_JS to the real DOM)")
    args = ap.parse_args()

    try:
        ws = connect_to_draft(args.host, args.port)
    except (OSError, LookupError) as e:
        print(f"cannot attach to Chrome at {args.host}:{args.port} — {e}\n\n"
              "Is Chrome running with --remote-debugging-port=9222 on Windows?\n"
              "PowerShell:\n"
              '  & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
              '--remote-debugging-port=9222 '
              '--user-data-dir="$env:LOCALAPPDATA\\ChromeDebugProfile"')
        sys.exit(1)

    if args.probe:
        v = cdp_eval(ws, PROBE_JS) or {}
        print(f"\nURL:    {v.get('url')}\nTitle:  {v.get('title')}\n")
        print("Top 30 classes (name, count):")
        for name, count in v.get("topClasses", []):
            print(f"  {count:5d}  {name}")
        print("\n---- body.innerText (first 4000 chars) ----")
        print(v.get("text", ""))
        ws.close()
        return

    try:
        srv = HTTPServer((SERVE_HOST, SERVE_PORT), Handler)
    except OSError as e:
        print(f"cannot bind {SERVE_HOST}:{SERVE_PORT} ({e}) — "
              "is yahoo_sync.py already running? Stop it first; "
              "this script serves the same endpoint.")
        sys.exit(1)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"serving http://{SERVE_HOST}:{SERVE_PORT}/drafted.json — "
          "click 'Yahoo sync' on the board.")

    while True:
        try:
            picks, league = normalize(cdp_eval(ws, SCRAPE_JS))
            state["picks"], state["updated"] = picks, time.time()
            if league:
                state["league"] = league
            print(f"\r{time.strftime('%H:%M:%S')}  {len(picks)} picks "
                  f"({sum(1 for p in picks if p['mine'])} mine)   ",
                  end="", flush=True)
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
            print(f"\nscrape failed ({e}); reattaching in {args.interval}s...")
            try:
                ws.close()
            except OSError:
                pass
            time.sleep(args.interval)
            try:
                ws = connect_to_draft(args.host, args.port)
            except (OSError, LookupError) as e2:
                print(f"reattach failed: {e2}")
            continue
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
