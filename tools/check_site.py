#!/usr/bin/env python3
"""Check the built site: SEO tags, JSON-LD, links, images, sitemap and feeds. Standard library only.

  python3 tools/check_site.py            # exits 1 when something is broken

What it verifies on every indexable page (home, about, disclosure and articles, in all languages):
* one <title>, one meta description, one self-referencing canonical, one <h1>, <html lang>
* titles and descriptions are unique inside a language
* Open Graph + Twitter card tags, robots allows indexing with large image previews
* every JSON-LD block is valid JSON; articles carry (News)Article + BreadcrumbList, homes WebSite + Organization
* hreflang alternates point at existing pages and link back
* every internal link and fragment resolves; every local image exists and has alt, width and height
* sitemap.xml lists exactly the indexable pages; no URL from the previously committed sitemap is lost
* feeds are well-formed and their self link is right
"""
from __future__ import annotations
import json, re, subprocess, sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://plainbtc.com"
LANGS = [l["code"] for l in json.loads((ROOT / "i18n/langs.json").read_text(encoding="utf-8"))["langs"]]
errors: list[str] = []


class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.titles: list[str] = []
        self.metas: list[dict] = []
        self.links: list[dict] = []
        self.anchors: list[str] = []
        self.imgs: list[dict] = []
        self.ids: set[str] = set()
        self.h1 = 0
        self.ld: list[str] = []
        self._buf: list[str] | None = None
        self._kind = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._buf, self._kind = [], "title"
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "a" and a.get("href") is not None:
            self.anchors.append(a["href"])
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "h1":
            self.h1 += 1
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._buf, self._kind = [], "ld"

    def handle_endtag(self, tag):
        if self._buf is not None and tag in ("title", "script"):
            text = "".join(self._buf)
            (self.titles if self._kind == "title" else self.ld).append(text)
            self._buf = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)

    def meta(self, key: str, attr: str = "name") -> list[str]:
        return [m.get("content", "") for m in self.metas if m.get(attr) == key]


def url_for(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    rel = rel[: -len(".html")]
    if rel == "index":
        return "/"
    if rel.endswith("/index"):
        return "/" + rel[: -len("index")]
    return "/" + rel


def file_for(url_path: str) -> Path | None:
    """Resolve a site path the way Cloudflare Pages does (pretty URLs)."""
    p = url_path.split("#")[0].split("?")[0]
    if p.endswith("/"):
        f = ROOT / p.lstrip("/") / "index.html"
    else:
        f = ROOT / p.lstrip("/")
        if not f.is_file():
            f = ROOT / (p.lstrip("/") + ".html")
    return f if f.is_file() else None


def pages() -> list[Path]:
    out = [ROOT / "index.html", ROOT / "about.html", ROOT / "disclosure.html"]
    out += sorted((ROOT / "articles").glob("*.html"))
    for l in LANGS[1:]:
        out += sorted((ROOT / l).glob("*.html")) + sorted((ROOT / l / "articles").glob("*.html"))
    return [p for p in out if p.exists()]


def main() -> int:
    docs: dict[str, Doc] = {}
    for path in pages() + [ROOT / "404.html"]:
        d = Doc()
        d.feed(path.read_text(encoding="utf-8"))
        docs[url_for(path)] = d

    titles: dict[tuple[str, str], str] = {}
    descs: dict[tuple[str, str], str] = {}
    indexable: set[str] = set()
    for url, d in docs.items():
        err = lambda msg: errors.append(f"{url}: {msg}")
        is_404 = url == "/404"
        robots = (d.meta("robots") or [""])[0]
        if len(d.titles) != 1 or not d.titles[0].strip():
            err(f"expected one <title>, found {len(d.titles)}")
        if not d.lang:
            err("missing <html lang>")
        if d.h1 != 1:
            err(f"expected one <h1>, found {d.h1}")
        for raw in d.ld:
            try:
                json.loads(raw)
            except ValueError as e:
                err(f"invalid JSON-LD ({e})")
        for img in d.imgs:
            src = img.get("src", "")
            if "alt" not in img:
                err(f"image without alt: {src}")
            if not (img.get("width") and img.get("height")):
                err(f"image without width/height: {src}")
            if src.startswith("/") and not (ROOT / src.lstrip("/")).is_file():
                err(f"missing image file: {src}")
        for href in d.anchors:
            if href.startswith("#"):
                if len(href) > 1 and href != "#top" and href[1:] not in d.ids:
                    err(f"broken fragment {href}")
                continue
            if not href.startswith("/") or href.startswith("//"):
                continue
            target = file_for(href)
            if target is None:
                err(f"broken internal link {href}")
            elif "#" in href:
                frag = href.split("#", 1)[1]
                tdoc = docs.get(url_for(target)) if target.suffix == ".html" else None
                if frag and tdoc and frag not in tdoc.ids:
                    err(f"broken fragment in link {href}")
        for l in d.links:
            href = l.get("href", "")
            if l.get("rel") in ("stylesheet", "preload", "icon", "apple-touch-icon", "manifest") and href.startswith("/"):
                if not (ROOT / href.split("?",1)[0].lstrip("/")).is_file():
                    err(f"missing asset {href}")
        if is_404:
            if "noindex" not in robots:
                err("404 page must be noindex")
            continue
        indexable.add(url)
        if "noindex" in robots or "max-image-preview:large" not in robots:
            err(f"robots meta should allow indexing with large previews, got {robots!r}")
        desc = d.meta("description")
        if len(desc) != 1 or len(desc[0]) < 50:
            err("missing or very short meta description")
        canon = [l.get("href") for l in d.links if l.get("rel") == "canonical"]
        if canon != [SITE + url]:
            err(f"canonical should be {SITE + url}, got {canon}")
        for key, attr in (("og:title", "property"), ("og:description", "property"), ("og:url", "property"),
                          ("og:image", "property"), ("og:type", "property"), ("og:locale", "property"),
                          ("twitter:card", "name"), ("twitter:image", "name")):
            if not d.meta(key, attr):
                err(f"missing {key}")
        if d.meta("og:url", "property") not in ([SITE + url], []):
            err("og:url differs from the canonical URL")
        for image in d.meta("og:image", "property"):
            if image.startswith(SITE) and not (ROOT / image[len(SITE):].lstrip("/")).is_file():
                err(f"missing og:image file {image}")
        types = []
        for raw in d.ld:
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            types.append(obj.get("@type") if isinstance(obj, dict) else None)
            if isinstance(obj, dict) and obj.get("@type") in ("NewsArticle", "Article"):
                for k in ("headline", "datePublished", "dateModified", "author", "publisher", "image", "mainEntityOfPage"):
                    if not obj.get(k):
                        err(f"article JSON-LD without {k}")
                if not (obj.get("publisher") or {}).get("logo"):
                    err("article JSON-LD publisher without logo")
        if "/articles/" in url:
            if not ({"NewsArticle", "Article"} & set(types)) or "BreadcrumbList" not in types:
                err(f"article needs (News)Article + BreadcrumbList JSON-LD, has {types}")
        elif url == "/" or url.strip("/") in LANGS:
            if "WebSite" not in types or "Organization" not in types:
                err(f"home needs WebSite + Organization JSON-LD, has {types}")
        lang = d.lang
        t = d.titles[0].strip() if d.titles else ""
        if (lang, t) in titles:
            err(f"duplicate title, also on {titles[(lang, t)]}")
        titles[(lang, t)] = url
        if desc:
            if (lang, desc[0]) in descs:
                err(f"duplicate meta description, also on {descs[(lang, desc[0])]}")
            descs[(lang, desc[0])] = url
        # hreflang: targets exist and link back
        alts = {l.get("hreflang"): l.get("href", "") for l in d.links if l.get("rel") == "alternate" and l.get("hreflang")}
        if "x-default" not in alts:
            err("missing hreflang x-default")
        if SITE + url not in alts.values():
            err("hreflang set does not include the page itself")
        for hl, href in alts.items():
            other = docs.get(href[len(SITE):]) if href.startswith(SITE) else None
            if other is None:
                err(f"hreflang {hl} points to a missing page {href}")
            elif hl != "x-default":
                back = [l.get("href") for l in other.links if l.get("rel") == "alternate" and l.get("hreflang")]
                if SITE + url not in back:
                    err(f"hreflang {hl} target {href} does not link back")

    # sitemap
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    try:
        sm = ET.parse(ROOT / "sitemap.xml")
        locs = [e.text for e in sm.getroot().findall("s:url/s:loc", ns)]
    except ET.ParseError as e:
        errors.append(f"sitemap.xml is not well-formed: {e}")
        locs = []
    page_locs = {l[len(SITE):] for l in locs if not l.endswith(".xml")}
    for miss in sorted(indexable - page_locs):
        errors.append(f"sitemap.xml: missing {miss}")
    for extra in sorted(page_locs - indexable):
        errors.append(f"sitemap.xml: lists a page that does not exist or is not indexable: {extra}")
    for l in locs:
        if l.endswith(".xml") and not (ROOT / l[len(SITE):].lstrip("/")).is_file():
            errors.append(f"sitemap.xml: missing file {l}")
    # nothing that was in the last committed sitemap may disappear
    try:
        old = subprocess.run(["git", "show", "HEAD:sitemap.xml"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        for l in re.findall(r"<loc>([^<]+)</loc>", old):
            if file_for(l[len(SITE):]) is None:
                errors.append(f"URL from the committed sitemap no longer exists: {l}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # feeds
    for l in LANGS:
        rel = "feed.xml" if l == LANGS[0] else f"{l}/feed.xml"
        f = ROOT / rel
        if not f.exists():
            errors.append(f"missing {rel}")
            continue
        try:
            ch = ET.parse(f).getroot().find("channel")
        except ET.ParseError as e:
            errors.append(f"{rel} is not well-formed: {e}")
            continue
        self_link = ch.find("{http://www.w3.org/2005/Atom}link")
        if self_link is None or self_link.get("href") != f"{SITE}/{rel}":
            errors.append(f"{rel}: atom self link should be {SITE}/{rel}")
        for item in ch.findall("item"):
            link = item.findtext("link") or ""
            if file_for(link[len(SITE):]) is None:
                errors.append(f"{rel}: item link does not exist: {link}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: {SITE}/sitemap.xml" not in robots:
        errors.append("robots.txt does not point to the sitemap")

    if errors:
        print("\n".join("ERROR " + e for e in errors))
        print(f"{len(errors)} problem(s) in {len(docs)} pages")
        return 1
    print(f"site OK: {len(docs)} pages, {len(locs)} sitemap URLs, {len(LANGS)} feeds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
