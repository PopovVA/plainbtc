#!/usr/bin/env python3
"""Generate the *English* article HTML (articles/<slug>.html) from i18n/content/<slug>/en.txt.

English articles are normally hand-written; for new evergreen guides it is faster and keeps all
language versions structurally identical (figures, FAQPage/HowTo JSON-LD, CTAs) to render en.txt with the
same builder used for the other 9 languages, then post-fix a few English-specific bits (URL prefix,
US referral wording that matches the hand-written articles).

Usage: python3 tools/gen_en_article.py <slug> [<slug> ...]
Afterwards run: python3 tools/build_i18n.py   (patches hreflang / language menu / community box, builds other langs)
"""
import importlib.util, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_i18n", ROOT / "tools" / "build_i18n.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

EN_OVERRIDES = {
    "banner_text": "Eligible new users may get a bitcoin bonus after a qualifying trade. Terms vary.",
    "banner_button": "Open Coinbase",
    "cta_title": "Start on Coinbase with this referral link",
    "cta_text": "Open a new Coinbase account through the link below if you are ready to begin. Eligible new users may receive a bonus after a qualifying trade; terms vary by country and Coinbase’s current terms.",
    "cta_button": "Sign up on Coinbase with this link",
    "disc_affiliate": "<strong>Disclosure:</strong> This post contains a referral link. If you sign up and complete a qualifying purchase through it, PlainBTC may earn a referral reward from Coinbase at no extra cost to you. See our [full affiliate disclosure](/disclosure).",
}


def main(slugs):
    for slug in slugs:
        (ROOT / "articles" / f"{slug}.html").touch(exist_ok=True)   # so has_page() sees the English page
        if slug not in b.SLUGS:
            b.SLUGS.append(slug)
    b.load_content()
    b.STR["en"].update(EN_OVERRIDES)
    for slug in slugs:
        html = b.build_article("en", slug)
        html = html.replace('href="/en/', 'href="/')
        html = re.sub(r'\s*<p class="sources-note">.*?</p>', '', html, flags=re.S)   # note only makes sense for translations
        (ROOT / "articles" / f"{slug}.html").write_text(html, encoding="utf-8")
        print("wrote", f"articles/{slug}.html")
    if b.errors:
        print("\n".join("ERROR " + e for e in b.errors)); sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
