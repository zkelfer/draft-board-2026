"""Smoke tests: valid JSON in, clean build out, joins intact, fetch guards sane.

Run with:  python -m pytest tests/   (pip install -r requirements-dev.txt first)
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PIPELINE = ROOT / "pipeline"
DIST_INDEX = ROOT / "dist" / "index.html"

sys.path.insert(0, str(PIPELINE))
import fetch_borischen  # noqa: E402
from names import name_key  # noqa: E402


def test_data_json_valid_and_sane():
    data = json.loads((PIPELINE / "data.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0
    player = data[0]
    for key in ("id", "name", "pos", "team", "r"):
        assert key in player
    assert isinstance(player["r"], dict)


def test_proj_json_valid_and_sane():
    proj = json.loads((PIPELINE / "proj.json").read_text(encoding="utf-8"))
    assert isinstance(proj, dict)
    assert "players" in proj
    assert isinstance(proj["players"], dict)
    assert len(proj["players"]) > 0


def test_build_produces_clean_html():
    subprocess.run([sys.executable, "build.py"], cwd=PIPELINE, check=True)
    assert DIST_INDEX.exists()
    # dist contains non-ASCII glyphs (star/x/emoji) — must read as UTF-8, never cp1252
    html = DIST_INDEX.read_text(encoding="utf-8")
    for placeholder in ("__DATA__", "__PROJ__", "__DATES__", "__ASOF__"):
        assert placeholder not in html


def test_name_keys_are_canonical():
    """Every stored player id must be a fixed point of name_key — if the normalizer
    drifts (alias edits, new stripping rules), stored ids stop matching live joins."""
    data = json.loads((PIPELINE / "data.json").read_text(encoding="utf-8"))
    bad = [p["id"] for p in data
           if not p["id"].startswith("def_") and name_key(p["id"]) != p["id"]]
    assert bad == [], f"ids no longer canonical under name_key: {bad[:5]}"


def test_projection_join_coverage():
    """Most skill-position board players should join a projection row (VAL column).
    A big drop means the rank<->projection join regressed."""
    data = json.loads((PIPELINE / "data.json").read_text(encoding="utf-8"))
    proj = json.loads((PIPELINE / "proj.json").read_text(encoding="utf-8"))
    keys = set(proj["players"])
    skill = [p for p in data if p["pos"] in ("QB", "RB", "WR", "TE")]
    joined = sum(1 for p in skill if p["id"] in keys)
    assert joined / len(skill) >= 0.8, f"only {joined}/{len(skill)} skill players join projections"


FIXTURE_CSV = '"Rank","Player.Name","Tier","Position","Best.Rank","Worst.Rank","Avg.Rank","Std.Dev"\n' + "\n".join(
    f'{i},"Player {i}","{(i - 1) // 12 + 1}","{pos}",{i},{i + 6},{i + 2}.1,1.5'
    for i, pos in enumerate(
        (["QB"] * 25 + ["RB"] * 55 + ["WR"] * 60 + ["TE"] * 25 + ["K"] * 5 + ["DST"] * 5), start=1)
)


def test_borischen_parse_fixture():
    board = fetch_borischen._parse(FIXTURE_CSV)
    # K/DST filtered; QB/RB/WR/TE kept with rank/tier/pos/dispersion
    assert len(board) == 165
    one = board[name_key("Player 1")]
    assert one["r"] == 1 and one["t"] == 1 and one["p"] == "QB"
    assert one["lo"] == 1 and one["hi"] == 7 and one["sd"] == 1.5
    assert fetch_borischen.looks_like_draft_board(board)


def test_borischen_season_guard():
    assert not fetch_borischen.season_started(datetime.date(2026, 9, 6))
    assert fetch_borischen.season_started(datetime.date(2026, 9, 10))
    assert fetch_borischen.season_started(datetime.date(2026, 10, 1))
    # a thin, QB-poor list (weekly mode) must fail the shape check
    thin = {f"p{i}": {"r": i, "t": 1, "p": "RB", "lo": i, "hi": i, "sd": 1.0} for i in range(40)}
    assert not fetch_borischen.looks_like_draft_board(thin)
