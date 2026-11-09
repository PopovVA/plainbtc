# PlainBTC

Plain-English Bitcoin & crypto news for beginners.

**Live site:** [https://plainbtc.com](https://plainbtc.com)

Static HTML site (no build step). Deployable to Cloudflare Pages or any static host.

Includes market recaps, a Coinbase beginner guide, regulation notes, sitemap, RSS (`feed.xml`), and FTC affiliate disclosure pages.

Referral CTAs use `rel="sponsored"`. Nothing on the site is financial advice.


## Open Graph images

Article and page link previews (X / Facebook / Slack) use 1200×630 PNGs in `assets/og/`.

Generate or refresh an image:

```bash
python3 tools/make_og.py <slug> "<Headline title>" "<LABEL>"
# examples:
python3 tools/make_og.py my-new-article "Why bitcoin moved today" "MARKET NEWS"
python3 tools/make_og.py --all   # rebuild every known article + default.png
```

Then point the article's `og:image` / `twitter:image` meta tags (and NewsArticle JSON-LD `image`) at:

`https://plainbtc.com/assets/og/<slug>.png`

Labels that look good: `MARKET NEWS`, `REGULATION`, `GUIDE`, `BUSINESS`, `PLAINBTC`.
Requires Python 3 + Pillow (`pip install Pillow`) and DejaVu fonts.




## Mid-article images

Every news/guide article should show the hero/OG image at the top **and two more images in the middle of the body** (after ~paragraph 2–3 and again around the mid-CTA). Prefer:

1. A **chart** from real public data (CoinGecko price series, or bar charts of figures cited in the article’s sources).
2. A **fact card** highlighting one key number/quote from those sources (Pillow, same navy/orange brand as OG images).

Generate both with:

```bash
# needs: python3 -m venv .venv && .venv/bin/pip install matplotlib Pillow
.venv/bin/python tools/make_article_images.py --all
.venv/bin/python tools/make_article_images.py <slug>
```

Outputs land in `assets/img/<slug>/` (webp preferred, &lt;200 KB) and `i18n/content/<slug>/figures.json` (per-language `alt` + `caption`).

In every language body (`i18n/content/<slug>/<lang>.txt`) insert markers in the **same places**:

```
!figure:chart
!figure:fact
```

`tools/build_i18n.py` turns those into `<figure class="article-figure">…</figure>` blocks. English HTML under `articles/` is still hand-edited: paste the same two figures (see an existing article for the markup) and keep the hero `<img class="og-hero">`.

Never invent chart numbers. Never hotlink news-outlet photos — only official press-kit assets with credit, or graphics you generate.

## IndexNow (Bing / Yandex / others)

After publishing or updating pages, ping search engines via IndexNow:

```bash
python3 tools/indexnow.py                  # all URLs from sitemap.xml
python3 tools/indexnow.py https://plainbtc.com/articles/my-slug
python3 tools/indexnow.py --dry-run
```

The key file at site root (`<key>.txt`) must be publicly reachable at
`https://plainbtc.com/<key>.txt`. Key value is also in `tools/indexnow.key`.


## Multilingual site (10 languages)

Languages (see `i18n/langs.json`): `en` (default, no URL prefix — existing URLs never change), `es`, `pt` (Brazilian, hreflang `pt-BR`), `fr`, `de`, `ru`, `tr`, `id`, `ja`, `ko`.

URL scheme: `/` and `/articles/<slug>` stay English. Every other language lives under its prefix:
`/<lang>/` (home), `/<lang>/articles/<slug>`, `/<lang>/about`, `/<lang>/disclosure`, `/<lang>/feed.xml`.
Every page carries `hreflang` alternates for all 10 languages + `x-default` (= English), a self-referencing canonical, localized `<html lang>`, title/description/OG tags/`og:locale`, JSON-LD `inLanguage`, and a language switcher (header menu + footer list). OG images are reused from the English article. `sitemap.xml` is a single sitemap with `xhtml:link` alternates.

### What is generated vs hand-written

* English articles/pages are still hand-written HTML (`articles/<slug>.html`, `index.html`, ...). `tools/build_i18n.py` only *patches* them between `<!-- i18n:... -->` markers (hreflang block, language menu, footer languages) and fixes JSON-LD quoting. Safe to re-run.
* Everything under `es/ pt/ fr/ de/ ru/ tr/ id/ ja/ ko/` and `sitemap.xml` is **generated — do not edit by hand**. Edit the sources under `i18n/` and rebuild.

### Workflow for every new English article

```bash
# 1. After the English article HTML is written (with title, description, OG, JSON-LD, sources, related):
python3 tools/i18n_extract.py <slug>
#    -> i18n/content/<slug>/{meta.json, links.json, en.txt}
#    (use --all to re-extract everything; then re-apply manual edits to en.txt, e.g. the {{#ref}} sentence in the how-to)

# 2. Write 9 translations: i18n/content/<slug>/{es,pt,fr,de,ru,tr,id,ja,ko}.txt
#    Same block sequence as en.txt, natural native wording, facts/numbers/sources unchanged.

# 3. Validate and build
python3 tools/build_i18n.py --check     # block order, link keys, lists, numbers, inline tags, {{#ref}} markers
python3 tools/build_i18n.py             # writes <lang>/..., feeds, sitemap.xml; patches English pages

# 4. Commit, push, then ping search engines
python3 tools/indexnow.py
```

An article without a translation simply has no alternates and is skipped on non-English index pages (it is still in the sitemap as English).
Also remember: new articles should be added to `related` in `meta.json` of other articles only if you want cross-links; the English "related" list is extracted from the HTML.

### Translation file format (`i18n/content/<slug>/<lang>.txt`)

```
title: ...            # <h1>
page_title: ...       # <title> prefix (site name added by the builder)
description: ...      # meta description
og_description: ...
label: ...            # category label on cards
summary: ...          # card / home-page blurb
===
Paragraph blocks are separated by blank lines. Allowed inline HTML: <strong> <em> <code> <br>.
Links: [text](L1)  -> URL from links.json key L1;   [text](REF) -> Coinbase referral link (handled per language mode)
{{#ref}} through our referral link{{/ref}}   -> only shown in languages with referral mode full/hedged
## Heading
!takeaways
- bullet
- bullet
!mid_cta            # mid-article Coinbase banner (rendered only in full/hedged modes)
!soft: Text with [link](/articles/other-slug).   # soft internal-link CTA
!end_cta            # end-of-article Coinbase CTA (text depends on referral mode)
!disclosure         # standard disclosure box for this article's disclosure_variant
```
The block sequence (headings, paragraphs, lists, `!` blocks), link keys and numbers must match `en.txt`; `--check` reports mismatches (a few benign warnings, e.g. `ja`/`ko` number grouping, are expected).

### UI strings, static pages

* `i18n/strings/<lang>.json` — navigation, footer, labels, banner/CTA/disclosure text, home hero, month names.
* `i18n/pages/<lang>/{about,disclosure}.txt` — about and disclosure pages (same format).

### Coinbase referral per language (`referral` in `i18n/langs.json`)

* `full` (en): inline referral link, mid-article banner, end CTA.
* `hedged` (es, pt, fr, de): same placements, but the CTA/banner is worded "if Coinbase is available in your country"; the disclosure explains eligibility varies.
* `soft` (ru, id, ja, ko): no banner; a single hedged end CTA; inline `[Coinbase](REF)` mentions are plain text.
* `none` (tr): no referral links at all; disclosure page explains this.

Reasoning: Coinbase's own international-referral page lists Poland and Portugal as the only eligible non-US referral countries; Coinbase does not serve Russia. Change a language's mode in `langs.json` and rebuild to adjust the policy. Never invent bonus amounts in any language.
