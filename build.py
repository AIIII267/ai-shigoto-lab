"""依存ライブラリなしの静的ブログビルダー。

content/posts/*.md と content/pages/*.md を読み、docs/ に HTML を出力する。
docs/ はそのまま GitHub Pages / Cloudflare Pages に公開できる。

記事内のアフィリエイトリンク記法:  [[aff:ID|リンク文言]]
  - ID の URL は affiliate_links.json で管理する
  - URL が空ならリンクにせず文言だけ出す（ASP 承認前でも安全に公開できる）
"""
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
AFF = json.loads((ROOT / "affiliate_links.json").read_text(encoding="utf-8"))
OUT = ROOT / "docs"


def parse_front_matter(text):
    meta = {}
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        return meta, body.strip()
    return meta, text


def inline(text):
    text = html.escape(text, quote=False)

    def aff(m):
        link_id, label = m.group(1), m.group(2)
        url = AFF.get(link_id, {}).get("url", "")
        if not url:
            return label
        return f'<a href="{html.escape(url)}" rel="sponsored noopener" target="_blank">{label}</a>'

    text = re.sub(r"\[\[aff:([\w-]+)\|(.+?)\]\]", aff, text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(md):
    lines = md.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(html.escape(lines[i]))
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
            i += 1
            continue
        m = re.match(r"(#{1,4}) (.+)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            anchor = re.sub(r"\s+", "-", title.strip())
            out.append(f'<h{level} id="{html.escape(anchor)}">{inline(title)}</h{level}>')
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, *body = rows
            t = "<div class=\"table-wrap\"><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            for r in body:
                t += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table></div>")
            continue
        if line.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(inline(lines[i].lstrip("> ").rstrip()))
                i += 1
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            continue
        if re.match(r"(\s*)([-*]|\d+\.) ", line):
            ordered = bool(re.match(r"\d+\.", line.strip()))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and re.match(r"([-*]|\d+\.) ", lines[i].strip()):
                items.append(re.sub(r"^([-*]|\d+\.) ", "", lines[i].strip()))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||>|```|[-*] |\d+\. )", lines[i].strip()):
            para.append(inline(lines[i].strip()))
            i += 1
        out.append("<p>" + "<br>".join(para) + "</p>")
    return "\n".join(out)


def layout(title, description, body, path):
    site = CONFIG["site_name"]
    full_title = site if title == site else f"{title} | {site}"
    canonical = CONFIG["site_url"].rstrip("/") + "/" + path
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{html.escape(canonical)}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{'../' * path.count('/')}style.css">
</head>
<body>
<header class="site-header"><a class="brand" href="{'../' * path.count('/')}index.html">{html.escape(site)}</a>
<nav><a href="{'../' * path.count('/')}about.html">運営者情報</a><a href="{'../' * path.count('/')}disclosure.html">広告について</a><a href="{'../' * path.count('/')}privacy.html">プライバシー</a><a href="{html.escape(CONFIG['contact_url'])}" target="_blank" rel="noopener">お問い合わせ</a></nav></header>
<main>{body}</main>
<footer>© {date.today().year} {html.escape(site)}　|　当サイトはアフィリエイトプログラムに参加しています。</footer>
</body>
</html>"""


def build():
    OUT.mkdir(exist_ok=True)
    (OUT / "posts").mkdir(exist_ok=True)
    (OUT / "style.css").write_text((ROOT / "style.css").read_text(encoding="utf-8"), encoding="utf-8")

    posts = []
    for f in sorted((ROOT / "content/posts").glob("*.md")):
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        if meta.get("draft") == "true":
            continue
        slug = f.stem
        pr = '<p class="pr">※本記事にはアフィリエイト広告（PR）が含まれています。</p>'
        article = (
            f'<article><p class="meta">{meta["date"]}{"（更新 " + meta["updated"] + "）" if meta.get("updated") else ""}</p>'
            f'<h1>{inline(meta["title"])}</h1>{pr}{md_to_html(body)}</article>'
        )
        (OUT / "posts" / f"{slug}.html").write_text(
            layout(meta["title"], meta.get("description", ""), article, f"posts/{slug}.html"), encoding="utf-8")
        posts.append((meta, slug))

    for f in sorted((ROOT / "content/pages").glob("*.md")):
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        page = f'<article><h1>{inline(meta["title"])}</h1>{md_to_html(body)}</article>'
        (OUT / f"{f.stem}.html").write_text(layout(meta["title"], meta.get("description", ""), page, f"{f.stem}.html"), encoding="utf-8")

    posts.sort(key=lambda p: p[0]["date"], reverse=True)
    cards = "".join(
        f'<li class="card"><a href="posts/{slug}.html"><span class="meta">{m["date"]}</span>'
        f'<strong>{html.escape(m["title"])}</strong><span>{html.escape(m.get("description", ""))}</span></a></li>'
        for m, slug in posts)
    index = f'<section class="hero"><h1>{html.escape(CONFIG["site_name"])}</h1><p>{html.escape(CONFIG["tagline"])}</p></section><ul class="cards">{cards}</ul>'
    (OUT / "index.html").write_text(layout(CONFIG["site_name"], CONFIG["tagline"], index, "index.html"), encoding="utf-8")

    base = CONFIG["site_url"].rstrip("/")
    urls = [f"{base}/index.html"] + [f"{base}/posts/{s}.html" for _, s in posts]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
    (OUT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    print(f"built {len(posts)} posts -> {OUT}")


if __name__ == "__main__":
    build()
