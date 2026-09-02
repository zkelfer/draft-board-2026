"""Smoke test for the data pipeline: valid JSON in, clean build out."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PIPELINE = ROOT / "pipeline"
DIST_INDEX = ROOT / "dist" / "index.html"


def test_data_json_valid_and_sane():
    data = json.loads((PIPELINE / "data.json").read_text())
    assert isinstance(data, list)
    assert len(data) > 0
    player = data[0]
    for key in ("id", "name", "pos", "team", "r"):
        assert key in player
    assert isinstance(player["r"], dict)


def test_proj_json_valid_and_sane():
    proj = json.loads((PIPELINE / "proj.json").read_text())
    assert isinstance(proj, dict)
    assert "players" in proj
    assert isinstance(proj["players"], dict)
    assert len(proj["players"]) > 0


def test_build_produces_clean_html():
    subprocess.run([sys.executable, "build.py"], cwd=PIPELINE, check=True)
    assert DIST_INDEX.exists()
    html = DIST_INDEX.read_text()
    for placeholder in ("__DATA__", "__PROJ__", "__ASOF__"):
        assert placeholder not in html
