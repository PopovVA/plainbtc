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


## IndexNow (Bing / Yandex / others)

After publishing or updating pages, ping search engines via IndexNow:

```bash
python3 tools/indexnow.py                  # all URLs from sitemap.xml
python3 tools/indexnow.py https://plainbtc.com/articles/my-slug
python3 tools/indexnow.py --dry-run
```

The key file at site root (`<key>.txt`) must be publicly reachable at
`https://plainbtc.com/<key>.txt`. Key value is also in `tools/indexnow.key`.
