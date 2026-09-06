"""Build dist/index.html from template.html + data.json. Run build_data.py first if sources changed."""
import json, datetime, pathlib
here = pathlib.Path(__file__).parent
# Explicit utf-8 everywhere: the template/data carry non-ASCII glyphs (★ ✕ — ▲),
# and Windows would otherwise default to cp1252 and fail to read/write them.
data = json.loads((here/"data.json").read_text(encoding="utf-8"))
proj = json.loads((here/"proj.json").read_text(encoding="utf-8")) if (here/"proj.json").exists() else None
html = (here/"template.html").read_text(encoding="utf-8")
_today = datetime.date.today()
asof = f"{_today:%b} {_today.day}, {_today.year}"  # cross-platform (Windows has no %-d)
html = (html.replace("__DATA__", json.dumps(data, separators=(",",":")))
            .replace("__PROJ__", json.dumps(proj, separators=(",",":")))
            .replace("__ASOF__", asof))
out = here.parent/"dist"/"index.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({len(html)//1024} KB, {len(data)} players)")
