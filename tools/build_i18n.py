#!/usr/bin/env python3
"""PlainBTC multilingual builder.

Reads  i18n/langs.json, i18n/partners.json, i18n/strings/<lang>.json,
       i18n/pages/<lang>/{about,disclosure}.txt,
       i18n/content/<slug>/{meta.json,links.json,<lang>.txt}
Writes <lang>/index.html, <lang>/about.html, <lang>/disclosure.html, <lang>/articles/<slug>.html,
       <lang>/feed.xml, sitemap.xml (with hreflang alternates)
Patches the hand-written English pages in place (head assets, site header and footer, hreflang block,
home <main>, article head, JSON-LD), so it is safe to run repeatedly.
Publishes content-hashed copies of assets/styles.css and assets/site.js.

Usage:
  python3 tools/build_i18n.py            # build everything
  python3 tools/build_i18n.py --check    # validate translations only (no writes)
See README ("Multilingual site").
"""
from __future__ import annotations
import html as _html
import hashlib, json, re, shutil, sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://plainbtc.com"
REF_URL = "https://coinbase.com/join/F2XRWRL?src=referral-link"

COMMUNITY = [
    ("discord", "https://discord.gg/EcuGXPDr2d", "community_discord"),
    ("facebook", "https://www.facebook.com/groups/1688106109771364", "community_facebook"),
    ("x", "https://x.com/lean_redfield", "community_x"),
]
SAME_AS = [u for _, u, _ in COMMUNITY]
ASSET_DIR = ROOT / "assets"
TWITTER_SITE = "@lean_redfield"
LOGO_PNG = SITE + "/assets/logo-512.png"
HOME_VISIBLE = 13      # cards shown on a home page before the "older articles" expander (1 lead + 4 rows of 3)


def _asset_url(name: str) -> str:
    """/assets/<stem>.<content hash>.<ext> for a source file in assets/ (cache-busting, see sync_assets())."""
    stem, ext = name.rsplit(".", 1)
    digest = hashlib.sha256((ASSET_DIR / name).read_bytes()).hexdigest()[:10]
    return f"/assets/{stem}.{digest}.{ext}"


# Edit assets/styles.css and assets/site.js; the build publishes hashed copies and points every page at them.
STYLES_CSS = _asset_url("styles.css")
SITE_JS = _asset_url("site.js")


def sync_assets() -> None:
    """Write the hashed copies of styles.css / site.js and delete stale ones."""
    for name, url in (("styles.css", STYLES_CSS), ("site.js", SITE_JS)):
        dst = ROOT / url.lstrip("/")
        if not dst.exists():
            shutil.copyfile(ASSET_DIR / name, dst)
        stem, ext = name.rsplit(".", 1)
        for old in ASSET_DIR.glob(f"{stem}.*.{ext}"):
            if old != dst:
                old.unlink()

ICON_SVG = {
    "discord": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>',
    "facebook": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 13.5h2.5l1-4H14v-2c0-1.03 0-2 2-2h1.5V2.14C17.174 2.097 15.943 2 14.643 2 11.928 2 10 3.657 10 6.7v2.8H7v4h3V22h4v-8.5z"/></svg>',
    "x": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.727-8.835L1.254 2.25H8.08l4.251 5.632 5.913-5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
}


def org_publisher() -> dict:
    return {"@type": "Organization", "@id": SITE + "/#organization", "name": "PlainBTC", "url": SITE + "/",
            "logo": {"@type": "ImageObject", "url": LOGO_PNG, "width": 512, "height": 512},
            "sameAs": list(SAME_AS)}


def community_links_html(lang: str, *, compact: bool = False) -> str:
    s = STR[lang]
    bits = []
    for key, url, label_k in COMMUNITY:
        raw = s.get(label_k, key)
        bits.append(
            f'<a class="community-link" href="{esc_attr(url)}" target="_blank" rel="noopener" '
            f'title="{esc_attr(raw)}">{ICON_SVG[key]}<span>{esc(raw)}</span></a>'
        )
    return "".join(bits)


def community_box_html(lang: str, *, home: bool = False) -> str:
    s = STR[lang]
    cls = "community-box home-community" if home else "community-box"
    aria = esc_attr(s.get("community_aria", "Community links"))
    return (
        f'      <aside class="{cls}" aria-label="{aria}">\n'
        f'        <h2>{esc(s["community_title"])}</h2>\n'
        f'        <p>{esc(s["community_text"])}</p>\n'
        f'        <div class="community-links">{community_links_html(lang)}</div>\n'
        f'      </aside>\n'
    )


def footer_social_html(lang: str) -> str:
    s = STR[lang]
    aria = esc_attr(s.get("community_aria", "Community links"))
    return (
        '  <!-- i18n:footersocial -->\n'
        f'  <div class="wrap footer-social" aria-label="{aria}">{community_links_html(lang)}</div>\n'
        '  <!-- /i18n:footersocial -->'
    )


def community_marker_html(lang: str, *, home: bool = False) -> str:
    return (
        '  <!-- i18n:community -->\n'
        + community_box_html(lang, home=home)
        + '  <!-- /i18n:community -->'
    )

def strip_community_boxes(h: str) -> str:
    """Remove every article/home community box (marked or unmarked). Idempotent cleanup."""
    h = re.sub(r"[ \t]*<!-- i18n:community -->.*?<!-- /i18n:community -->\s*", "\n", h, flags=re.S)
    # Unmarked leftovers from older build_article runs (SVG-heavy asides).
    h = re.sub(
        r"\s*<aside class=\"community-box(?: home-community)?\"[^>]*>.*?</aside>\s*",
        "\n",
        h,
        flags=re.S,
    )
    return h


def place_community(h: str, lang: str, *, home: bool, kind: str) -> str:
    """Ensure exactly one community block. Always strip first, then insert the marked block once."""
    h = strip_newsletter(strip_community_boxes(h))  # newsletter is re-placed afterwards by place_newsletter
    new = community_marker_html(lang, home=home)
    if home or kind == "home":
        m = re.search(r'(</section>)\s*(<section id="articles")', h, re.S)
        if m:
            return h[: m.end(1)] + "\n\n" + new + "\n    " + h[m.start(2) :]
        # fallback: after hero
        m = re.search(r'(</section>\s*)', h)
        if m:
            return h[: m.end(1)] + new + "\n" + h[m.end(1) :]
        errors.append(f"cannot place home community after strip")
        return h + "\n" + new
    m = re.search(r'(?P<pre>\n)(?P<rel>\s*<aside class="related")', h)
    if m:
        return h[: m.start("rel")] + "\n" + new + "\n" + h[m.start("rel") :]
    m = re.search(r'(?P<pre>\n)(?P<src>\s*<section class="sources")', h)
    if m:
        return h[: m.start("src")] + "\n" + new + "\n" + h[m.start("src") :]
    # inside </article> before close as last resort
    m = re.search(r'(</article>)', h)
    if m:
        return h[: m.start(1)] + "\n" + new + "\n    " + h[m.start(1) :]
    errors.append("cannot place community box after strip")
    return h

# ---------------------------------------------------------------- newsletter signup form
NLS = json.loads((ROOT / "i18n/newsletter.json").read_text(encoding="utf-8"))


def newsletter_box_html(lang: str, source: str) -> str:
    n = NLS[lang]
    dis = "/disclosure" if lang == DEFAULT else f"/{lang}/disclosure"
    da = lambda k: esc_attr(n[k])
    return (
        '  <!-- i18n:newsletter -->\n'
        '      <aside class="newsletter-box" aria-labelledby="nl-title">\n'
        f'        <h2 id="nl-title">{esc(n["form_title"])}</h2>\n'
        f'        <p>{esc(n["form_text"])}</p>\n'
        f'        <form class="newsletter-form" method="post" action="/api/subscribe" novalidate '
        f'data-ok="{da("msg_ok")}" data-invalid="{da("msg_invalid")}" data-rate="{da("msg_rate")}" '
        f'data-error="{da("msg_error")}" data-sending="{da("sending")}">\n'
        f'          <input type="hidden" name="lang" value="{lang}">\n'
        f'          <input type="hidden" name="source" value="{esc_attr(source)}">\n'
        '          <div class="nl-hp" aria-hidden="true"><label>Website <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>\n'
        f'          <label class="nl-label" for="nl-email">{esc(n["email_label"])}</label>\n'
        f'          <div class="nl-row"><input id="nl-email" type="email" name="email" required maxlength="254" '
        f'autocomplete="email" inputmode="email" placeholder="{da("placeholder")}">\n'
        f'          <button type="submit">{esc(n["button"])}</button></div>\n'
        '        </form>\n'
        '        <p class="nl-status" role="status" aria-live="polite"></p>\n'
        f'        <p class="nl-note">{esc(n["consent"])} <a href="{dis}">{esc(n["privacy_link"])}</a></p>\n'
        '      </aside>\n'
        '  <!-- /i18n:newsletter -->'
    )


def strip_newsletter(h: str) -> str:
    h = re.sub(r"[ \t]*<!-- i18n:newsletter -->.*?<!-- /i18n:newsletter -->\s*", "\n", h, flags=re.S)
    h = re.sub(r"\s*<aside class=\"newsletter-box\"[^>]*>.*?</aside>\s*", "\n", h, flags=re.S)  # unmarked leftovers
    return h


def place_newsletter(h: str, lang: str, kind: str, source: str) -> str:
    """Idempotent: strip every newsletter block (marked or not), then insert exactly one marked block."""
    h = strip_newsletter(h)
    new = newsletter_box_html(lang, source)
    if kind == "article":
        m = re.search(r"<!-- /i18n:community -->\s*", h)
        if m:
            tail = h[m.end():]
            return h[: m.start()] + "<!-- /i18n:community -->\n" + new + "\n\n" + (tail if tail.startswith(("<", " ")) else tail)
        m = re.search(r'\n(\s*<aside class="related")', h)
        if m:
            return h[: m.start(1)] + new + "\n\n" + h[m.start(1):]
    elif kind == "home":
        m = re.search(r'\s*(<section id="about")', h)
        if m:
            return h[: m.start()] + "\n\n" + new + "\n\n    " + h[m.start(1):]
    else:  # about / disclosure (prose pages)
        ms = list(re.finditer(r"\n(\s*</div>\s*</main>)", h))
        if ms:
            m = ms[-1]
            return h[: m.start()] + "\n\n" + new + h[m.start():]
    errors.append(f"cannot place newsletter form ({lang}/{kind}/{source})")
    return h


CFG = json.loads((ROOT / "i18n/langs.json").read_text(encoding="utf-8"))
LANGS = CFG["langs"]
DEFAULT = CFG["default"]
LANG = {l["code"]: l for l in LANGS}
ALLOWED = r"(</?(?:strong|em|code)>|<br>)"
errors: list[str] = []
warnings: list[str] = []


# ---------------------------------------------------------------- partners (i18n/partners.json)
# A partner is live only when enabled is true, url is a non-empty https:// link,
# and share_policy allows publishing it. Empty urls must not appear in HTML.
PARTNERS_CFG = json.loads((ROOT / "i18n/partners.json").read_text(encoding="utf-8"))
PARTNERS = PARTNERS_CFG.get("partners", [])
PARTNER_UI = PARTNERS_CFG.get("ui", {})


def _partner_url(p: dict) -> str:
    return (p.get("url") or "").strip()


def partner_by_id(pid: str) -> dict | None:
    for p in PARTNERS:
        if p.get("id") == pid:
            return p
    return None


def _apply_coinbase_url() -> None:
    """Use partners.json as the Coinbase URL source of truth (same default if unset)."""
    global REF_URL
    cb = partner_by_id("coinbase")
    if cb and _partner_url(cb).startswith("https://"):
        REF_URL = _partner_url(cb)


_apply_coinbase_url()


def partner_activation_error(p: dict) -> str | None:
    """Blocking error if a partner is marked live incorrectly; None if it stays dark or is valid."""
    url = _partner_url(p)
    if not p.get("enabled") or not url:
        return None
    pid = p.get("id") or "?"
    if not url.startswith("https://"):
        return f"partner {pid}: url must start with https://"
    policy = p.get("share_policy") or "allowed"
    if policy == "forbidden":
        return (
            f"partner {pid}: share_policy is forbidden — official terms do not allow "
            "publishing this referral link on a website. Leave url empty and enabled false."
        )
    if policy == "affiliate_only" and p.get("url_type") != "affiliate":
        return (
            f"partner {pid}: share_policy is affiliate_only. Use an approved affiliate URL "
            "and set url_type to 'affiliate' (do not publish a personal referral link)."
        )
    langs = p.get("languages") or []
    if not langs:
        return f"partner {pid}: languages must be a non-empty list"
    if pid == "coinbase":
        return None
    for lang in langs:
        cta = (p.get("cta") or {}).get(lang) or {}
        if not all(cta.get(k) for k in ("title", "text", "button")):
            return f"partner {pid}: missing cta title/text/button for language '{lang}'"
        if not (p.get("disclosure") or {}).get(lang):
            return f"partner {pid}: missing disclosure text for language '{lang}'"
        if lang not in PARTNER_UI:
            return f"partner {pid}: missing ui strings for language '{lang}' in partners.json"
    return None


def validate_partners() -> None:
    seen: list[str] = []
    for p in PARTNERS:
        pid = p.get("id")
        if not pid:
            errors.append("partners.json: a partner is missing id")
            continue
        if pid in seen:
            errors.append(f"partners.json: duplicate id {pid}")
        seen.append(pid)
        err = partner_activation_error(p)
        if err:
            errors.append(err)
        # Even while dark, require CTA copy for every listed language so activation is url+enabled only.
        for lang in p.get("languages") or []:
            card = (p.get("card") or {}).get(lang) or {}
            if p.get("enabled") and not (card.get("button") and card.get("benefit")):
                errors.append(f"partner {pid}: missing card button/benefit for language '{lang}'")
            for k, v in card.items():
                if isinstance(v, str) and ("\u2014" in v or "--" in v.replace("://", "")):
                    errors.append(f"partner {pid}: card.{lang}.{k} contains an em dash or double dash")
        if pid == "coinbase":
            continue
        for lang in p.get("languages") or []:
            cta = (p.get("cta") or {}).get(lang) or {}
            if not all(cta.get(k) for k in ("title", "text", "button")):
                errors.append(f"partner {pid}: prepare cta title/text/button for language '{lang}' before it can be enabled")
            if not (p.get("disclosure") or {}).get(lang):
                errors.append(f"partner {pid}: prepare disclosure text for language '{lang}' before it can be enabled")
            if lang not in PARTNER_UI:
                errors.append(f"partners.json: missing ui.{lang} strings used by partner {pid}")


def live_partners(lang: str) -> list[dict]:
    out = []
    for p in PARTNERS:
        if partner_activation_error(p):
            continue
        if not p.get("enabled") or not _partner_url(p).startswith("https://"):
            continue
        if lang in (p.get("languages") or []):
            out.append(p)
    return out


def extra_partners(lang: str) -> list[dict]:
    """Live partners other than Coinbase (Coinbase still uses the existing CTA path)."""
    return [p for p in live_partners(lang) if p.get("id") != "coinbase"]


def _slug_hash(slug: str, lang: str) -> int:
    return int(hashlib.sha256(f"{slug}|{lang}|plainbtc-cta-v1".encode()).hexdigest()[:8], 16)


# Coinbase-specific beginner / product guides stay on Coinbase when that partner is live.
COINBASE_PINNED_SLUGS = frozenset({
    "how-to-buy-first-bitcoin-coinbase",
    "coinbase-fees-explained",
    "how-to-cash-out-bitcoin-coinbase-to-bank",
    "is-coinbase-safe-for-beginners",
})
# Bitcoin-only / savings / DCA topics prefer River when River is live.
RIVER_HINT_SLUGS = frozenset({
    "how-much-bitcoin-should-a-beginner-buy-dca",
    "bitcoin-etf-vs-buying-bitcoin",
    "bitcoin-loses-50-week-moving-average-nov-2026",
    "bitcoin-volatility-liquidations-nov-2026",
    "river-referral-bonus",
    "will-bitcoin-hit-a-new-all-time-high-in-2026",
    "what-happens-if-you-only-buy-bitcoin-and-never-sell",
    "how-to-keep-bitcoin-safe-after-you-buy",
})
EXCHANGE_HINT_SLUGS = frozenset({
    "gemini-referral-bonus",
    "coinbase-fees-explained",
    "how-to-buy-first-bitcoin-coinbase",
    "how-to-cash-out-bitcoin-coinbase-to-bank",
    "is-coinbase-safe-for-beginners",
    "binance-hack-october-2022",
})

_PRIMARY_CACHE: dict[tuple[str, str], str | None] = {}
_PRIMARY_MAPS: dict[str, dict[str, str]] = {}


def article_slugs_for_lang(lang: str) -> list[str]:
    slugs = []
    seen = set()
    for slug in SLUGS:
        if slug in seen:
            continue
        if lang == DEFAULT:
            if slug in CONTENT or (ROOT / "articles" / f"{slug}.html").exists():
                slugs.append(slug)
                seen.add(slug)
        elif slug in CONTENT and lang in CONTENT[slug]:
            slugs.append(slug)
            seen.add(slug)
    return slugs


def _meta_for(slug: str) -> dict:
    return (CONTENT.get(slug, {}).get("meta") or {}) if slug in CONTENT else {}


def assign_primary_ids(lang: str) -> dict[str, str]:
    """One primary partner per article, deterministic and balanced among live partners."""
    if lang in _PRIMARY_MAPS:
        return _PRIMARY_MAPS[lang]
    live = live_partners(lang)
    ids = [p["id"] for p in live]
    slugs = article_slugs_for_lang(lang)
    assigned: dict[str, str] = {}
    if not ids:
        _PRIMARY_MAPS[lang] = assigned
        return assigned

    for slug in slugs:
        meta = _meta_for(slug)
        ov = meta.get("primary_partner")
        if ov == "none":
            continue
        if isinstance(ov, str) and ov in ids:
            assigned[slug] = ov
            continue
        if slug == "gemini-referral-bonus" and "gemini" in ids:
            assigned[slug] = "gemini"
        elif slug == "river-referral-bonus" and "river" in ids:
            assigned[slug] = "river"
        elif slug in COINBASE_PINNED_SLUGS and "coinbase" in ids:
            assigned[slug] = "coinbase"
        elif (slug in RIVER_HINT_SLUGS or _looks_river_topic(slug)) and "river" in ids:
            assigned[slug] = "river"

    remaining = [
        s for s in slugs
        if s not in assigned and _meta_for(s).get("primary_partner") != "none"
    ]

    from collections import Counter
    counts: Counter[str] = Counter(assigned.values())
    for i in ids:
        counts.setdefault(i, 0)

    exchange_ids = [i for i in ("gemini", "coinbase") if i in ids] or list(ids)

    def pick(slug: str, prefer: list[str]) -> str:
        cand = [i for i in prefer if i in ids] or ids
        minc = min(counts[c] for c in cand)
        tied = [c for c in ids if c in cand and counts[c] == minc]
        choice = tied[_slug_hash(slug, lang) % len(tied)]
        counts[choice] += 1
        return choice

    remaining_sorted = sorted(remaining, key=lambda s: (_slug_hash(s, lang), s))
    for slug in remaining_sorted:
        prefer = exchange_ids if (slug in EXCHANGE_HINT_SLUGS or _looks_exchange_topic(slug)) else ids
        assigned[slug] = pick(slug, prefer)

    _PRIMARY_MAPS[lang] = assigned
    return assigned


def _looks_river_topic(slug: str) -> bool:
    tokens = slug.replace("-", " ")
    if "coinbase" in slug or "gemini" in slug or "uphold" in slug:
        return False
    hints = ("dca", "savings", "never-sell", "keep-bitcoin-safe", "etf-vs-buying", "only-buy-bitcoin")
    return any(h in slug for h in hints)


def _looks_exchange_topic(slug: str) -> bool:
    hints = ("coinbase", "gemini", "binance", "exchange", "fees", "cash-out", "altcoin")
    return any(h in slug for h in hints)


def primary_partner_id(slug: str, lang: str) -> str | None:
    key = (lang, slug)
    if lang not in _PRIMARY_MAPS:
        assign_primary_ids(lang)
    if key not in _PRIMARY_CACHE:
        _PRIMARY_CACHE[key] = _PRIMARY_MAPS.get(lang, {}).get(slug)
    return _PRIMARY_CACHE.get(key)


def primary_partner(slug: str, lang: str, meta: dict | None = None) -> dict | None:
    if meta and meta.get("primary_partner") == "none":
        return None
    if meta and meta.get("primary_partner") in {p["id"] for p in live_partners(lang)}:
        pid = meta["primary_partner"]
    else:
        pid = primary_partner_id(slug, lang)
    if not pid:
        return None
    return next((p for p in live_partners(lang) if p["id"] == pid), None)


def partner_cta_copy(p: dict, lang: str) -> tuple[str, str, str, str]:
    """title, text, button, url for a live partner (Coinbase uses string catalog)."""
    s = STR[lang]
    url = _partner_url(p) if p["id"] != "coinbase" else REF_URL
    if p["id"] == "coinbase":
        return s["cta_title"], s["cta_text"], s["cta_button"], url
    cta = (p.get("cta") or {}).get(lang) or {}
    return (
        cta.get("title") or p.get("name") or p["id"],
        cta.get("text") or "",
        cta.get("button") or p.get("name") or p["id"],
        url,
    )


def partner_mid_copy(p: dict, lang: str) -> tuple[str, str, str, str]:
    s = STR[lang]
    url = _partner_url(p) if p["id"] != "coinbase" else REF_URL
    if p["id"] == "coinbase":
        return s["banner_title"], s["banner_text"], s["banner_button"], url
    cta = (p.get("cta") or {}).get(lang) or {}
    return (
        cta.get("title") or p.get("name") or p["id"],
        cta.get("text") or "",
        cta.get("button") or p.get("name") or p["id"],
        url,
    )


def _bitcoin_topic(slug: str) -> bool:
    return "bitcoin" in slug or "btc" in slug.split("-")


def secondary_partner(slug: str, lang: str, meta: dict | None, first: dict | None) -> dict | None:
    """A second, different live partner for the end card (None when only one partner is live).

    meta["secondary_partner"] pins it; Bitcoin-topic articles prefer River; otherwise rotate by slug."""
    if not first:
        return None
    live = [p for p in live_partners(lang) if p["id"] != first["id"]]
    if not live:
        return None
    ov = (meta or {}).get("secondary_partner")
    if ov == "none":
        return None
    if isinstance(ov, str):
        hit = next((p for p in live if p["id"] == ov), None)
        if hit:
            return hit
    if _bitcoin_topic(slug):
        hit = next((p for p in live if p["id"] == "river"), None)
        if hit:
            return hit
    return live[_slug_hash(slug, lang + "|second") % len(live)]


def partner_pair(slug: str, lang: str, meta: dict | None) -> tuple[dict | None, dict | None]:
    """(lead card partner, second card partner). Lead is the primary partner; on Bitcoin-topic
    articles without a manual primary_partner pin, River leads when it is in the pair."""
    first = primary_partner(slug, lang, meta)
    second = secondary_partner(slug, lang, meta, first)
    pinned = bool(meta and meta.get("primary_partner")) or slug in COINBASE_PINNED_SLUGS or slug in (
        "gemini-referral-bonus", "river-referral-bonus")
    if (not pinned and second and second["id"] == "river" and _bitcoin_topic(slug)):
        first, second = second, first
    return first, second


def partner_card_copy(p: dict, lang: str, variant: int = 1) -> tuple[str, str, str]:
    """button, benefit line, url for the compact referral card. variant 2 is the alternate pitch."""
    card = (p.get("card") or {}).get(lang) or {}
    url = REF_URL if p["id"] == "coinbase" else _partner_url(p)
    sfx = "2" if variant == 2 else ""
    button = card.get("button" + sfx) or card.get("button") or p.get("name") or p["id"]
    benefit = card.get("benefit" + sfx) or card.get("benefit") or ""
    return button, benefit, url


def referral_card_html(pg: Page, lang: str, p: dict, *, where: str, variant: int = 1) -> str:
    """Compact referral card: one CTA button, one benefit line, one tiny disclosure line.

    where="mid" renders <aside class="mid-cta ...">, where="end" renders <div class="cta ...">.
    The card holds no nested <div>/<aside> so the strip-and-replace regexes stay safe."""
    s = STR[lang]
    button, benefit, url = partner_card_copy(p, lang, variant)
    pid = esc_attr(p["id"])
    label = s.get("ref_label") or "Partner offer"
    note = s.get("ref_note") or "Referral link, we may earn a bonus."
    details = s.get("ref_details") or "Details"
    disc_href = internal(lang, "/disclosure")
    tag, cls = ("aside", "mid-cta") if where == "mid" else ("div", "cta")
    aria = f' aria-label="{esc_attr(label)}"' if where == "mid" else ""
    return (
        f'      <{tag} class="{cls} ref-card"{aria} data-partner-cta="{pid}">\n'
        f'        <p class="ref-benefit"><span class="ref-label">{esc(label)}</span> {esc(benefit)}</p>\n'
        f'        <a class="cta-button ref-button" href="{esc_attr(url)}" rel="sponsored noopener" target="_blank" data-partner="{pid}">{esc(button)}</a>\n'
        f'        <p class="ref-note">{esc(note)} <a href="{disc_href}">{esc(details)}</a></p>\n'
        f"      </{tag}>\n"
    )


def article_cards_html(pg: Page, lang: str, slug: str, meta: dict | None) -> tuple[str, str, list[dict]]:
    """(mid card, end card, partners used). Two different offers when possible."""
    first, second = partner_pair(slug, lang, meta)
    if not first:
        return "", "", []
    mid = referral_card_html(pg, lang, first, where="mid", variant=1)
    if second:
        end = referral_card_html(pg, lang, second, where="end", variant=1)
        return mid, end, [first, second]
    end = referral_card_html(pg, lang, first, where="end", variant=2)
    return mid, end, [first]


def single_partner_mid_html(pg: Page, lang: str, p: dict) -> str:
    return referral_card_html(pg, lang, p, where="mid", variant=1)


def single_partner_end_cta_html(pg: Page, lang: str, p: dict) -> str:
    return referral_card_html(pg, lang, p, where="end", variant=2)


def partner_disclosure_line(pg: Page, p: dict, lang: str) -> str:
    if p["id"] == "coinbase":
        return pg.inline(STR[lang].get("disc_affiliate") or "")
    raw = (p.get("disclosure") or {}).get(lang) or ""
    return pg.inline(raw) if raw else ""



def partners_disclosure_text(pg: Page, used: list[dict], lang: str) -> str:
    """One disclosure sentence for the card partners on an article (combined when there are two)."""
    ui = PARTNER_UI.get(lang) or {}
    if len(used) > 1 and ui.get("disc_multi"):
        names = [p.get("name") or p["id"] for p in used]
        joined = ", ".join(names[:-1]) + f" {ui.get('and', 'and')} " + names[-1]
        return pg.inline(ui["disc_multi"].replace("{names}", joined))
    return "<br><br>\n        ".join(x for x in (partner_disclosure_line(pg, p, lang) for p in used) if x)


def _partner_id_from_url(href: str) -> str | None:
    h = (href or "").lower()
    if "coinbase.com/join" in h:
        return "coinbase"
    if "exchange.gemini.com" in h:
        return "gemini"
    if "wallet.uphold.com" in h or "uphold.com/signup" in h:
        return "uphold"
    if "river.com/invite" in h or "/river.com/r/" in h:
        return "river"
    return None


def add_data_partner_attrs(h: str) -> str:
    """Add data-partner on referral anchors that do not already have it."""
    rules = (
        ("coinbase.com/join", "coinbase"),
        ("exchange.gemini.com", "gemini"),
        ("wallet.uphold.com", "uphold"),
        ("uphold.com/signup", "uphold"),
        ("river.com/invite", "river"),
        ("river.com/r/", "river"),
    )

    def inject(html: str, needle: str, pid: str) -> str:
        def repl(m: re.Match[str]) -> str:
            tag = m.group(0)
            if re.search(r"\bdata-partner=", tag, re.I):
                return tag
            if tag.endswith("/>"):
                return tag[:-2] + f' data-partner="{pid}"/>'
            return tag[:-1] + f' data-partner="{pid}">'

        return re.sub(
            rf'<a\b[^>]*href="[^"]*{re.escape(needle)}[^"]*"[^>]*>',
            repl,
            html,
            flags=re.I,
        )

    for needle, pid in rules:
        h = inject(h, needle, pid)
    return h


def cta_distribution(lang: str) -> dict[str, int]:
    from collections import Counter
    return dict(Counter(assign_primary_ids(lang).values()))


def format_cta_distribution() -> str:
    lines = ["CTA rotation (primary partner per article):"]
    for lang in (l["code"] for l in LANGS):
        dist = cta_distribution(lang)
        assigned = assign_primary_ids(lang)
        if not dist and not live_partners(lang):
            lines.append(f"  {lang}: none")
            continue
        bits = ", ".join(f"{k}={v}" for k, v in sorted(dist.items()))
        lines.append(f"  {lang}: {bits}  (n={len(assigned)})")
    return "\n".join(lines)



def partner_cta_slot_html(pg: Page, p: dict, lang: str) -> str:
    cta = (p.get("cta") or {}).get(lang) or {}
    url = esc_attr(_partner_url(p))
    name = p.get("name") or p.get("id") or "partner"
    title = cta.get("title") or name
    text = cta.get("text") or ""
    button = cta.get("button") or name
    return (
        f'        <div class="partner-slot" data-partner="{esc_attr(p["id"])}">\n'
        f"          <h3>{esc(title)}</h3>\n"
        f"          <p>{pg.inline(text)}</p>\n"
        f'          <a class="cta-button" href="{url}" rel="sponsored noopener" target="_blank">{esc(button)}</a>\n'
        "        </div>\n"
    )


def partners_end_cta_html(pg: Page, lang: str) -> str:
    extras = extra_partners(lang)
    if not extras:
        return ""
    ui = PARTNER_UI.get(lang) or PARTNER_UI.get("en") or {}
    slots = "".join(partner_cta_slot_html(pg, p, lang) for p in extras)
    title = ui.get("box_title") or "If you decide to open an account"
    intro = ui.get("box_intro") or ""
    return (
        '      <div class="cta partners-cta">\n'
        f"        <h2>{esc(title)}</h2>\n"
        f"        <p>{pg.inline(intro)}</p>\n"
        f"{slots}"
        "      </div>\n"
    )


def partner_mid_cta_html(pg: Page, p: dict, lang: str) -> str:
    return referral_card_html(pg, lang, p, where="mid", variant=1)


def partners_article_disclosure_html(pg: Page, lang: str) -> str:
    bits = []
    for p in extra_partners(lang):
        raw = (p.get("disclosure") or {}).get(lang) or ""
        if raw:
            bits.append(pg.inline(raw))
    return "<br><br>\n        ".join(bits)


def partners_page_html(pg: Page, lang: str) -> str:
    """Disclosure-page list of extra live partners. Empty when none are live (Coinbase stays in static English copy)."""
    extras = extra_partners(lang)
    if not extras:
        return ""
    ui = PARTNER_UI.get(lang) or PARTNER_UI.get("en") or {}
    items = []
    for p in extras:
        disc = (p.get("disclosure") or {}).get(lang) or ""
        if disc:
            items.append(f"        <li>{pg.inline(disc)}</li>")
    intro = ui.get("page_intro") or ""
    parts = ['      <div class="partner-list">']
    if intro:
        parts.append(f"        <p>{pg.inline(intro)}</p>")
    if items:
        parts.append("        <ul>")
        parts.extend(items)
        parts.append("        </ul>")
    parts.append("      </div>")
    return "\n".join(parts) + "\n"


def strip_partners(h: str) -> str:
    h = re.sub(r"[ \t]*<!-- i18n:partners -->.*?<!-- /i18n:partners -->\s*", "\n", h, flags=re.S)
    h = re.sub(r'\s*<div class="cta partners-cta"[^>]*>.*?</div>\s*', "\n", h, flags=re.S)
    h = re.sub(r'\s*<div class="partner-list"[^>]*>.*?</div>\s*', "\n", h, flags=re.S)
    return h



def unlink_nonprimary_referrals(h: str, primary_id: "str | set[str] | None") -> str:
    """Drop leftover referral anchors that are not one of this article's card partners."""
    keep = {primary_id} if isinstance(primary_id, str) else set(primary_id or ())
    dropped = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal dropped
        tag, inner = m.group(0), m.group(1)
        href_m = re.search(r'href="([^"]+)"', tag, re.I)
        href = href_m.group(1) if href_m else ""
        pid_m = re.search(r'\bdata-partner="([^"]+)"', tag, re.I)
        pid = (pid_m.group(1) if pid_m else _partner_id_from_url(href) or "")
        if pid and pid in keep:
            return tag
        dropped += 1
        return inner

    h = re.sub(
        r'<a\b[^>]*href="[^"]*(?:coinbase\.com/join|exchange\.gemini\.com|wallet\.uphold\.com|uphold\.com/signup|river\.com/invite|river\.com/r/)[^"]*"[^>]*>(.*?)</a>',
        repl,
        h,
        flags=re.I | re.S,
    )
    if dropped:
        h = re.sub(r"\s+through our referral link", "", h)
    return h



def related_slugs(lang: str, meta: dict) -> list[str]:
    out = []
    for r in meta.get("related") or []:
        if r not in CONTENT:
            continue
        if lang in CONTENT[r] or DEFAULT in CONTENT[r] or has_page(DEFAULT, "article", r):
            out.append(r)
    return out


def related_href_title(lang: str, slug: str) -> tuple[str, str]:
    href = path_for(lang if has_page(lang, "article", slug) else DEFAULT, "article", slug)
    if lang in CONTENT.get(slug, {}):
        title = CONTENT[slug][lang][0]["title"]
    else:
        title = CONTENT[slug][DEFAULT][0]["title"]
    return href, title


def place_related(h: str, lang: str, slug: str) -> str:
    meta = _meta_for(slug)
    rel = related_slugs(lang, meta)
    if not rel:
        return h
    s = STR[lang]
    lis = "\n".join(
        f'          <li><a href="{href}">{esc(title)}</a></li>'
        for href, title in (related_href_title(lang, r) for r in rel)
    )
    block = (
        f'      <aside class="related" aria-label="{esc_attr(s["related"])}">\n'
        f"        <h2>{esc(s['related'])}</h2>\n"
        "        <ul>\n"
        f"{lis}\n"
        "        </ul>\n"
        "      </aside>\n"
    )
    if re.search(r'<aside class="related"', h):
        return re.sub(r'\s*<aside class="related"[^>]*>.*?</aside>', "\n" + block, h, count=1, flags=re.S)
    m = re.search(r'(<section class="sources")', h)
    if m:
        return h[: m.start()] + block + "\n      " + h[m.start() :]
    return h


def place_partners(h: str, lang: str, kind: str, slug: str = "") -> str:
    """Place the single primary partner CTA on English pages; list partners on the disclosure page."""
    h = strip_partners(h)
    h = add_data_partner_attrs(h)
    pg = Page(lang)
    if kind == "article":
        meta = _meta_for(slug)
        part = primary_partner(slug, lang, meta)
        mid, end, used = article_cards_html(pg, lang, slug, meta)
        h = unlink_nonprimary_referrals(h, {p["id"] for p in used})
        if not part:
            s = STR[lang]
            end = (
                f'      <div class="cta">\n'
                f"        <h2>{esc(s['alt_cta_title'])}</h2>\n"
                f"        <p>{pg.inline(s['alt_cta_text'])}</p>\n"
                "      </div>\n"
            )
        if re.search(r'<aside class="mid-cta(?: [^"]*)?"', h):
            if mid:
                h = re.sub(r'\s*<aside class="mid-cta(?: [^"]*)?"[^>]*>.*?</aside>', "\n" + mid, h, count=1, flags=re.S)
            else:
                h = re.sub(r'\s*<aside class="mid-cta(?: [^"]*)?"[^>]*>.*?</aside>', "", h, count=1, flags=re.S)
        elif mid:
            m = re.search(r'(<div class="cta(?: [^"]*)?"[^>]*>)', h)
            if m:
                h = h[: m.start()] + mid + "\n" + h[m.start() :]
        if re.search(r'<div class="cta(?: [^"]*)?"', h):
            h = re.sub(r'\s*<div class="cta(?: [^"]*)?"[^>]*>.*?</div>', "\n" + end, h, count=1, flags=re.S)
        else:
            m = re.search(r'(<div class="disclosure">)', h)
            if m:
                h = h[: m.start()] + end + "\n      " + h[m.start() :]
            else:
                errors.append(f"cannot place partner CTA ({lang}/{slug or kind})")
        # Replace any existing affiliate sentence with the primary partner's disclosure.
        if used:
            disc = partners_disclosure_text(pg, used, lang)
            if disc:
                def _inject_disc(m):
                    inner = m.group(1)
                    # Drop previous Coinbase/affiliate lead sentence(s) before the advice line.
                    # Keep the not-advice paragraph, which follows the last <br><br> on EN pages.
                    if "<br><br>" in inner:
                        _, _, tail = inner.rpartition("<br><br>")
                        rebuilt = disc + "<br><br>\n        " + tail.strip()
                    else:
                        rebuilt = disc + "<br><br>\n        " + inner
                    return '<div class="disclosure">\n        ' + rebuilt + "\n      </div>"
                h2, n = re.subn(
                    r'<div class="disclosure">\s*(.*?)\s*</div>',
                    _inject_disc,
                    h,
                    count=1,
                    flags=re.S,
                )
                if n:
                    h = h2
    elif kind == "disclosure":
        extras = extra_partners(lang)
        if not extras:
            return h
        already = [x for x in extras if f'id="partner-{x["id"]}"' in h or f'<!-- partner:{x["id"]} -->' in h]
        if len(already) == len(extras):
            return h
        block = (
            "  <!-- i18n:partners -->\n"
            + partners_page_html(pg, lang)
            + "  <!-- /i18n:partners -->"
        )
        m = re.search(
            r"(<h2>(?:How we mark links|Cómo marcamos los enlaces|Como marcamos os links|Comment nous marquons les liens|Wie wir Links kennzeichnen)</h2>)",
            h,
        )
        if m:
            h = h[: m.start()] + block + "\n      " + h[m.start() :]
        else:
            errors.append(f"cannot place partners disclosure list ({lang})")
    return h



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
            return f'<a href="{REF_URL}" rel="sponsored noopener" target="_blank" data-partner="coinbase">{inner}</a>'
        if key.startswith("/"):
            return f'<a href="{internal(self.lang, key)}">{inner}</a>'
        href = self.links.get(key, key)
        if not href.startswith("http"):
            errors.append(f"[{self.lang}] unknown link key {key!r}")
        pid = _partner_id_from_url(href)
        if pid:
            if not any(p["id"] == pid for p in live_partners(self.lang)):
                return inner
            return (
                f'<a href="{esc_attr(href)}" rel="sponsored noopener" target="_blank" '
                f'data-partner="{esc_attr(pid)}">{inner}</a>'
            )
        return f'<a href="{esc_attr(href)}" target="_blank" rel="noopener">{inner}</a>'


# ---------------------------------------------------------------- site model
def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def en_articles_order() -> list[str]:
    """Slugs in the order the English home page lists them (newest first)."""
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    # The cards between the i18n:articles markers are the source of truth; other links (ticker, guide list)
    # are generated from that order and must not influence it.
    blk = re.search(r"<!-- i18n:articles -->(.*?)<!-- /i18n:articles -->", idx, re.S)
    if blk:
        idx = blk.group(1) + idx
    seen = []
    # Match both pretty URLs (/articles/<slug>) and legacy .html links.
    for m in re.finditer(r'href="(?:/articles/|articles/)([a-z0-9-]+)(?:\.html)?"', idx):
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
def pre(lang: str) -> str:
    """URL prefix of a language ('' for the default language)."""
    return "" if lang == DEFAULT else f"/{lang}"


def strip_tags(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


def article_kind(slug: str) -> str:
    """'guide' (evergreen) or 'news'. Set "kind" in meta.json to override."""
    meta = _meta_for(slug)
    return meta.get("kind") or ("guide" if meta.get("disclosure_variant") == "guide" else "news")


_PUB_CACHE: dict[str, str] = {}


def pub_iso(slug: str) -> str:
    """Publication time as ISO 8601. Uses the precise pubDate kept in feed.xml, else the meta.json date."""
    if not _PUB_CACHE:
        for k, v in en_feed_dates().items():
            try:
                _PUB_CACHE[k] = datetime.strptime(v, "%a, %d %b %Y %H:%M:%S GMT").strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except ValueError:
                pass
        _PUB_CACHE.setdefault("", "")
    return _PUB_CACHE.get(slug) or _meta_for(slug).get("date", "")


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


ICON_GLOBE = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/>'
              '<path d="M3 12h18M12 3c2.6 2.8 3.9 5.800 3.9 9s-1.300 6.200-3.900 9c-2.600-2.800-3.900-5.800-3.900-9s1.300-6.200 3.900-9z"/></svg>')
ICON_THEME = ('<svg class="ico ico-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
              '<path d="M12 2v2.500M12 19.500V22M2 12h2.500M19.500 12H22M4.900 4.900l1.800 1.800M17.300 17.300l1.800 1.800M4.900 19.100l1.800-1.800M17.300 6.700l1.800-1.800"/></svg>'
              '<svg class="ico ico-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.500A8.500 8.500 0 0 1 9.500 4a8.500 8.500 0 1 0 10.500 10.500z"/></svg>')
ICON_LINK = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a4.500 4.500 0 0 0 6.400 0l3-3a4.500 4.500 0 0 0-6.400-6.400l-1.200 1.200"/>'
             '<path d="M14 10a4.500 4.500 0 0 0-6.400 0l-3 3a4.500 4.500 0 0 0 6.400 6.400l1.200-1.200"/></svg>')
# The brand mark: noise on the left resolves into one plain line.
LOGO_MARK = ('<svg class="logo-mark" viewBox="0 0 40 20" aria-hidden="true">'
             '<path d="M1 10l2.500-6 3 12 3-10 3 7 2.500-5 2.500 2H39"/></svg>')


def logo_html(lang: str) -> str:
    return (f'<a class="logo" href="{pre(lang)}/" aria-label="PlainBTC">{LOGO_MARK}'
            '<span class="logo-word">Plain<span>BTC</span></span></a>')


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
            f'{ICON_GLOBE}<span class="lang-name">{esc(LANG[cur]["name"])}</span>'
            f'<span class="lang-code" aria-hidden="true">{esc(cur.upper())}</span></summary><ul>'
            + "".join(items) + "</ul></details>\n      <!-- /i18n:langmenu -->")


def footer_langs(kind: str, slug: str, cur: str) -> str:
    links = []
    for l in LANGS:
        target = path_for(l["code"], kind, slug) if has_page(l["code"], kind, slug) else path_for(l["code"], "home")
        links.append(f'<a href="{target}" lang="{l["hreflang"]}" hreflang="{l["hreflang"]}">{esc(l["name"])}</a>')
    return ('  <!-- i18n:footerlangs -->\n  <div class="wrap footer-langs"><nav aria-label="Languages">'
            + " ".join(links) + "</nav></div>\n  <!-- /i18n:footerlangs -->")


def og_tags(lang: str, title: str, desc: str, url: str, typ: str, image: str, alt: str, published: str = "",
            section: str = "") -> str:
    a = LANG[lang]
    extra = ""
    if published:
        extra += (f'\n  <meta property="article:published_time" content="{published}">'
                  f'\n  <meta property="article:modified_time" content="{published}">')
    if section:
        extra += f'\n  <meta property="article:section" content="{esc_attr(section)}">'
    return f'''  <meta property="og:type" content="{typ}">
  <meta property="og:title" content="{esc_attr(title)}">
  <meta property="og:description" content="{esc_attr(desc)}">
  <meta property="og:url" content="{url}">
  <meta property="og:site_name" content="PlainBTC">
  <meta property="og:locale" content="{a['locale']}">{extra}
  <meta property="og:image" content="{image}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{esc_attr(alt)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="{TWITTER_SITE}">
  <meta name="twitter:image" content="{image}">
  <meta name="twitter:title" content="{esc_attr(title)}">
  <meta name="twitter:description" content="{esc_attr(desc)}">'''


def jsonld(obj) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return "  <script type=\"application/ld+json\">\n" + "\n".join("  " + l for l in body.splitlines()) + "\n  </script>"


ROBOTS = "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"
# Runs before first paint: marks JS as available and applies a saved light/dark choice (no flash).
THEME_BOOT = ("(function(){var d=document.documentElement;d.classList.add('js');try{var t=localStorage.getItem('plainbtc-theme');"
              "if(t==='light'||t==='dark')d.setAttribute('data-theme',t)}catch(e){}})()")
# Webfont subset that covers the above-the-fold text of each language (ja/ko use system fonts).
FONT_PRELOAD = {"ru": ["cyrillic", "latin"], "ja": [], "ko": []}


def assets_block(lang: str) -> str:
    """Theme boot script, font preloads, stylesheet and icons. Identical on every page of a language."""
    fonts = "".join(
        f'  <link rel="preload" href="/assets/fonts/source-serif-4-{sub}.woff2" as="font" type="font/woff2" crossorigin>\n'
        for sub in FONT_PRELOAD.get(lang, ["latin"]))
    return f'''  <!-- i18n:assets -->
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#f4efe4">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#080e1d">
  <script>{THEME_BOOT}</script>
{fonts}  <link rel="stylesheet" href="{STYLES_CSS}">
  <link rel="icon" href="/favicon.ico?v=2" sizes="48x48">
  <link rel="icon" href="/assets/favicon.svg?v=2" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png?v=2">
  <link rel="manifest" href="/site.webmanifest">
  <!-- /i18n:assets -->'''


def head_html(lang, kind, slug, title, desc, og_title, og_desc, typ, image, ld, published="", section="") -> str:
    url = abs_url(path_for(lang, kind, slug))
    a = LANG[lang]
    return f'''<!DOCTYPE html>
<html lang="{a['hreflang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="{ROBOTS}">
{assets_block(lang)}
  <link rel="alternate" type="application/rss+xml" title="PlainBTC RSS ({esc_attr(a['name'])})" href="{pre(lang)}/feed.xml">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc_attr(desc)}">
  <link rel="canonical" href="{url}">
{hreflang_block(kind, slug, lang)}
{og_tags(lang, og_title, og_desc, url, typ, image, og_title, published, section)}
{ld}
</head>'''


def site_header_html(lang, kind, slug) -> str:
    s = STR[lang]
    p = pre(lang)
    cur = lambda k: ' aria-current="page"' if k == kind else ""
    return f'''  <header class="site-header">
    <div class="wrap inner">
      {logo_html(lang)}
      <input class="nav-toggle" type="checkbox" id="nav-toggle" aria-label="{esc_attr(s['menu'])}">
      <label class="nav-burger" for="nav-toggle" aria-hidden="true"><span></span><span></span></label>
      <nav class="nav" aria-label="Primary">
        <a href="{p}/#articles">{esc(s['nav_articles'])}</a>
        <a href="{p}/#guides">{esc(s['nav_guides'])}</a>
        <a href="{p}/about"{cur('about')}>{esc(s['nav_about'])}</a>
        <a href="{p}/disclosure"{cur('disclosure')}>{esc(s['nav_disclosure'])}</a>
      </nav>
      <div class="header-tools">
{lang_menu(kind, slug, lang)}
        <button class="theme-toggle" type="button" aria-label="{esc_attr(s['theme_toggle'])}" title="{esc_attr(s['theme_toggle'])}" hidden>{ICON_THEME}</button>
      </div>
    </div>
  </header>'''


def header_html(lang, kind, slug) -> str:
    s = STR[lang]
    return f'''<body>
  <a class="skip-link" href="#main">{esc(s['skip_link'])}</a>
{site_header_html(lang, kind, slug)}
'''


FOOTER_WAVE = ('<svg class="footer-wave" viewBox="0 0 1200 40" preserveAspectRatio="none" aria-hidden="true">'
               '<path d="M0 20l14-11 13 24 12-30 14 26 11-19 13 15 12-22 13 25 12-17 13 13 12-9 12 8 13-5 12 3h958"/></svg>')


def site_footer_html(lang, kind, slug) -> str:
    s = STR[lang]
    p = pre(lang)
    return f'''  <footer class="site-footer">
    {FOOTER_WAVE}
    <div class="wrap inner">
      <div class="footer-brand">
        {logo_html(lang)}
        <p>{esc(s['footer'])}</p>
      </div>
      <nav class="footer-nav" aria-label="Footer">
        <a href="{p}/">{esc(s['nav_home'])}</a>
        <a href="{p}/about">{esc(s['nav_about'])}</a>
        <a href="{p}/disclosure">{esc(s['nav_disclosure'])}</a>
        <a href="{p}/feed.xml">{esc(s['rss'])}</a>
      </nav>
    </div>
{footer_social_html(lang)}
{footer_langs(kind, slug, lang)}
    <div class="wrap footer-base"><a class="back-top" href="#top">{esc(s['back_top'])} <span aria-hidden="true">↑</span></a></div>
  </footer>'''


def footer_html(lang, kind, slug) -> str:
    return f'''{site_footer_html(lang, kind, slug)}
  <script src="{SITE_JS}" defer></script>
</body>
</html>
'''


def crumbs_html(lang: str, trail: list[tuple[str, str]], current: str = "") -> str:
    """Visible breadcrumb trail: [(label, href), ...] plus an optional unlinked current item."""
    s = STR[lang]
    sep = '<span class="crumb-sep" aria-hidden="true">/</span>'
    bits = [f'<a href="{href}">{esc(label)}</a>' for label, href in trail]
    if current:
        bits.append(f'<span aria-current="page">{esc(current)}</span>')
    return (f'      <!-- i18n:crumbs -->\n      <nav class="crumbs" aria-label="{esc_attr(s["crumbs_aria"])}">'
            + sep.join(bits) + "</nav>\n      <!-- /i18n:crumbs -->")


def share_html(lang: str, url: str, title: str) -> str:
    s = STR[lang]
    from urllib.parse import quote
    def tagged(src: str) -> str:
        return quote(f"{url}?utm_source={src}&utm_medium=social", safe="")
    x = f"https://x.com/intent/post?url={tagged('x')}&text={quote(title, safe='')}"
    fb = f"https://www.facebook.com/sharer/sharer.php?u={tagged('facebook')}"
    return (f'        <div class="share" role="group" aria-label="{esc_attr(s["share"])}">\n'
            f'          <span class="share-label">{esc(s["share"])}</span>\n'
            f'          <a class="share-btn" href="{esc_attr(x)}" target="_blank" rel="noopener nofollow" aria-label="X">{ICON_SVG["x"]}</a>\n'
            f'          <a class="share-btn" href="{esc_attr(fb)}" target="_blank" rel="noopener nofollow" aria-label="Facebook">{ICON_SVG["facebook"]}</a>\n'
            f'          <button class="share-btn share-copy" type="button" data-url="{esc_attr(url)}" data-copied="{esc_attr(s["share_copied"])}" '
            f'aria-label="{esc_attr(s["share_copy"])}" title="{esc_attr(s["share_copy"])}" hidden>{ICON_LINK}</button>\n'
            f'          <span class="share-status" role="status" aria-live="polite"></span>\n'
            '        </div>\n')


def article_head_html(lang: str, slug: str, label: str, h1_html: str, meta_html: str) -> str:
    """Top of an article: breadcrumbs, label, headline, byline, share row and the hero image."""
    s = STR[lang]
    url = abs_url(path_for(lang, "article", slug))
    crumbs = crumbs_html(lang, [("PlainBTC", pre(lang) + "/"), (s["nav_articles"], pre(lang) + "/#articles")])
    crumbs = crumbs.replace("\n      ", "\n        ").replace("      <!--", "        <!--", 1)
    return f'''      <!-- i18n:arthead -->
      <header class="article-head">
{crumbs}
        <div class="badge">{esc(label)}</div>
        <h1>{h1_html}</h1>
        <div class="meta">{meta_html}</div>
{share_html(lang, url, strip_tags(h1_html))}      </header>
      <img class="og-hero" src="/assets/og/{slug}.png" width="1200" height="630" alt="{esc_attr(_html.unescape(strip_tags(h1_html)))}" loading="eager" fetchpriority="high" decoding="async">
      <!-- /i18n:arthead -->'''


def article_main_open(lang: str) -> str:
    """<main> of an article page; the data attributes carry the localized strings site.js needs."""
    s, n = STR[lang], NLS[lang]
    return (f'<main class="article-page" id="main" data-toc="{esc_attr(s["toc"])}" data-nl="{esc_attr(n["form_title"])}" '
            f'data-nl-cta="{esc_attr(n["button"])}" data-close="{esc_attr(s["close"])}">')


def readtime_html(lang: str, slug: str) -> str:
    n = _meta_for(slug).get("readtime")
    if not n:
        return ""
    return f'<span class="meta-read"> · {esc(STR[lang]["readtime"].format(n=n))}</span>'


def article_ld(lang: str, slug: str, head: dict, ptitle: str, extra: list[dict]) -> str:
    s = STR[lang]
    url = abs_url(path_for(lang, "article", slug))
    img = f"{SITE}/assets/og/{slug}.png"
    when = pub_iso(slug)
    ld = jsonld({
        "@context": "https://schema.org", "@type": "Article" if article_kind(slug) == "guide" else "NewsArticle",
        "headline": head["title"], "name": ptitle, "description": head["description"],
        "datePublished": when, "dateModified": when,
        "author": {"@type": "Organization", "name": "PlainBTC", "url": SITE + "/"},
        "publisher": org_publisher(),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url,
        "image": {"@type": "ImageObject", "url": img, "width": 1200, "height": 630},
        "articleSection": head["label"], "isAccessibleForFree": True,
        "inLanguage": LANG[lang]["hreflang"],
    }) + "\n" + jsonld({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": s["nav_home"], "item": abs_url(path_for(lang, "home"))},
            {"@type": "ListItem", "position": 2, "name": head["title"], "item": url}]})
    for x in extra:
        ld += "\n" + jsonld(x)
    return ld


def render_blocks(pg: Page, blocks: list[dict], indent="      ") -> str:
    out = []
    for b in blocks:
        t = b["t"]
        if t in ("p", "h2", "h3", "blockquote"):
            out.append(f"{indent}<{t}>{pg.inline(b['text'])}</{t}>")
        elif t in ("ul", "ol"):
            lis = "\n".join(f"{indent}  <li>{pg.inline(i)}</li>" for i in b["items"])
            out.append(f"{indent}<{t}>\n{lis}\n{indent}</{t}>")
        elif t == "partners":
            # Extra live partners on a disclosure page. Renders nothing until a URL is filled.
            html = partners_page_html(pg, pg.lang).rstrip()
            if html:
                out.append(html)
        else:
            raise ValueError(f"unexpected block {t}")
    return "\n".join(out)


def plain_text(pg, text: str) -> str:
    """Render an inline-markup string as plain text (for JSON-LD)."""
    h = pg.inline(text)
    h = re.sub(r"<br\s*/?>", " ", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\s+", " ", _html.unescape(h)).strip()


def extra_jsonld(pg, head: dict, blocks: list[dict], url: str, lang: str) -> list[dict]:
    """FAQPage / HowTo JSON-LD from `!faq` / `!howto` markers.

    `!faq`   -> placed right before the FAQ `##` heading; each following `###` is a question and the
               paragraphs/lists until the next `###`/`##`/`!` block are its answer.
    `!howto` -> placed right before the `##` heading of the how-to section; that heading is the name,
               the first `ol` after it holds the steps (leading <strong>..</strong> = step name).
    """
    out = []
    for i, b in enumerate(blocks):
        if b["t"] == "faq":
            qa, q, ans, seen_h2 = [], None, [], False
            for nb in blocks[i + 1:]:
                t = nb["t"]
                if t == "h2" and not seen_h2:
                    seen_h2 = True
                    continue
                if t == "h3":
                    if q is not None and ans:
                        qa.append((q, " ".join(ans)))
                    q, ans = plain_text(pg, nb["text"]), []
                elif t in ("p", "ul", "ol") and q is not None:
                    if t == "p":
                        ans.append(plain_text(pg, nb["text"]))
                    else:
                        ans.extend(plain_text(pg, x) for x in nb["items"])
                else:
                    break
            if q is not None and ans:
                qa.append((q, " ".join(ans)))
            if qa:
                out.append({"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": LANG[lang]["hreflang"],
                            "mainEntity": [{"@type": "Question", "name": a,
                                            "acceptedAnswer": {"@type": "Answer", "text": r}} for a, r in qa]})
        elif b["t"] == "howto":
            name, steps, intro = None, [], []
            for nb in blocks[i + 1:]:
                t = nb["t"]
                if t == "h2" and name is None:
                    name = plain_text(pg, nb["text"])
                elif t == "p" and name is not None and not steps:
                    intro.append(plain_text(pg, nb["text"]))
                elif t == "ol" and name is not None:
                    for k, item in enumerate(nb["items"], 1):
                        m = re.match(r"\s*<strong>(.*?)</strong>\s*(.*)", item, re.S)
                        sname = plain_text(pg, m.group(1)) if m else plain_text(pg, item)
                        stext = plain_text(pg, item)
                        steps.append({"@type": "HowToStep", "position": k, "name": sname, "text": stext})
                    break
                elif t in ("faq", "howto", "end_cta", "figure", "mid_cta", "takeaways"):
                    break
            if name and steps:
                d = {"@context": "https://schema.org", "@type": "HowTo", "name": name, "inLanguage": LANG[lang]["hreflang"],
                     "description": " ".join(intro) or head["description"], "step": steps}
                out.append(d)
    return out


# ---------------------------------------------------------------- page builders
def build_article(lang: str, slug: str):
    s, c = STR[lang], CONTENT[slug]
    head, blocks = c[lang]
    meta = c["meta"]
    pg = Page(lang, c["links"])
    url = abs_url(path_for(lang, "article", slug))
    img = f"{SITE}/assets/og/{slug}.png"
    ptitle = f"{head['page_title']} | PlainBTC"
    ld = article_ld(lang, slug, head, ptitle, extra_jsonld(pg, head, blocks, url, lang))
    parts = [head_html(lang, "article", slug, ptitle, head["description"], head["title"], head["og_description"],
                       "article", img, ld, meta["date"], head["label"])]
    parts.append(header_html(lang, "article", slug))
    time_html = f'<time datetime="{meta["date"]}">{esc(fmt_date(lang, meta["date"]))}</time>'
    pub = esc(s["published"]).format(date=time_html, country=esc(s["country"]))
    body = [f'''  {article_main_open(lang)}
    <article class="content">
{article_head_html(lang, slug, head['label'], esc(head['title']), pub + readtime_html(lang, slug))}
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
        if t in ("faq", "howto"):
            continue   # structural markers for JSON-LD only
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
        <img src="{src}" width="{fig['w']}" height="{fig['h']}" alt="{esc_attr(alt)}" loading="lazy" decoding="async">
        <figcaption>{esc(cap)}</figcaption>
      </figure>
'''
                )
        elif t == "mid_cta":
            mid_html, _end_html, _used = article_cards_html(pg, lang, slug, meta)
            if mid_html:
                body.append(mid_html)
        elif t == "soft":
            body.append(f'      <p class="soft-guide">{pg.inline(b["text"])}</p>\n')
        elif t == "end_cta":
            _mid_html, end_html, _used = article_cards_html(pg, lang, slug, meta)
            if end_html:
                body.append(end_html)
            else:
                # Non-affiliate closer: newsletter + community sit just below; related guides follow.
                body.append(f'''      <div class="cta">
        <h2>{esc(s['alt_cta_title'])}</h2>
        <p>{pg.inline(s['alt_cta_text'])}</p>
      </div>
''')
        elif t == "disclosure":
            _m, _e, used = article_cards_html(pg, lang, slug, meta)
            adv = s["not_advice_" + meta.get("disclosure_variant", "std")]
            aff_parts = []
            line = partners_disclosure_text(pg, used, lang)
            if line:
                aff_parts.append(line)
            aff = ("<br><br>\n        ".join(aff_parts) + "<br><br>\n        ") if aff_parts else ""
            body.append(f'      <div class="disclosure">\n        {aff}{pg.inline(adv)}\n      </div>\n')
        else:
            errors.append(f"[{lang}/{slug}] unknown block {t}")
    flush()
    body.append(community_marker_html(lang))
    rel = related_slugs(lang, meta)
    if rel:
        lis = "\n".join(
            f'          <li><a href="{href}">{esc(title)}</a></li>'
            for href, title in (related_href_title(lang, r) for r in rel)
        )
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


def card_thumb_src(slug: str) -> tuple[str, int, int]:
    """Prefer topical 640×360 thumb.webp (or .jpg); fall back to OG PNG."""
    d = ROOT / "assets" / "img" / slug
    for name, w, h in (("thumb.webp", 640, 360), ("thumb.jpg", 640, 360)):
        if (d / name).exists():
            return f"/assets/img/{slug}/{name}", w, h
    return f"/assets/og/{slug}.png", 1200, 630


def visible_slugs(lang: str) -> list[str]:
    """Articles listed on this language's home page, newest first."""
    return [x for x in SLUGS if x in CONTENT and lang in CONTENT[x]]


def card_html(lang: str, slug: str, *, lead: bool = False) -> str:
    s = STR[lang]
    head = CONTENT[slug][lang][0]
    meta = CONTENT[slug]["meta"]
    href = path_for(lang, "article", slug)
    thumb, tw, th = card_thumb_src(slug)
    sep = '<span class="sep" aria-hidden="true"> · </span>'
    m = (f'<span class="kicker">{esc(head["label"])}</span>{sep}'
         f'<time datetime="{meta["date"]}">{esc(fmt_date(lang, meta["date"]))}</time>{sep}'
         f'<span>{esc(s["readtime"].format(n=meta["readtime"]))}</span>')
    # The lead story is above the fold: load its image eagerly. Everything else is lazy.
    load = 'loading="eager" fetchpriority="high"' if lead else 'loading="lazy"'
    cls = "card card-lead" if lead else "card"
    return f'''      <article class="{cls}" data-kind="{article_kind(slug)}">
        <a class="card-thumb" href="{href}" tabindex="-1" aria-hidden="true">
          <img src="{thumb}" width="{tw}" height="{th}" alt="{esc_attr(head['title'])}" {load} decoding="async">
        </a>
        <div class="card-body">
          <div class="meta">{m}</div>
          <h3><a href="{href}">{esc(head["title"])}</a></h3>
          <p>{esc(head['summary'])}</p>
          <a class="read-more" href="{href}" tabindex="-1" aria-hidden="true">{esc(s['read_article'])}</a>
        </div>
      </article>'''


def article_cards(lang):
    """Home-page article cards with topical thumbnails. Future articles get a thumb automatically."""
    s = STR[lang]
    cards = [card_html(lang, slug, lead=(i == 0)) for i, slug in enumerate(visible_slugs(lang))]
    out = "\n\n".join(cards[:HOME_VISIBLE])
    if cards[HOME_VISIBLE:]:
        out += (f'\n\n      <details class="older">\n        <summary>{esc(s["older_articles"])}</summary>\n'
                '        <div class="article-grid">\n' + "\n\n".join(cards[HOME_VISIBLE:]) + "\n        </div>\n      </details>")
    return out


def split_words(text: str) -> str:
    """Wrap each word for the staggered headline reveal (pure CSS; the text stays readable without it)."""
    words = text.split(" ")
    last = len(words) - 1
    return " ".join(
        f'<span class="w{" w-last" if i == last and last > 0 else ""}" style="--i:{i}"><span>{esc(w)}</span></span>'
        for i, w in enumerate(words))


def hero_art_html() -> str:
    """Static 'noise becomes a plain line' graphic. site.js animates it; without JS this drawing stays."""
    seed, pts, lens = 20261110, [], 700
    for x in range(0, lens + 1, 10):
        seed = (seed * 1103515245 + 12345) % 2147483648
        n = seed / 2147483648 * 2 - 1
        amp = 86 * min(1.0, (lens - x) / 300) ** 1.4
        pts.append(f"{x} {120 + n * amp:.1f}")
    return f'''      <div class="hero-art" aria-hidden="true">
        <svg class="wave" viewBox="0 0 1200 240" preserveAspectRatio="none" focusable="false">
          <path class="wave-noise" vector-effect="non-scaling-stroke" d="M{' L'.join(pts)}"/>
          <path class="wave-plain" vector-effect="non-scaling-stroke" d="M{lens} 120H1200"/>
        </svg>
        <span class="wave-lens"><span class="wave-chip">plain</span></span>
      </div>'''


def ticker_html(lang: str, slugs: list[str]) -> str:
    s = STR[lang]
    lis = "".join(
        f'<li><a href="{path_for(lang, "article", x)}">{esc(CONTENT[x][lang][0]["title"])}</a></li>' for x in slugs)
    return f'''    <div class="ticker" role="region" aria-label="{esc_attr(s['ticker_label'])}">
      <span class="ticker-label">{esc(s['ticker_label'])}</span>
      <div class="ticker-viewport"><ul class="ticker-track">{lis}</ul></div>
    </div>'''


def home_main(lang: str, h1_text: str, lead_html: str, about_html: str) -> str:
    """<main> of a home page. Used for every language; the English hero copy comes from index.html itself."""
    s = STR[lang]
    p = pre(lang)
    slugs = visible_slugs(lang)
    latest = max((CONTENT[x]["meta"]["date"] for x in slugs), default=date.today().isoformat())
    n_sources = sum(len(CONTENT[x]["meta"].get("sources") or []) for x in slugs)
    stats = "".join(
        f'<div class="stat"><dt>{esc(s[k])}</dt><dd data-count="{n}">{n}</dd></div>'
        for k, n in (("stat_articles", len(slugs)), ("stat_langs", len(LANGS)), ("stat_sources", n_sources)))
    guides = [x for x in slugs if article_kind(x) == "guide"]
    guides_html = ""
    if guides:
        lis = "\n".join(
            f'        <li><a href="{path_for(lang, "article", x)}"><span class="guide-n" aria-hidden="true">{i:02d}</span>'
            f'<span class="guide-t">{esc(CONTENT[x][lang][0]["title"])}</span>'
            f'<span class="guide-m">{esc(s["readtime"].format(n=CONTENT[x]["meta"]["readtime"]))}</span></a></li>'
            for i, x in enumerate(guides, 1))
        guides_html = f'''
    <section id="guides" class="wrap section" aria-labelledby="guides-title">
      <div class="section-head"><h2 id="guides-title">{esc(s['guides_title'])}</h2></div>
      <ul class="guide-list">
{lis}
      </ul>
    </section>
'''
    return f'''  <main id="main">
{ticker_html(lang, slugs[:8])}
    <section class="hero">
      <div class="wrap hero-copy">
        <div class="badge">{esc(s['hero_badge'].format(date=fmt_date(lang, latest)))}</div>
        <h1>{split_words(h1_text)}</h1>
        <p class="hero-lead">{lead_html}</p>
        <div class="hero-actions">
          <a class="btn btn-primary" href="#articles">{esc(s['hero_cta_latest'])}</a>
          <a class="btn btn-ghost" href="#guides">{esc(s['hero_cta_guides'])}</a>
        </div>
      </div>
{hero_art_html()}
      <dl class="wrap stats" aria-label="{esc_attr(s['stats_aria'])}">{stats}</dl>
    </section>

    <section id="articles" class="wrap section" aria-labelledby="articles-title">
      <div class="section-head"><h2 id="articles-title">{esc(s['section_latest'])}</h2><a class="section-link" href="{p}/feed.xml">{esc(s['rss'])}</a></div>
      <div class="article-grid">
  <!-- i18n:articles -->
{article_cards(lang)}
  <!-- /i18n:articles -->
      </div>
    </section>
{guides_html}
    <section class="wrap loop">
{community_marker_html(lang, home=True)}
{newsletter_box_html(lang, path_for(lang, "home"))}
    </section>

    <section id="about" class="wrap about-box">
      <div class="disclosure">
        {about_html}
      </div>
    </section>
  </main>'''


def home_ld(lang: str) -> str:
    s = STR[lang]
    url = abs_url(path_for(lang, "home"))
    hl = LANG[lang]["hreflang"]
    items = [{"@type": "ListItem", "position": i, "url": abs_url(path_for(lang, "article", x)),
              "name": CONTENT[x][lang][0]["title"]} for i, x in enumerate(visible_slugs(lang)[:10], 1)]
    out = [jsonld({"@context": "https://schema.org", "@type": "WebSite", "@id": url + "#website", "name": "PlainBTC",
                   "url": url, "description": s["tagline"], "inLanguage": hl,
                   "publisher": {"@id": SITE + "/#organization"}}),
           jsonld({"@context": "https://schema.org", **org_publisher()})]
    if items:
        out.append(jsonld({"@context": "https://schema.org", "@type": "ItemList", "name": s["section_latest"],
                           "itemListElement": items}))
    return "\n".join(out)


def build_home(lang):
    s = STR[lang]
    pg = Page(lang)
    img = f"{SITE}/assets/og/default.png"
    h = head_html(lang, "home", "", s["home_title"], s["home_description"], s["home_title"], s["home_og_description"],
                  "website", img, home_ld(lang))
    return "\n".join([h, header_html(lang, "home", ""),
                      home_main(lang, s["hero_h1"], esc(s["hero_p"]), pg.inline(s["about_box"])) + "\n",
                      footer_html(lang, "home", "")])


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
    return "\n".join([h, header_html(lang, kind, ""), f'''  <main class="prose-page" id="main">
    <div class="content">
{crumbs_html(lang, [("PlainBTC", pre(lang) + "/")], s["nav_" + kind])}
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
                         f"      <pubDate>{pd}</pubDate>\n      <category>{esc(h['label'])}</category>\n"
                         f"      <description>{esc(h['summary'])}</description>\n    </item>")
    last = max(dates.values(), key=lambda x: datetime.strptime(x, "%a, %d %b %Y %H:%M:%S GMT")) if dates else "Mon, 09 Nov 2026 12:00:00 GMT"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>PlainBTC</title>
    <link>{abs_url(path_for(lang, "home"))}</link>
    <description>{esc(s['tagline'])}</description>
    <language>{LANG[lang]['hreflang'].lower()}</language>
    <lastBuildDate>{last}</lastBuildDate>
    <atom:link href="{SITE}{pre(lang)}/feed.xml" rel="self" type="application/rss+xml"/>
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
        if kind == "article":
            alt_xml += f"\n    <image:image>\n      <image:loc>{SITE}/assets/og/{slug}.png</image:loc>\n    </image:image>"
        for l in LANGS:
            if has_page(l["code"], kind, slug):
                loc = abs_url(path_for(l["code"], kind, slug))
                urls.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lm}</lastmod>\n    <changefreq>{cf}</changefreq>\n    <priority>{pr}</priority>{alt_xml}\n  </url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
            + "\n".join(urls) + "\n</urlset>\n")


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


LD_BLOCK = re.compile(r'[ \t]*<script type="application/ld\+json">(.*?)</script>', re.S)


def normalize_en_links(h: str) -> str:
    """Hand-written English pages used relative *.html links; point them at the canonical pretty URLs."""
    h = re.sub(r'href="(?:\.\./|/)?index\.html(#[^"]*)?"', lambda m: f'href="/{m.group(1) or ""}"', h)
    h = re.sub(r'href="(?:\.\./|/)?(about|disclosure)\.html"', r'href="/\1"', h)
    h = re.sub(r'href="(?:\.\./|/)?feed\.xml"', 'href="/feed.xml"', h)
    h = re.sub(r'href="(?:\.\./|/)?(?:articles/)?([a-z0-9-]+)\.html"',
               lambda m: f'href="/articles/{m.group(1)}"' if (ROOT / "articles" / f"{m.group(1)}.html").exists() else m.group(0), h)
    return h


def replace_shell(h: str, lang: str, kind: str, slug: str, *, robots: str = ROBOTS) -> str:
    """Head assets, site header, footer and script tag of a hand-written page (same markup as generated pages)."""
    h = normalize_en_links(h)
    # <head>: one assets block instead of loose icon / stylesheet links
    h = re.sub(r'[ \t]*<!-- i18n:assets -->.*?<!-- /i18n:assets -->\n?', "", h, flags=re.S)
    h = re.sub(r'[ \t]*<link rel="(?:icon|stylesheet|apple-touch-icon|manifest|preload)"[^>]*>\n?', "", h)
    h = re.sub(r'[ \t]*<meta name="(?:color-scheme|theme-color)"[^>]*>\n?', "", h)
    h, n = re.subn(r'(<meta name="robots" content=")[^"]*(">\n)', lambda m: m.group(1) + robots + m.group(2) + assets_block(lang) + "\n", h, count=1)
    if not n:
        h, n = re.subn(r'(<meta name="viewport"[^>]*>\n)',
                       lambda m: m.group(1) + f'  <meta name="robots" content="{robots}">\n' + assets_block(lang) + "\n", h, count=1)
    if not n:
        errors.append(f"cannot place head assets ({kind}/{slug})")
    if 'name="twitter:site"' not in h:
        h = re.sub(r'([ \t]*<meta name="twitter:card"[^>]*>\n)',
                   lambda m: m.group(1) + f'  <meta name="twitter:site" content="{TWITTER_SITE}">\n', h, count=1)
    if 'property="og:locale"' not in h:
        h = re.sub(r'([ \t]*<meta property="og:site_name"[^>]*>\n)',
                   lambda m: m.group(1) + f'  <meta property="og:locale" content="{LANG[lang]["locale"]}">\n', h, count=1)
    if 'property="og:image:type"' not in h:
        h = re.sub(r'([ \t]*<meta property="og:image" content="[^"]*\.png">\n)',
                   lambda m: m.group(1) + '  <meta property="og:image:type" content="image/png">\n', h, count=1)
    # <body>: skip link + header, footer, script
    hk = "home" if kind == "404" else kind
    top = f'  <a class="skip-link" href="#main">{esc(STR[lang]["skip_link"])}</a>\n' + site_header_html(lang, hk, slug)
    h, n = re.subn(r'[ \t]*(?:<a class="skip-link"[^>]*>.*?</a>\s*)?<header class="site-header">.*?</header>', lambda m: top, h, count=1, flags=re.S)
    if not n:
        errors.append(f"cannot place site header ({kind}/{slug})")
    h, n = re.subn(r'[ \t]*<footer class="site-footer">.*?</footer>', lambda m: site_footer_html(lang, hk, slug), h, count=1, flags=re.S)
    if not n:
        errors.append(f"cannot place site footer ({kind}/{slug})")
    script = f'<script src="{SITE_JS}" defer></script>'
    h, n = re.subn(r'<script src="/assets/site[^"]*"[^>]*></script>', script, h, count=1)
    if not n:
        h = h.replace("</body>", f"  {script}\n</body>", 1)
    h = re.sub(r"<main(?![^>]*\bid=)", '<main id="main"', h, count=1)
    return h


def patch_article_head(h: str, slug: str) -> str:
    """Rebuild the top of a hand-written English article (breadcrumbs, label, h1, byline, share, hero image).

    The label, headline and byline text are read back from the page, so hand edits to them survive."""
    m = re.search(r'<article class="content">\s*', h)
    if not m:
        errors.append(f"no <article class=\"content\"> in articles/{slug}.html")
        return h
    blk = re.search(r"[ \t]*<!-- i18n:arthead -->.*?<!-- /i18n:arthead -->", h, re.S)
    if blk:
        a, b = blk.span()
    else:
        a = m.end()
        meta_m = re.compile(r'<div class="meta">.*?</div>', re.S).search(h, a)
        img_m = re.compile(r'<img class="og-hero"[^>]*>').search(h, a)
        if not meta_m:
            errors.append(f"no byline (.meta) in articles/{slug}.html")
            return h
        b = img_m.end() if img_m and img_m.start() - meta_m.end() < 200 else meta_m.end()
    region = h[a:b]
    badge = re.search(r'<div class="badge">(.*?)</div>', region, re.S)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", region, re.S)
    meta = re.search(r'<div class="meta">(.*?)</div>', region, re.S)
    if not (badge and h1 and meta):
        errors.append(f"cannot read label/h1/byline in articles/{slug}.html")
        return h
    byline = re.sub(r'<span class="meta-read">.*?</span>', "", meta.group(1)).strip()
    iso = _meta_for(slug).get("date") or ""
    if iso and "<time" not in byline:
        shown = fmt_date(DEFAULT, iso)
        byline = byline.replace(shown, f'<time datetime="{iso}">{shown}</time>', 1)
    new = article_head_html(DEFAULT, slug, _html.unescape(strip_tags(badge.group(1))), h1.group(1).strip(),
                            byline + readtime_html(DEFAULT, slug))
    # Without a marker block the regex above already consumed the indentation after <article>.
    return h[:a] + (new if blk else new.lstrip()) + h[b:]


def upgrade_article_jsonld(h: str, slug: str) -> str:
    """Bring hand-written English JSON-LD in line with the generated pages (publisher logo, type, section)."""
    label = (CONTENT.get(slug, {}).get(DEFAULT) or [{}])[0].get("label", "")

    def fix(m):
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            warnings.append(f"invalid JSON-LD left as is in articles/{slug}.html")
            return m.group(0)
        if isinstance(obj, dict) and obj.get("@type") in ("NewsArticle", "Article", "BlogPosting"):
            obj["@type"] = "Article" if article_kind(slug) == "guide" else "NewsArticle"
            when = pub_iso(slug)
            if when:
                if obj.get("dateModified") in (None, obj.get("datePublished")):
                    obj["dateModified"] = when
                obj["datePublished"] = when
            obj["author"] = {"@type": "Organization", "name": "PlainBTC", "url": SITE + "/"}
            obj["publisher"] = org_publisher()
            if isinstance(obj.get("image"), str):
                obj["image"] = {"@type": "ImageObject", "url": obj["image"], "width": 1200, "height": 630}
            if label:
                obj["articleSection"] = label
            obj["isAccessibleForFree"] = True
        return jsonld(obj)

    return LD_BLOCK.sub(fix, h)


def patch_home(h: str) -> str:
    """Rebuild <main> and JSON-LD of the English home page; the hero headline, lead and about text are kept."""
    m = re.search(r"[ \t]*<main\b[^>]*>.*</main>", h, re.S)
    if not m:
        errors.append("no <main> in index.html")
        return h
    main = m.group(0)
    hero = re.search(r'<section class="hero[^"]*"[^>]*>(.*?)</section>', main, re.S)
    h1 = hero and re.search(r"<h1[^>]*>(.*?)</h1>", hero.group(1), re.S)
    lead = hero and re.search(r"<p[^>]*>(.*?)</p>", hero.group(1), re.S)
    about = re.search(r'<section id="about"[^>]*>\s*<div class="disclosure">(.*?)</div>', main, re.S)
    if not (h1 and lead and about):
        errors.append("cannot read hero headline / lead / about box in index.html")
        return h
    squash = lambda x: re.sub(r"\s+", " ", x).strip()
    h = h[:m.start()] + home_main(DEFAULT, _html.unescape(strip_tags(h1.group(1))), squash(lead.group(1)),
                                  squash(about.group(1))) + h[m.end():]
    h = re.sub(r'[ \t]*<script type="application/ld\+json">.*?</script>\n?', "", h, flags=re.S)
    return h.replace("</head>", home_ld(DEFAULT) + "\n</head>", 1)


def patch_en(path: Path, kind: str, slug: str = ""):
    h = path.read_text(encoding="utf-8")
    o = h
    h = fix_jsonld(h)
    h = replace_shell(h, DEFAULT, kind, slug)
    new = hreflang_block(kind, slug, DEFAULT)
    h, ok = replace_marked(h, "hreflang", new)
    if not ok:
        h = h.replace("</head>", new + "\n</head>", 1)
    if kind == "article":
        h = re.sub(r'<main\b[^>]*class="article-page"[^>]*>', lambda m: article_main_open(DEFAULT), h, count=1)
        h = patch_article_head(h, slug)
        # Idempotent: strip any prior marked/unmarked community boxes, then place exactly one.
        h = place_community(h, DEFAULT, home=False, kind=kind)
        h = place_newsletter(h, DEFAULT, kind, path_for(DEFAULT, kind, slug))
        h = place_partners(h, DEFAULT, kind, slug)
        h = place_related(h, DEFAULT, slug)
        h = upgrade_article_jsonld(h, slug)
    elif kind == "home":
        h = patch_home(h)
    else:  # about / disclosure
        crumbs = crumbs_html(DEFAULT, [("PlainBTC", "/")], STR[DEFAULT]["nav_" + kind])
        h, ok = replace_marked(h, "crumbs", crumbs)
        if not ok:
            h, n = re.subn(r'[ \t]*<a class="back"[^>]*>.*?</a>', lambda m: crumbs, h, count=1, flags=re.S)
            if not n:
                errors.append(f"cannot place breadcrumbs in {path.name}")
        h = place_newsletter(h, DEFAULT, kind, path_for(DEFAULT, kind, slug))
        if kind == "disclosure":
            h = place_partners(h, DEFAULT, kind, slug)
    h = re.sub(r"\n{3,}", "\n\n", h)   # repeated strip-and-place passes must not pile up blank lines
    if h != o:
        path.write_text(h, encoding="utf-8")


def patch_404():
    """404.html is hand-written; keep its head assets, header and footer in step with the rest of the site."""
    path = ROOT / "404.html"
    if not path.exists():
        return
    o = path.read_text(encoding="utf-8")
    h = replace_shell(o, DEFAULT, "404", "", robots="noindex,follow")
    art = "    <!-- i18n:heroart -->\n" + hero_art_html().replace("\n      ", "\n  ")[2:] + "\n    <!-- /i18n:heroart -->"
    h, _ = replace_marked(h, "heroart", art)
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
    if path.suffix.lower() in {".html", ".htm"}:
        content = add_data_partner_attrs(content)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")



def _llms_desc(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _llms_item(title: str, url: str, desc: str) -> str:
    d = _llms_desc(desc)
    return f"- [{title}]({url}): {d}" if d else f"- [{title}]({url})"


def build_llms_txt() -> str:
    """llmstxt.org-style index: key pages + every article, grouped by language."""
    lines = [
        "# PlainBTC",
        "",
        f"> {STR[DEFAULT]['tagline']}",
        "",
        "Plain-English Bitcoin and crypto news and beginner guides. Official site: https://plainbtc.com",
        "",
    ]
    for l in LANGS:
        code = l["code"]
        if code not in STR:
            continue
        lines.append(f"## {l['name']}")
        lines.append("")
        st = STR[code]
        lines.append(_llms_item("PlainBTC", abs_url(path_for(code, "home")), st.get("home_description") or st["tagline"]))
        for kind in ("about", "disclosure"):
            src = ROOT / "i18n" / "pages" / code / f"{kind}.txt"
            if src.exists():
                head, _blocks = parse_txt(src)
                title = head.get("h1") or head.get("page_title") or kind
                desc = head.get("description") or head.get("og_description") or ""
                lines.append(_llms_item(title, abs_url(path_for(code, kind)), desc))
        for slug in SLUGS:
            if slug in CONTENT and code in CONTENT[slug]:
                head = CONTENT[slug][code][0]
                desc = head.get("summary") or head.get("description") or ""
                lines.append(_llms_item(head["title"], abs_url(path_for(code, "article", slug)), desc))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    check_only = "--check" in sys.argv
    load_content()
    validate_strings()
    validate_partners()
    validate()
    if errors:
        print("\n".join("ERROR " + e for e in errors)); sys.exit(1)
    print(format_cta_distribution())
    if check_only:
        print("\n".join("warn  " + w for w in warnings)); print("check OK"); return
    sync_assets()
    n = 0
    for l in LANGS:
        code = l["code"]
        if code == DEFAULT or code not in STR:
            continue
        write(file_for(code, "home"), build_home(code)); n += 1
        for kind in ("about", "disclosure"):
            if has_page(code, kind):
                write(file_for(code, kind), place_newsletter(build_simple(code, kind), code, kind, path_for(code, kind))); n += 1
        for slug in SLUGS:
            if has_page(code, "article", slug):
                write(file_for(code, "article", slug), place_newsletter(build_article(code, slug), code, "article", path_for(code, "article", slug))); n += 1
        write(ROOT / code / "feed.xml", build_feed(code))
    # English pages: patch in place
    patch_en(ROOT / "index.html", "home")
    patch_en(ROOT / "about.html", "about")
    patch_en(ROOT / "disclosure.html", "disclosure")
    for slug in SLUGS:
        patch_en(ROOT / "articles" / f"{slug}.html", "article", slug)
    patch_404()
    write(ROOT / "feed.xml", build_feed(DEFAULT))
    write(ROOT / "sitemap.xml", build_sitemap())
    write(ROOT / "llms.txt", build_llms_txt())
    print(f"built {n} non-English pages; {len(SLUGS)} articles; wrote llms.txt")
    if errors:
        print("\n".join("ERROR " + e for e in errors)); sys.exit(1)
    print("\n".join("warn  " + w for w in warnings))


if __name__ == "__main__":
    main()
