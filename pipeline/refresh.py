"""One-command refresh: fetch the free sources, rebuild data.json, rebuild dist/index.html.

Each fetch step is best-effort — if a source is unreachable, build_data.py carries the
last-known values forward so the board still rebuilds. The build steps are required.

    python pipeline/refresh.py

Uses the same interpreter it's launched with (so `python`, not the missing `python3`).
"""
import subprocess, sys, pathlib

HERE = pathlib.Path(__file__).parent
PY = sys.executable

def run(script, required=False):
    print(f"\n=== {script} ===", flush=True)
    code = subprocess.run([PY, str(HERE / script)], cwd=HERE).returncode
    if code != 0:
        msg = f"{script} exited {code}"
        if required:
            sys.exit(f"FATAL: {msg}")
        print(f"  (non-fatal: {msg} - continuing; build_data will carry values forward)", flush=True)
    return code

# free, no-key fetchers (best-effort)
run("fetch_borischen.py")     # FantasyPros ECR ranks + tiers
run("fetch_sleeper.py")       # injury flags + scratch suggestions
run("fetch_subvertadown.py")  # SubD value board (may fail if the scrape breaks)
# build (required); build_proj is safe without the xlsx (won't clobber a good proj.json)
run("build_proj.py")
run("build_data.py", required=True)
run("build.py", required=True)
print("\nrefresh complete.", flush=True)
