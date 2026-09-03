"""Local monitor for the Draft Board Sync extension.

The extension POSTs its scrape results, DOM probe, and the board's match
status to http://127.0.0.1:8738/report. Everything is appended to
data_private/sync_log.jsonl and the latest report of each kind is kept in
data_private/sync_latest.json — so a terminal session can watch how the
sync is doing during a live draft without access to the browser.

    python3 pipeline/sync_monitor.py
"""
import json, time, pathlib
from http.server import HTTPServer, BaseHTTPRequestHandler

PRIV = pathlib.Path(__file__).parent.parent/"data_private"
LOG, LATEST = PRIV/"sync_log.jsonl", PRIV/"sync_latest.json"
PORT = 8738
latest = {}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def do_GET(self):
        body = json.dumps(latest).encode()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            rep = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            rep = {"kind": "bad-json"}
        rep["received"] = time.strftime("%Y-%m-%d %H:%M:%S")
        PRIV.mkdir(exist_ok=True)
        with open(LOG, "a") as f: f.write(json.dumps(rep) + "\n")
        latest[rep.get("kind", "?")] = rep
        json.dump(latest, open(LATEST, "w"), indent=1)
        print(f"{rep['received']}  {rep.get('kind','?'):8s} "
              f"{('picks='+str(len(rep.get('picks',[]))) if 'picks' in rep else rep.get('status', rep.get('title',''))[:80])}", flush=True)
        self.send_response(204); self._cors(); self.end_headers()

if __name__ == "__main__":
    print(f"sync monitor on http://127.0.0.1:{PORT}/report -> {LOG}", flush=True)
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
