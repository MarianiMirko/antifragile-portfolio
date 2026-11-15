"""html_kit.py - minimal helpers to write a self-contained HTML report."""
import html as _h

CSS = """
:root{--bg:#f9f9f7;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#dddcd6;--ok:#0a6b0a;--warn:#8a5a00;--bad:#b02a2a}
@media (prefers-color-scheme:dark){:root{--bg:#0d0d0d;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#383835;--ok:#4cc24c;--warn:#fab219;--bad:#ef7a7a}}
body{background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:0;padding:24px 16px}
main{max-width:980px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
p,li{color:var(--ink)}.meta{color:var(--ink2);font-size:13px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}.tile .k{color:var(--ink2);font-size:12px}.tile .v{font-size:22px;font-weight:600}
.tile .s{font-size:12px;color:var(--ink2)}.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}img{max-width:100%;background:#fff;border:1px solid var(--line);border-radius:8px}
.OK{color:var(--ok);font-weight:700}.WARNING{color:var(--warn);font-weight:700}.BREACH{color:var(--bad);font-weight:700}.note{color:var(--ink2);font-size:13px}
"""


def esc(x):
    return _h.escape(str(x), quote=False)


def table(df, status=False):
    th = "".join(f"<th>{esc(c)}</th>" for c in df.columns); rows = []
    for r in df.itertuples(index=False):
        tds = "".join(f'<td class="{v}">{v}</td>' if status and v in ("OK", "WARNING", "BREACH") else f"<td>{esc(v)}</td>" for v in r)
        rows.append(f"<tr>{tds}</tr>")
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>' + "\n".join(rows) + "</tbody></table></div>"


def tile(k, v, s):
    return f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'


def page(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")
