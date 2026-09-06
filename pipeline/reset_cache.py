"""Strip every cached draft pick so the board starts empty. One command:

    python pipeline/reset_cache.py

What it clears (the three places stale picks hide):
  1. Windows' notification history — can't be deleted safely, so every draft toast
     that exists right now is BASELINED into data_private/toast_baseline.json; the
     helper ignores baselined toasts forever. Only genuinely new picks will show.
  2. data_private/toast_seen.json — the helper's own pick cache. Deleted.
  3. The browser extension's cached room + the board's marks — a script can't reach
     inside Chrome, but the board's "Clear this draft" button now does both (it wipes
     the extension cache and turns Sync off). This script reminds you of that step.

If the helper is running it must be restarted to pick up the baseline (this script
tells you if so). Equivalent one-shot: start the helper with `--reset`.
"""
import json, pathlib, sys, urllib.request, urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from toast_sync import read_toasts, DEFAULT_DB, PORT

PRIV = pathlib.Path(__file__).parent.parent / "data_private"
PRIV.mkdir(exist_ok=True)
BASELINE_FILE = PRIV / "toast_baseline.json"
SEEN_FILE = PRIV / "toast_seen.json"

def helper_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2):
            return True
    except urllib.error.HTTPError:
        return True   # something answered (an older helper without /health) — still running
    except OSError:
        return False

def main():
    if not DEFAULT_DB:
        sys.exit("notification db not found — is this a Windows machine?")
    ids = [str(nid) for nid, *_ in read_toasts(DEFAULT_DB)]
    json.dump(ids, open(BASELINE_FILE, "w"))
    print(f"1) baselined {len(ids)} old draft toasts -> {BASELINE_FILE.name} (helper will ignore them)")
    if SEEN_FILE.exists():
        SEEN_FILE.unlink()
        print(f"2) deleted {SEEN_FILE.name} (helper pick cache)")
    else:
        print("2) no toast_seen.json to delete (already clean)")
    if helper_running():
        print(f"3) a helper IS running on :{PORT} — RESTART it now so the baseline takes effect")
    else:
        print("3) no helper running — next launch starts with an empty feed")
    print("4) in the board tab: click \"Clear this draft\" (also wipes the extension's cached")
    print("   room and turns Sync off until you re-enable it)")

if __name__ == "__main__":
    main()
