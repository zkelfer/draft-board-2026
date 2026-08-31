"""Build dist/index.html from template.html + data.json. Run build_data.py first if sources changed."""
import json, datetime, pathlib
here = pathlib.Path(__file__).parent
data = json.load(open(here/"data.json"))
html = open(here/"template.html").read()
asof = datetime.date.today().strftime("%b %-d, %Y")
html = html.replace("__DATA__", json.dumps(data, separators=(",",":"))).replace("__ASOF__", asof)
out = here.parent/"dist"/"index.html"
out.write_text(html)
print(f"wrote {out} ({len(html)//1024} KB, {len(data)} players)")
