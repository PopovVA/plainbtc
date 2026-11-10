#!/usr/bin/env python3
"""Extract an English article (articles/<slug>.html) into the i18n translation source.

Creates i18n/content/<slug>/{meta.json, links.json, en.txt}.
Translators copy en.txt to <lang>.txt and translate the text (see README, "Translations").

Usage: python3 tools/i18n_extract.py <slug> [<slug> ...]   |  --all
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
REF_URL = "https://coinbase.com/join/F2XRWRL?src=referral-link"


class Ctx:
    def __init__(self):
        self.links: dict[str, str] = {}

    def key(self, href: str) -> str:
        if href == REF_URL:
            return "REF"
        m = re.match(r"^(?:\.\./)?(?:articles/)?([a-z0-9-]+)\.html$", href)
        if m and m.group(1) not in ("index", "about", "disclosure"):
            return "/articles/" + m.group(1)
        if href in ("../disclosure.html", "disclosure.html", "/disclosure"):
            return "/disclosure"
        if href in ("../about.html", "about.html", "/about"):
            return "/about"
        if re.match(r"^/articles/[a-z0-9-]+$", href):   # pretty URL (what the build writes back into the page)
            return href
        for k, v in self.links.items():
            if v == href:
                return k
        k = f"L{len(self.links) + 1}"
        self.links[k] = href
        return k


def inline(el: Tag, ctx: Ctx) -> str:
    out = []
    for c in el.children:
        if isinstance(c, NavigableString):
            out.append(str(c))
        elif c.name == "a":
            out.append(f"[{inline(c, ctx).strip()}]({ctx.key(c['href'])})")
        elif c.name in ("strong", "em"):
            out.append(f"<{c.name}>{inline(c, ctx)}</{c.name}>")
        elif c.name == "br":
            out.append("<br>")
        else:
            out.append(inline(c, ctx))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def extract(slug: str):
    html = (ROOT / "articles" / f"{slug}.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    art = soup.select_one("article.content")
    ctx = Ctx()
    meta_og = lambda p: (soup.find("meta", attrs={"property": p}) or {}).get("content", "")
    head = {
        "title": soup.h1.get_text(strip=True),
        "page_title": re.sub(r"\s*\|\s*PlainBTC$", "", soup.title.get_text(strip=True)),
        "description": soup.find("meta", attrs={"name": "description"})["content"],
        "og_description": meta_og("og:description"),
        "label": art.select_one(".badge").get_text(strip=True),
    }
    meta = {"slug": slug, "date": meta_og("article:published_time"), "readtime": 7, "related": [], "sources": [],
            "disclosure_variant": "std"}
    idx = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
    for card in idx.select("article.card"):
        title = card.find(["h2", "h3"])
        if title and title.a and title.a["href"].rstrip("/").split("/")[-1].removesuffix(".html") == slug:
            head["summary"] = card.find("p").get_text(strip=True)
            m = re.search(r"~(\d+)\s*min", card.select_one(".meta").get_text())
            meta["readtime"] = int(m.group(1)) if m else 7
    blocks: list[str] = []
    for el in art.find_all(recursive=False):
        cls = el.get("class") or []
        if el.name in ("a", "img", "h1", "header", "nav") or "badge" in cls or "meta" in cls:
            continue   # article head (breadcrumbs, label, headline, byline, share row, hero image)
        if el.name == "aside" and ("community-box" in cls or "newsletter-box" in cls):
            continue   # placed by the build on every page
        if el.name == "aside" and "mid-cta" in cls:
            blocks.append("!mid_cta")
        elif el.name == "div" and "cta" in cls:
            blocks.append("!end_cta")
        elif el.name == "div" and "takeaways" in cls:
            blocks.append("!takeaways\n" + "\n".join("- " + inline(li, ctx) for li in el.find_all("li")))
        elif el.name == "div" and "disclosure" in cls:
            t = el.get_text(" ", strip=True)
            meta["disclosure_variant"] = "political" if "political advice" in t else ("guide" if "educational only" in t else "std")
            blocks.append("!disclosure")
        elif el.name == "aside" and "related" in cls:
            meta["related"] = [a["href"].rstrip("/").split("/")[-1].removesuffix(".html") for a in el.find_all("a")]
        elif el.name == "section" and "sources" in cls:
            for li in el.find_all("li"):
                a = li.find("a")
                rest = li.get_text(" ", strip=True).replace(a.get_text(strip=True), "", 1).strip()
                meta["sources"].append({"url": a["href"], "title": a.get_text(strip=True), "date": rest.strip("() ")})
        elif el.name == "p" and "soft-guide" in cls:
            blocks.append("!soft: " + inline(el, ctx))
        elif el.name == "p":
            blocks.append(inline(el, ctx))
        elif el.name in ("h2", "h3"):
            blocks.append("#" * int(el.name[1]) + " " + inline(el, ctx))
        elif el.name == "blockquote":
            blocks.append("> " + inline(el, ctx))
        elif el.name == "ul":
            blocks.append("\n".join("- " + inline(li, ctx) for li in el.find_all("li", recursive=False)))
        elif el.name == "ol":
            blocks.append("\n".join(f"{i}. " + inline(li, ctx) for i, li in enumerate(el.find_all("li", recursive=False), 1)))
        else:
            print("UNHANDLED", slug, el.name, cls, file=sys.stderr)
    blocks = [b.replace("(REF) through our referral link", "(REF){{#ref}} through our referral link{{/ref}}") for b in blocks]
    txt = "\n".join(f"{k}: {v}" for k, v in head.items()) + "\n===\n\n" + "\n\n".join(blocks) + "\n"
    return meta, ctx.links, txt


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--all"]:
        args = [p.stem for p in sorted((ROOT / "articles").glob("*.html"))]
    for slug in args:
        meta, links, txt = extract(slug)
        out = ROOT / "i18n" / "content" / slug
        out.mkdir(parents=True, exist_ok=True)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (out / "links.json").write_text(json.dumps(links, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (out / "en.txt").write_text(txt, encoding="utf-8")
        print("extracted", slug)
