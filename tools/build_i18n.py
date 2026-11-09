#!/usr/bin/env python3
"""PlainBTC multilingual builder.

Reads  i18n/langs.json, i18n/strings/<lang>.json, i18n/pages/<lang>/{about,disclosure}.txt,
       i18n/content/<slug>/{meta.json,links.json,<lang>.txt}
Writes <lang>/index.html, <lang>/about.html, <lang>/disclosure.html, <lang>/articles/<slug>.html,
       <lang>/feed.xml, sitemap.xml (with hreflang alternates)
Patches the hand-written English pages in place (hreflang block, language menu, footer language list,
valid JSON-LD) between <!-- i18n:... --> markers, so it is safe to run repeatedly.

Usage:
  python3 tools/build_i18n.py            # build everything
  python3 tools/build_i18n.py --check    # validate translations only (no writes)
See README ("Multilingual site").
"""
from __future__ import annotations
import html as _html
import json, re, sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://plainbtc.com"
REF_URL = "https://coinbase.com/join/F2XRWRL?src=referral-link"
CFG = json.loads((ROOT / "i18n/langs.json").read_text(encoding="utf-8"))
LANGS = CFG["langs"]
DEFAULT = CFG["default"]
LANG = {l["code"]: l for l in LANGS}
ALLOWED = r"(</?(?:strong|em|code)>|<br>)"
errors: list[str] = []
warnings: list[str] = []


# ---------------------------------------------------------------- text format
def parse_txt(path: Path):
    """-> (header dict, [block dict])"""
    raw = path.read_text(encoding="utf-8")
    head_s, _, body_s = raw.partition("\n===\n")
    head = {}
    for line in head_s.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            head[k.strip()] = v.strip()
    blocks = []
    for chunk in re.split(r"\n\s*\n", body_s.strip()):
        lines = chunk.strip().splitlines()
        if not lines:
            continue
        first = lines[0]
        if first.startswith("!takeaways"):
            blocks.append({"t": "takeaways", "items": [l[2:] for l in lines[1:] if l.startswith("- ")]})
        elif first.startswith("!figure:"):
            blocks.append({"t": "figure", "id": first.split(":", 1)[1].strip()})
        elif first.startswith("!soft:"):
            blocks.append({"t": "soft", "text": first[6:].strip()})
        elif first.startswith("!"):
            blocks.append({"t": first[1:].strip()})
        elif first.startswith("- "):
            blocks.append({"t": "ul", "items": [l[2:] for l in lines]})
        elif re.match(r"\d+\. ", first):
            blocks.append({"t": "ol", "items": [re.sub(r"^\d+\. ", "", l) for l in lines]})
        elif first.startswith("### "):
            blocks.append({"t": "h3", "text": first[4:]})
        elif first.startswith("## "):
            blocks.append({"t": "h2", "text": first[3:]})
        elif first.startswith("> "):
            blocks.append({"t": "blockquote", "text": " ".join(l[2:] if l.startswith("> ") else l for l in lines)})
        else:
            blocks.append({"t": "p", "text": " ".join(lines)})
    return head, blocks


def esc(s: str) -> str:
    return _html.escape(s, quote=False)


def esc_attr(s: str) -> str:
    return _html.escape(s, quote=True)


def esc_text(s: str) -> str:
    return "".join(p if re.fullmatch(ALLOWED, p) else esc(p) for p in re.split(ALLOWED, s))


class Page:
    """Rendering context for one language."""

    def __init__(self, lang: str, links: dict | None = None):
        self.lang = lang
        self.mode = LANG[lang]["referral"]
        self.links = links or {}

    def inline(self, text: str) -> str:
        keep = self.mode in ("full", "hedged")
        text = re.sub(r"\{\{#ref\}\}(.*?)\{\{/ref\}\}", lambda m: m.group(1) if keep else "", text, flags=re.S)
        out = []
        for tok in re.split(r"(\[[^\]]*\]\([^)\s]*\))", text):
            m = re.fullmatch(r"\[([^\]]*)\]\(([^)\s]*)\)", tok)
            if not m:
                out.append(esc_text(tok))
                continue
            label, key = m.groups()
            out.append(self.link(label, key))
        return "".join(out)

    def link(self, label: str, key: str) -> str:
        inner = esc_text(label)
        if key in ("REF", "REFD"):
            on = self.mode in ("full", "hedged") if key == "REF" else self.mode != "none"
            if not on:
                return inner
            return f'<a href="{REF_URL}" rel="sponsored noopener" target="_blank">{inner}</a>'
        if key.startswith("/"):
            return f'<a href="{internal(self.lang, key)}">{inner}</a>'
        href = self.links.get(key, key)
        if not href.startswith("http"):
            errors.append(f"[{self.lang}] unknown link key {key!r}")
        return f'<a href="{esc_attr(href)}" target="_blank" rel="noopener">{inner}</a>'


# ---------------------------------------------------------------- site model
def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def en_articles_order() -> list[str]:
    """Slugs in the order the English home page lists them (newest first)."""
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    seen = []
    for m in re.finditer(r'href="(?:articles/)?([a-z0-9-]+)\.html"', idx):
        s = m.group(1)
        if (ROOT / "articles" / f"{s}.html").exists() and s not in seen:
            seen.append(s)
    for p in sorted((ROOT / "articles").glob("*.html")):
        if p.stem not in seen:
            seen.append(p.stem)
    return seen


SLUGS = en_articles_order()
STR = {l["code"]: load_json(ROOT / "i18n/strings" / f"{l['code']}.json") for l in LANGS if (ROOT / "i18n/strings" / f"{l['code']}.json").exists()}
CONTENT: dict[str, dict] = {}   # slug -> {meta, links, <lang>: (head, blocks)}


def load_content():
    for slug in SLUGS:
        d = ROOT / "i18n/content" / slug
        if not (d / "meta.json").exists():
            warnings.append(f"no i18n source for article {slug} (run tools/i18n_extract.py {slug})")
            continue
        c = {"meta": load_json(d / "meta.json"), "links": load_json(d / "links.json")}
        figs = d / "figures.json"
        c["figures"] = {f["id"]: f for f in load_json(figs)} if figs.exists() else {}
        for l in LANGS:
            f = d / f"{l['code']}.txt"
            if f.exists():
                c[l["code"]] = parse_txt(f)
        CONTENT[slug] = c


def has_page(lang: str, kind: str, slug: str = "") -> bool:
    if lang == DEFAULT:
        return True if kind != "article" else (ROOT / "articles" / f"{slug}.html").exists()
    if lang not in STR:
        return False
    if kind == "home":
        return True
    if kind in ("about", "disclosure"):
        return (ROOT / "i18n/pages" / lang / f"{kind}.txt").exists()
    return slug in CONTENT and lang in CONTENT[slug]


def path_for(lang: str, kind: str, slug: str = "") -> str:
    pre = "" if lang == DEFAULT else f"/{lang}"
    if kind == "home":
        return pre + "/"
    if kind == "article":
        return f"{pre}/articles/{slug}"
    return f"{pre}/{kind}"


def file_for(lang: str, kind: str, slug: str = "") -> Path:
    if lang == DEFAULT:
        return ROOT / ("index.html" if kind == "home" else f"articles/{slug}.html" if kind == "article" else f"{kind}.html")
    base = ROOT / lang
    return base / ("index.html" if kind == "home" else f"articles/{slug}.html" if kind == "article" else f"{kind}.html")


def internal(lang: str, key: str) -> str:
    """Resolve an internal link key (/articles/x, /about, /disclosure, /) for a language, falling back to English."""
    if key == "/":
        kind, slug = "home", ""
    elif key.startswith("/articles/"):
        kind, slug = "article", key[len("/articles/"):]
    else:
        kind, slug = key.strip("/"), ""
    return path_for(lang if has_page(lang, kind, slug) else DEFAULT, kind, slug)


def abs_url(path: str) -> str:
    return SITE + path


def fmt_date(lang: str, iso: str) -> str:
    s = STR[lang]
    d = datetime.strptime(iso, "%Y-%m-%d")
    return s["date_fmt"].format(d=d.day, M=d.month, y=d.year, month=s["months"][d.month - 1])


def fmt_src_date(lang: str, raw: str) -> str:
    try:
        d = datetime.strptime(raw, "%b %d, %Y")
        return fmt_date(lang, d.strftime("%Y-%m-%d"))
    except ValueError:
        return raw


# ---------------------------------------------------------------- shared fragments
def alternates(kind: str, slug: str = "") -> list[tuple[str, str]]:
    out = [(l["hreflang"], abs_url(path_for(l["code"], kind, slug))) for l in LANGS if has_page(l["code"], kind, slug)]
    return out


def hreflang_block(kind: str, slug: str, cur: str) -> str:
    lines = [f'  <link rel="alternate" hreflang="{h}" href="{u}">' for h, u in alternates(kind, slug)]
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{abs_url(path_for(DEFAULT, kind, slug))}">')
    for l in LANGS:
        if l["code"] != cur and has_page(l["code"], kind, slug):
            lines.append(f'  <meta property="og:locale:alternate" content="{l["locale"]}">')
    return "  <!-- i18n:hreflang -->\n" + "\n".join(lines) + "\n  <!-- /i18n:hreflang -->"


def lang_menu(kind: str, slug: str, cur: str) -> str:
    items = []
    for l in LANGS:
        if has_page(l["code"], kind, slug):
            target = path_for(l["code"], kind, slug)
        else:
            target = path_for(l["code"], "home")
        aria = ' aria-current="true"' if l["code"] == cur else ""
        items.append(f'<li><a href="{target}" lang="{l["hreflang"]}" hreflang="{l["hreflang"]}"{aria}>{esc(l["name"])}</a></li>')
    label = STR.get(cur, STR.get(DEFAULT, {})).get("lang_label", "Language")
    return (f'      <!-- i18n:langmenu -->\n      <details class="lang-menu"><summary aria-label="{esc_attr(label)}">'
            f'🌐 {esc(LANG[cur]["name"])}</summary><ul>' + "".join(items) + "</ul></details>\n      <!-- /i18n:langmenu -->")


def footer_langs(kind: str, slug: str, cur: str) -> str:
    links = []
    for l in LANGS:
        target = path_for(l["code"], kind, slug) if has_page(l["code"], kind, slug) else path_for(l["code"], "home")
        links.append(f'<a href="{target}" lang="{l["hreflang"]}" hreflang="{l["hreflang"]}">{esc(l["name"])}</a>')
    return ('  <!-- i18n:footerlangs -->\n  <div class="wrap footer-langs"><nav aria-label="Languages">'
            + " ".join(links) + "</nav></div>\n  <!-- /i18n:footerlangs -->")


def og_tags(lang: str, title: str, desc: str, url: str, typ: str, image: str, alt: str, published: str = "") -> str:
    a = LANG[lang]
    pub = f'\n  <meta property="article:published_time" content="{published}">' if published else ""
    return f'''  <meta property="og:type" content="{typ}">
  <meta property="og:title" content="{esc_attr(title)}">
  <meta property="og:description" content="{esc_attr(desc)}">
  <meta property="og:url" content="{url}">
  <meta property="og:site_name" content="PlainBTC">
  <meta property="og:locale" content="{a['locale']}">{pub}
  <meta property="og:image" content="{image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{esc_attr(alt)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{image}">
  <meta name="twitter:title" content="{esc_attr(title)}">
  <meta name="twitter:description" content="{esc_attr(desc)}">'''


def jsonld(obj) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return "  <script type=\"application/ld+json\">\n" + "\n".join("  " + l for l in body.splitlines()) + "\n  </script>"


def head_html(lang, kind, slug, title, desc, og_title, og_desc, typ, image, ld, published="") -> str:
    url = abs_url(path_for(lang, kind, slug))
    a = LANG[lang]
    return f'''<!DOCTYPE html>
<html lang="{a['hreflang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index,follow">
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
  <link rel="alternate" type="application/rss+xml" title="PlainBTC RSS ({esc_attr(a['name'])})" href="/{lang}/feed.xml">
  <link rel="stylesheet" href="/assets/styles.20261109d.css">
  <link rel="stylesheet" href="/assets/article-media.css?v=20261109a">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc_attr(desc)}">
  <link rel="canonical" href="{url}">
{hreflang_block(kind, slug, lang)}
{og_tags(lang, og_title, og_desc, url, typ, image, og_title, published)}
{ld}
</head>'''


def header_html(lang, kind, slug) -> str:
    s = STR[lang]
    p = f"/{lang}"
    return f'''<body>
  <header class="site-header">
    <div class="wrap inner">
      <a class="logo" href="{p}/">Plain<span>BTC</span></a>
      <nav class="nav" aria-label="Primary">
        <a href="{p}/">{esc(s['nav_home'])}</a>
        <a href="{p}/#articles">{esc(s['nav_articles'])}</a>
        <a href="{p}/about">{esc(s['nav_about'])}</a>
        <a href="{p}/disclosure">{esc(s['nav_disclosure'])}</a>
      </nav>
{lang_menu(kind, slug, lang)}
    </div>
  </header>
'''


def footer_html(lang, kind, slug) -> str:
    s = STR[lang]
    p = f"/{lang}"
    return f'''  <footer class="site-footer">
    <div class="wrap inner">
      <div>{esc(s['footer'])}</div>
      <nav class="footer-nav" aria-label="Footer">
        <a href="{p}/">{esc(s['nav_home'])}</a>
        <a href="{p}/about">{esc(s['nav_about'])}</a>
        <a href="{p}/disclosure">{esc(s['nav_disclosure'])}</a>
        <a href="{p}/feed.xml">{esc(s['rss'])}</a>
      </nav>
    </div>
{footer_langs(kind, slug, lang)}
  </footer>
  <script src="/assets/site.js?v=20261109d" defer></script>
</body>
</html>
'''


def render_blocks(pg: Page, blocks: list[dict], indent="      ") -> str:
    out = []
    for b in blocks:
        t = b["t"]
        if t in ("p", "h2", "h3", "blockquote"):
            out.append(f"{indent}<{t}>{pg.inline(b['text'])}</{t}>")
        elif t in ("ul", "ol"):
            lis = "\n".join(f"{indent}  <li>{pg.inline(i)}</li>" for i in b["items"])
            out.append(f"{indent}<{t}>\n{lis}\n{indent}</{t}>")
        else:
            raise ValueError(f"unexpected block {t}")
    return "\n".join(out)


# ---------------------------------------------------------------- page builders
def build_article(lang: str, slug: str):
    s, c = STR[lang], CONTENT[slug]
    head, blocks = c[lang]
    meta = c["meta"]
    pg = Page(lang, c["links"])
    mode = pg.mode
    url = abs_url(path_for(lang, "article", slug))
    img = f"{SITE}/assets/og/{slug}.png"
    pub = s["published"].format(date=fmt_date(lang, meta["date"]), country=s["country"])
    ptitle = f"{head['page_title']} | PlainBTC"
    ld = jsonld({
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": head["title"], "name": ptitle, "description": head["description"],
        "datePublished": meta["date"], "dateModified": meta["date"],
        "author": {"@type": "Organization", "name": "PlainBTC"},
        "publisher": {"@type": "Organization", "name": "PlainBTC", "url": SITE + "/"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url, "image": img,
        "inLanguage": LANG[lang]["hreflang"],
    }) + "\n" + jsonld({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": s["nav_home"], "item": abs_url(path_for(lang, "home"))},
            {"@type": "ListItem", "position": 2, "name": head["title"], "item": url}]})
    parts = [head_html(lang, "article", slug, ptitle, head["description"], head["title"], head["og_description"],
                       "article", img, ld, meta["date"])]
    parts.append(header_html(lang, "article", slug))
    body = [f'''  <main class="article-page">
    <article class="content">
      <a class="back" href="/{lang}/">{esc(s['back_all'])}</a>
      <div class="badge">{esc(head['label'])}</div>
      <h1>{esc(head['title'])}</h1>
      <div class="meta">{esc(pub)}</div>
      <img class="og-hero" src="/assets/og/{slug}.png" width="1200" height="630" alt="{esc_attr(head['title'])}" loading="eager">
''']
    run: list[dict] = []

    def flush():
        if run:
            body.append(render_blocks(pg, run) + "\n")
            run.clear()

    for b in blocks:
        t = b["t"]
        if t in ("p", "h2", "h3", "blockquote", "ul", "ol"):
            run.append(b); continue
        flush()
        if t == "takeaways":
            lis = "\n".join(f"          <li>{pg.inline(i)}</li>" for i in b["items"])
            body.append(f'      <div class="takeaways">\n        <h2>{esc(s["takeaways"])}</h2>\n        <ul>\n{lis}\n        </ul>\n      </div>\n')
        elif t == "figure":
            fig = c["figures"].get(b["id"])
            if not fig:
                errors.append(f"[{lang}/{slug}] unknown figure id {b['id']!r}")
            else:
                alt = fig["alt"].get(lang) or fig["alt"].get("en", "")
                cap = fig["caption"].get(lang) or fig["caption"].get("en", "")
                src = f"/assets/img/{slug}/{fig['file']}"
                body.append(
                    f'''      <figure class="article-figure">
        <img src="{src}" width="{fig['w']}" height="{fig['h']}" alt="{esc_attr(alt)}" loading="lazy">
        <figcaption>{esc(cap)}</figcaption>
      </figure>
'''
                )
        elif t == "mid_cta":
            if mode in ("full", "hedged"):
                body.append(f'''      <aside class="mid-cta" aria-label="{esc_attr(s['banner_label'])}">
        <div class="mid-cta-label">{esc(s['banner_label'])}</div>
        <h2>{esc(s['banner_title'])}</h2>
        <p>{pg.inline(s['banner_text'])}</p>
        <a class="cta-button" href="{REF_URL}" rel="sponsored noopener" target="_blank">{esc(s['banner_button'])}</a>
      </aside>
''')
        elif t == "soft":
            body.append(f'      <p class="soft-guide">{pg.inline(b["text"])}</p>\n')
        elif t == "end_cta":
            if mode != "none":
                body.append(f'''      <div class="cta">
        <h2>{esc(s['cta_title'])}</h2>
        <p>{pg.inline(s['cta_text'])}</p>
        <a class="cta-button" href="{REF_URL}" rel="sponsored noopener" target="_blank">{esc(s['cta_button'])}</a>
      </div>
''')
        elif t == "disclosure":
            adv = s["not_advice_" + meta.get("disclosure_variant", "std")]
            aff = (pg.inline(s["disc_affiliate"]) + "<br><br>\n        ") if mode != "none" else ""
            body.append(f'      <div class="disclosure">\n        {aff}{pg.inline(adv)}\n      </div>\n')
        else:
            errors.append(f"[{lang}/{slug}] unknown block {t}")
    flush()
    rel = [r for r in meta["related"] if r in CONTENT and lang in CONTENT[r]]
    if rel:
        lis = "\n".join(f'          <li><a href="{path_for(lang, "article", r)}">{esc(CONTENT[r][lang][0]["title"])}</a></li>' for r in rel)
        body.append(f'''      <aside class="related" aria-label="{esc_attr(s['related'])}">
        <h2>{esc(s['related'])}</h2>
        <ul>
{lis}
        </ul>
      </aside>
''')
    srcs = "\n".join(
        f'          <li><a href="{esc_attr(x["url"])}" target="_blank" rel="noopener">{esc(x["title"])}</a>'
        + (f' ({esc(fmt_src_date(lang, x["date"]))})' if x.get("date") else "") + "</li>" for x in meta["sources"])
    body.append(f'''      <section class="sources" aria-label="{esc_attr(s['sources'])}">
        <h2>{esc(s['sources'])}</h2>
        <ol>
{srcs}
        </ol>
        <p class="sources-note">{esc(s['sources_note'])}</p>
      </section>
    </article>
  </main>
''')
    parts.append("\n".join(body))
    parts.append(footer_html(lang, "article", slug))
    return "\n".join(parts)


def article_cards(lang):
    s = STR[lang]
    cards = []
    for slug in SLUGS:
        if slug not in CONTENT or lang not in CONTENT[slug]:
            continue
        head = CONTENT[slug][lang][0]
        meta = CONTENT[slug]["meta"]
        href = path_for(lang, "article", slug)
        m = f"{head['label']} · {fmt_date(lang, meta['date'])} · {s['readtime'].format(n=meta['readtime'])}"
        cards.append(f'''      <article class="card">
        <div class="meta">{esc(m)}</div>
        <h2><a href="{href}">{esc(head['title'])}</a></h2>
        <p>{esc(head['summary'])}</p>
        <a class="read-more" href="{href}">{esc(s['read_article'])}</a>
      </article>''')
    return "\n\n".join(cards)


def build_home(lang):
    s = STR[lang]
    pg = Page(lang)
    url = abs_url(path_for(lang, "home"))
    img = f"{SITE}/assets/og/default.png"
    latest = max((CONTENT[x]["meta"]["date"] for x in CONTENT if lang in CONTENT[x]), default=date.today().isoformat())
    ld = jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": "PlainBTC", "url": url,
                 "description": s["tagline"], "inLanguage": LANG[lang]["hreflang"],
                 "publisher": {"@type": "Organization", "name": "PlainBTC", "url": SITE + "/"}})
    h = head_html(lang, "home", "", s["home_title"], s["home_description"], s["home_title"], s["home_og_description"], "website", img, ld)
    mode_box = s["about_box"]
    return "\n".join([h, header_html(lang, "home", ""), f'''  <main>
    <section class="hero wrap">
      <div class="badge">{esc(s['hero_badge'].format(date=fmt_date(lang, latest)))}</div>
      <h1>{esc(s['hero_h1'])}</h1>
      <p>{esc(s['hero_p'])}</p>
    </section>

    <section id="articles" class="wrap article-grid" aria-label="{esc_attr(s['nav_articles'])}">
{article_cards(lang)}
    </section>

    <section id="about" class="wrap" style="padding-bottom:3rem;">
      <div class="disclosure">
        {pg.inline(mode_box)}
      </div>
    </section>
  </main>
''', footer_html(lang, "home", "")])


def build_simple(lang, kind):
    s = STR[lang]
    head, blocks = parse_txt(ROOT / "i18n/pages" / lang / f"{kind}.txt")
    pg = Page(lang)
    url = abs_url(path_for(lang, kind))
    img = f"{SITE}/assets/og/default.png"
    ld = jsonld({"@context": "https://schema.org", "@type": "AboutPage" if kind == "about" else "WebPage",
                 "name": head["og_title"], "url": url, "inLanguage": LANG[lang]["hreflang"],
                 "isPartOf": {"@type": "WebSite", "name": "PlainBTC", "url": SITE + "/"}})
    h = head_html(lang, kind, "", head["page_title"], head["description"], head["og_title"], head["og_description"], "website", img, ld)
    tag = f'\n      <p class="tagline">{esc(head["tagline"])}</p>' if head.get("tagline") else ""
    return "\n".join([h, header_html(lang, kind, ""), f'''  <main class="prose-page">
    <div class="content">
      <a class="back" href="/{lang}/">{esc(s['back_home'])}</a>
      <h1>{esc(head['h1'])}</h1>{tag}
{render_blocks(pg, blocks)}
    </div>
  </main>
''', footer_html(lang, kind, "")])


def en_feed_dates() -> dict[str, str]:
    d = {}
    f = ROOT / "feed.xml"
    if f.exists():
        for m in re.finditer(r"<link>[^<]*/articles/([a-z0-9-]+)</link>.*?<pubDate>([^<]+)</pubDate>", f.read_text(encoding="utf-8"), re.S):
            d[m.group(1)] = m.group(2)
    return d


def build_feed(lang):
    s = STR[lang]
    dates = en_feed_dates()
    items = []
    for slug in SLUGS:
        if slug in CONTENT and lang in CONTENT[slug]:
            h = CONTENT[slug][lang][0]
            u = abs_url(path_for(lang, "article", slug))
            pd = dates.get(slug) or datetime.strptime(CONTENT[slug]["meta"]["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 12:00:00 GMT")
            items.append(f"    <item>\n      <title>{esc(h['title'])}</title>\n      <link>{u}</link>\n      <guid isPermaLink=\"true\">{u}</guid>\n"
                         f"      <pubDate>{pd}</pubDate>\n      <description>{esc(h['summary'])}</description>\n    </item>")
    last = max(dates.values(), key=lambda x: datetime.strptime(x, "%a, %d %b %Y %H:%M:%S GMT")) if dates else "Mon, 09 Nov 2026 12:00:00 GMT"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>PlainBTC</title>
    <link>{abs_url(path_for(lang, "home"))}</link>
    <description>{esc(s['tagline'])}</description>
    <language>{LANG[lang]['hreflang'].lower()}</language>
    <lastBuildDate>{last}</lastBuildDate>
    <atom:link href="{SITE}/{lang}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
'''


def build_sitemap():
    old = {}
    sm = ROOT / "sitemap.xml"
    if sm.exists():
        for m in re.finditer(r"<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>\s*<changefreq>([^<]+)</changefreq>\s*<priority>([^<]+)</priority>", sm.read_text(encoding="utf-8")):
            old[m.group(1)] = m.groups()[1:]
    latest = max((CONTENT[x]["meta"]["date"] for x in CONTENT), default=date.today().isoformat())
    pages = [("home", "")] + [("about", ""), ("disclosure", "")] + [("article", s) for s in SLUGS]
    urls = []
    for kind, slug in pages:
        en_loc = abs_url(path_for(DEFAULT, kind, slug))
        lm, cf, pr = old.get(en_loc, (None, None, None))
        if kind == "home":
            lm, cf, pr = latest, "daily", "1.0"
        elif kind == "article":
            lm = lm or CONTENT.get(slug, {}).get("meta", {}).get("date", latest)
            cf, pr = cf or "weekly", pr or "0.9"
        else:
            lm, cf, pr = lm or latest, cf or "monthly", pr or ("0.5" if kind == "about" else "0.4")
        alts = alternates(kind, slug)
        alt_xml = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{h}" href="{u}"/>' for h, u in alts)
        alt_xml += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{en_loc}"/>'
        for l in LANGS:
            if has_page(l["code"], kind, slug):
                loc = abs_url(path_for(l["code"], kind, slug))
                urls.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lm}</lastmod>\n    <changefreq>{cf}</changefreq>\n    <priority>{pr}</priority>{alt_xml}\n  </url>")
    feeds = [f"{SITE}/feed.xml"] + [f"{SITE}/{l['code']}/feed.xml" for l in LANGS if l["code"] != DEFAULT and l["code"] in STR]
    for f in feeds:
        urls.append(f"  <url>\n    <loc>{f}</loc>\n    <lastmod>{latest}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.3</priority>\n  </url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(urls) + "\n</urlset>\n")


# ---------------------------------------------------------------- English patching
def fix_jsonld(h: str) -> str:
    """The original English pages used single-quoted strings in JSON-LD (invalid JSON); rewrite as valid JSON."""
    def fix_block(m):
        txt = m.group(2)
        txt = re.sub(r"(:\s*)'((?:[^'\\]|\\.)*)'", lambda mm: mm.group(1) + json.dumps(mm.group(2).replace("\\'", "'"), ensure_ascii=False), txt)
        return m.group(1) + txt + m.group(3)
    return re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)', fix_block, h, flags=re.S)


def replace_marked(h: str, name: str, new: str) -> tuple[str, bool]:
    pat = re.compile(rf"[ \t]*<!-- i18n:{name} -->.*?<!-- /i18n:{name} -->", re.S)
    if pat.search(h):
        return pat.sub(lambda m: new, h, count=1), True
    return h, False


def patch_en(path: Path, kind: str, slug: str = ""):
    h = path.read_text(encoding="utf-8")
    o = h
    h = fix_jsonld(h)
    h = re.sub(
        r'<link rel="stylesheet" href="[^"]*styles(?:\.[\w-]+)?\.css(?:\?[^"]*)?">',
        '<link rel="stylesheet" href="/assets/styles.20261109d.css">',
        h,
        count=1,
    )
    if "article-media.css" not in h:
        h = h.replace(
            '<link rel="stylesheet" href="/assets/styles.20261109d.css">',
            '<link rel="stylesheet" href="/assets/styles.20261109d.css">\n'
            '  <link rel="stylesheet" href="/assets/article-media.css?v=20261109a">',
            1,
        )
    if "/assets/site.js" not in h:
        h = h.replace("</body>", '  <script src="/assets/site.js?v=20261109d" defer></script>\n</body>', 1)
    new = hreflang_block(kind, slug, DEFAULT)
    h, ok = replace_marked(h, "hreflang", new)
    if not ok:
        h = h.replace("</head>", new + "\n</head>", 1)
    new = lang_menu(kind, slug, DEFAULT)
    h, ok = replace_marked(h, "langmenu", new)
    if not ok:
        h, n = re.subn(r"(</nav>)(\n    </div>\n  </header>)", lambda m: m.group(1) + "\n" + new + m.group(2), h, count=1)
        if not n:
            errors.append(f"cannot place langmenu in {path}")
    new = footer_langs(kind, slug, DEFAULT)
    h, ok = replace_marked(h, "footerlangs", new)
    if not ok:
        h = h.replace("  </footer>", new + "\n  </footer>", 1)
    if h != o:
        path.write_text(h, encoding="utf-8")


# ---------------------------------------------------------------- validation
def num_tokens(s: str) -> set[str]:
    s = re.sub(r"\(\/?[^)]*\)", "", s)                       # drop link targets
    s = re.sub(r"(?<=\d)[\u00a0\u202f ](?=\d{3}\b)", "", s)   # "3 000" -> "3000"
    return {re.sub(r"\D", "", t) for t in re.findall(r"\d+(?:[.,]\d+)*", s)} - {""}


def validate():
    for slug, c in CONTENT.items():
        src_head, src_blocks = c["en"]
        for l in LANGS:
            code = l["code"]
            if code == DEFAULT or code not in c:
                continue
            head, blocks = c[code]
            tag = f"{code}/{slug}"
            for k in src_head:
                if not head.get(k):
                    errors.append(f"[{tag}] missing header '{k}'")
            def sig(b):
                return (b["t"], b.get("id", ""))
            if [sig(b) for b in blocks] != [sig(b) for b in src_blocks]:
                errors.append(f"[{tag}] block sequence differs: {len(blocks)} vs {len(src_blocks)} blocks")
                continue
            for i, (a, b) in enumerate(zip(src_blocks, blocks)):
                if a["t"] == "figure":
                    continue
                at = a.get("text") or " ".join(a.get("items", []))
                bt = b.get("text") or " ".join(b.get("items", []))
                if "items" in a and len(a["items"]) != len(b["items"]):
                    errors.append(f"[{tag}] block {i}: list length {len(a['items'])} vs {len(b['items'])}")
                la = sorted(re.findall(r"\]\(([^)]*)\)", at)); lb = sorted(re.findall(r"\]\(([^)]*)\)", bt))
                if la != lb:
                    errors.append(f"[{tag}] block {i}: link keys {la} vs {lb}")
                if at.count("{{#ref}}") != bt.count("{{#ref}}") or bt.count("{{#ref}}") != bt.count("{{/ref}}"):
                    errors.append(f"[{tag}] block {i}: {{#ref}} markers mismatch")
                if re.sub(r"[^<>/a-z]", "", " ".join(re.findall(r"</?(?:strong|em|code)>|<br>", at))) != re.sub(r"[^<>/a-z]", "", " ".join(re.findall(r"</?(?:strong|em|code)>|<br>", bt))):
                    warnings.append(f"[{tag}] block {i}: inline tags differ")
                miss = {n for n in num_tokens(at) if len(n) >= 2} - num_tokens(bt)
                if miss and code not in ("ja", "ko"):   # 万/億/만/억 grouping: review numbers by hand
                    warnings.append(f"[{tag}] block {i}: numbers not found in translation: {sorted(miss)}")
            for k in ("{{", "[["):
                pass


def validate_strings():
    base = STR[DEFAULT]
    for code, s in STR.items():
        mode = LANG[code]["referral"]
        need = set(base)
        if mode not in ("full", "hedged"):
            need -= {k for k in base if k.startswith("banner_")}
        if mode == "none":
            need -= {k for k in base if k.startswith("cta_")} | {"disc_affiliate"}
        missing = need - set(s)
        if missing:
            errors.append(f"[strings/{code}] missing keys: {sorted(missing)}")
        if len(s.get("months", [])) != 12:
            errors.append(f"[strings/{code}] months must have 12 entries")


# ---------------------------------------------------------------- main
def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def main():
    check_only = "--check" in sys.argv
    load_content()
    validate_strings()
    validate()
    if errors:
        print("\n".join("ERROR " + e for e in errors)); sys.exit(1)
    if check_only:
        print("\n".join("warn  " + w for w in warnings)); print("check OK"); return
    n = 0
    for l in LANGS:
        code = l["code"]
        if code == DEFAULT or code not in STR:
            continue
        write(file_for(code, "home"), build_home(code)); n += 1
        for kind in ("about", "disclosure"):
            if has_page(code, kind):
                write(file_for(code, kind), build_simple(code, kind)); n += 1
        for slug in SLUGS:
            if has_page(code, "article", slug):
                write(file_for(code, "article", slug), build_article(code, slug)); n += 1
        write(ROOT / code / "feed.xml", build_feed(code))
    # English pages: patch in place
    patch_en(ROOT / "index.html", "home")
    patch_en(ROOT / "about.html", "about")
    patch_en(ROOT / "disclosure.html", "disclosure")
    for slug in SLUGS:
        patch_en(ROOT / "articles" / f"{slug}.html", "article", slug)
    write(ROOT / "sitemap.xml", build_sitemap())
    print(f"built {n} non-English pages; {len(SLUGS)} articles")
    if errors:
        print("\n".join("ERROR " + e for e in errors)); sys.exit(1)
    print("\n".join("warn  " + w for w in warnings))


if __name__ == "__main__":
    main()
