#!/usr/bin/env python3
"""Generate branded Open Graph / Twitter preview images for PlainBTC.

Usage:
  python3 tools/make_og.py <slug> "<title>" "<LABEL>"
  python3 tools/make_og.py --all

Outputs 1200x630 PNG to assets/og/<slug>.png (or default.png for slug=default).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "og"

W, H = 1200, 630
BG_TOP = (11, 22, 48)       # #0b1630
BG_BOTTOM = (7, 14, 32)
ORANGE = (247, 147, 26)     # Bitcoin orange
WHITE = (255, 255, 255)
GRAY = (148, 163, 184)
GRID = (255, 255, 255, 16)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

ARTICLES = [
    (
        "trump-nominates-sec-cftc-commissioners-peirce-nov-2026",
        "Trump names four SEC and CFTC nominees, including a Peirce successor",
        "REGULATION",
    ),
    (
        "bitcoin-below-70000-200-week-average-nov-2026",
        "Bitcoin falls below $70,000 as traders bet on a Fed rate hike",
        "MARKET NEWS",
    ),
    (
        "msci-drops-strategy-bitcoin-falls-nvidia-nov-2026",
        "MSCI will drop Strategy from its indexes as bitcoin slides",
        "MARKETS",
    ),
    (
        "sec-backs-cftc-stock-perps-crypto-etf-options-nov-2026",
        "SEC backs the CFTC on stock perps and clears options on more crypto ETFs",
        "REGULATION",
    ),
    (
        "stablecoin-supply-shrinks-usdt-tether-nov-2026",
        "Stablecoin supply shrinks at the fastest pace since 2022",
        "MARKETS",
    ),
    (
        "across-protocol-domain-hijack-phishing-nov-2026",
        "Hackers hijack crypto bridge Across's website; about $350,000 drained",
        "SECURITY",
    ),
    (
        "okxice-tokenized-stocks-launch-nov-23-2026",
        "OKX and NYSE owner ICE set Nov. 23 launch for tokenized stock trading",
        "BUSINESS",
    ),
    (
        "bitcoin-below-73000-lowest-since-august-nov-2026",
        "Bitcoin drops below $73,000 for the first time since August",
        "MARKET NEWS",
    ),
    (
        "binance-warns-iphone-ios-flaw-wallet-keys-nov-2026",
        "Binance warns an iOS flaw could expose crypto wallet seed phrases",
        "SECURITY",
    ),
    (
        "binance-blocks-mexc-fincen-order-nov-2026",
        "Binance blocks MEXC transfers after a U.S. Treasury order",
        "REGULATION",
    ),
    (
        "banks-270-million-stablecoin-project-faro-nov-2026",
        "Banks reportedly commit $270 million to a joint dollar stablecoin",
        "BUSINESS",
    ),
    (
        "coinbase-occ-national-trust-charter-nov-2026",
        "Coinbase wins a full national trust charter from the OCC",
        "REGULATION",
    ),
    (
        "bitcoin-loses-50-week-moving-average-nov-2026",
        "Bitcoin loses its 50-week moving average as long liquidations top $1 billion",
        "MARKET NEWS",
    ),
    (
        "bitcoin-volatility-liquidations-nov-2026",
        "Bitcoin's weekend whipsaw: $1B liquidated as Nvidia headlines hit risk assets",
        "MARKET NEWS",
    ),
    (
        "fincen-fed-withdraw-250-travel-rule-nov-2026",
        "FinCEN and the Fed scrap the $250 Travel Rule plan — $3,000 threshold stays",
        "REGULATION",
    ),
    (
        "how-to-buy-first-bitcoin-coinbase",
        "How to buy your first Bitcoin on Coinbase (U.S. beginner guide)",
        "GUIDE",
    ),
    (
        "bitcoin-hot-cpi-etf-outflows-nov-2026",
        "Bitcoin slips after a hotter-than-expected October CPI",
        "MARKET NEWS",
    ),
    (
        "binance-hack-north-korea-memecoin-laundering-nov-2026",
        "North Korea is minting meme coins to launder the Binance hack",
        "SECURITY",
    ),
    (
        "pnc-coinbase-usdc-payments-pilot-nov-2026",
        "PNC Bank pilots USDC payments with Coinbase for corporate clients",
        "BUSINESS",
    ),
    (
        "us-midterms-crypto-regulation-etf-outflows",
        "After the midterms: ETF outflows and a tougher crypto rulebook ahead?",
        "REGULATION",
    ),
    (
        "is-coinbase-safe-for-beginners",
        "Is Coinbase safe for beginners? What's protected, what isn't",
        "GUIDE",
    ),
    (
        "how-much-bitcoin-should-a-beginner-buy-dca",
        "How much Bitcoin should a beginner buy? Dollar-cost averaging explained",
        "GUIDE",
    ),
    (
        "what-is-a-crypto-wallet-custodial-vs-self-custody",
        "What is a crypto wallet? Custodial vs. self-custody explained",
        "GUIDE",
    ),
]


# Topic-specific previews: slugs listed here get official logos / seals of the
# organizations in the story (white tiles on the right) instead of the generic bitcoin mark.
# Sources are Wikimedia Commons files (U.S. government seals are public domain; logos are
# used for identification only). Each entry: (image URL, tile background RGB).
WIKI = "https://upload.wikimedia.org/wikipedia/commons/"
OG_LOGOS: dict[str, list[tuple[str, tuple[int, int, int]]]] = {
    "trump-nominates-sec-cftc-commissioners-peirce-nov-2026": [
        (WIKI + "1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", (255, 255, 255)),
        (WIKI + "3/3e/Commodity_Futures_Trading_Commission_seal.svg", (255, 255, 255)),
    ],
    "bitcoin-below-70000-200-week-average-nov-2026": [
        (WIKI + "7/73/Seal_of_the_United_States_Federal_Reserve_Board.svg", (255, 255, 255)),
        (WIKI + "4/46/Bitcoin.svg", (255, 255, 255)),
    ],
}
LOGO_CACHE = Path("/tmp/og-logo-src")


def fetch_logo(url: str) -> Image.Image:
    """Download (and cache) a logo; SVGs are rasterized with cairosvg."""
    import hashlib
    import urllib.request

    LOGO_CACHE.mkdir(parents=True, exist_ok=True)
    dest = LOGO_CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".png")
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "PlainBTCOgBot/1.0 (https://plainbtc.com)"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        if url.lower().endswith(".svg") or b"<svg" in data[:400].lower():
            import cairosvg  # only needed for SVG logos (.venv has it)

            cairosvg.svg2png(bytestring=data, write_to=str(dest), output_width=900)
        else:
            dest.write_bytes(data)
    return Image.open(dest).convert("RGBA")


def draw_logo_tiles(base: Image.Image, logos) -> Image.Image:
    """Stack 1-3 rounded logo tiles in the right-hand column."""
    img = base.convert("RGBA")
    n = len(logos)
    tile_w, gap = 330, 24
    tile_h = min(220, (470 - gap * (n - 1)) // n) if n > 1 else 300
    total = n * tile_h + (n - 1) * gap
    x0, y0 = 1200 - 56 - tile_w, (630 - total) // 2 - 10
    for i, (url, bg) in enumerate(logos):
        y = y0 + i * (tile_h + gap)
        tile = Image.new("RGBA", (tile_w, tile_h), bg + (255,))
        mask = Image.new("L", (tile_w, tile_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile_w - 1, tile_h - 1], radius=22, fill=255)
        img.paste(tile, (x0, y), mask)
        logo = fetch_logo(url)
        pad = 22
        scale = min((tile_w - 2 * pad) / logo.width, (tile_h - 2 * pad) / logo.height)
        lw, lh = max(1, int(logo.width * scale)), max(1, int(logo.height * scale))
        logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
        img.alpha_composite(logo, (x0 + (tile_w - lw) // 2, y + (tile_h - lh) // 2))
    return img


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def wrap_text(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
    max_lines: int = 4,
) -> list[str]:
    words = text.replace("\u2014", "\u2014 ").replace("\u2013", "\u2013 ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines:
        used = " ".join(lines)
        remaining = text[len(used) :].strip()
        if remaining or draw.textlength(lines[-1], font=font) > max_width:
            ell = "\u2026"
            last = lines[-1]
            while last and draw.textlength(last + ell, font=font) > max_width:
                last = last[:-1].rstrip()
            lines[-1] = (last + ell) if last else ell
    return lines


def draw_bitcoin_mark(base: Image.Image, cx: int, cy: int, radius: int, alpha: int = 90) -> Image.Image:
    """Draw a soft Bitcoin coin mark (circle + B + vertical ticks) on the right."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for i, a in ((radius + 90, 18), (radius + 40, 28), (radius, 50)):
        d.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(247, 147, 26, a))

    ring = 12
    d.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=(247, 147, 26, alpha),
        width=ring,
    )

    b_font = load_font(FONT_BOLD, int(radius * 1.15))
    b = "B"
    bb = d.textbbox((0, 0), b, font=b_font)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    bx = cx - bw // 2 - 4
    by = cy - bh // 2 - int(radius * 0.08)
    d.text((bx, by), b, font=b_font, fill=(247, 147, 26, alpha))

    tick_w = max(6, radius // 18)
    gap = int(radius * 0.18)
    top_y = cy - int(radius * 0.62)
    bot_y = cy + int(radius * 0.62)
    for dx in (-gap, gap):
        d.rectangle(
            [cx + dx - tick_w // 2, top_y, cx + dx + tick_w // 2, bot_y],
            fill=(247, 147, 26, alpha),
        )

    return Image.alpha_composite(base.convert("RGBA"), layer)


def make_image(slug: str, title: str, label: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (W, H), BG_TOP)
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
        for x in range(W):
            px[x, y] = (r, g, b)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    step = 40
    for x in range(0, W, step):
        od.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, step):
        od.line([(0, y), (W, y)], fill=GRID, width=1)

    od.rectangle([0, 0, 8, H], fill=ORANGE + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    if slug in OG_LOGOS:
        img = draw_logo_tiles(img, OG_LOGOS[slug])
    else:
        img = draw_bitcoin_mark(img, cx=980, cy=300, radius=170, alpha=90)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    label_font = load_font(FONT_BOLD, 26)
    label_text = label.upper().strip()
    label_x, label_y = 56, 56
    draw.text((label_x, label_y), label_text, font=label_font, fill=ORANGE)
    lw = draw.textlength(label_text, font=label_font)
    draw.rectangle(
        [label_x, label_y + 36, label_x + max(48, int(lw * 0.45)), label_y + 40],
        fill=ORANGE,
    )

    title_font = load_font(FONT_BOLD, 52)
    max_title_width = 700 if slug not in OG_LOGOS else 680
    lines = wrap_text(title, title_font, max_title_width, draw, max_lines=4)
    if len(lines) >= 4:
        title_font = load_font(FONT_BOLD, 46)
        lines = wrap_text(title, title_font, max_title_width, draw, max_lines=4)

    line_gap = 10
    ascent = title_font.getmetrics()[0]
    title_y = 140
    for i, line in enumerate(lines):
        y = title_y + i * (ascent + line_gap)
        draw.text((56, y), line, font=title_font, fill=WHITE)

    footer_font = load_font(FONT_REG, 24)
    brand_font = load_font(FONT_BOLD, 24)
    draw.text((56, H - 64), "plainbtc.com", font=footer_font, fill=GRAY)
    draw.text((W - 200, H - 64), "Plain", font=brand_font, fill=WHITE)
    plain_w = draw.textlength("Plain", font=brand_font)
    draw.text((W - 200 + plain_w, H - 64), "BTC", font=brand_font, fill=ORANGE)

    out = OUT_DIR / f"{slug}.png"
    img.save(out, format="PNG", optimize=True)
    size = out.stat().st_size
    if size > 280_000:
        jpg = OUT_DIR / f"{slug}.jpg"
        img.save(jpg, format="JPEG", quality=85, optimize=True)
        out.unlink(missing_ok=True)
        out = jpg
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PlainBTC OG images")
    parser.add_argument("slug", nargs="?", help="Output slug (filename without extension)")
    parser.add_argument("title", nargs="?", help="Headline text")
    parser.add_argument("label", nargs="?", default="NEWS", help="Orange label, e.g. MARKET NEWS")
    parser.add_argument("--all", action="store_true", help="Generate all known article images + default")
    args = parser.parse_args()

    if args.all:
        paths = []
        paths.append(
            make_image(
                "default",
                "Plain-English Bitcoin & crypto news for beginners",
                "PLAINBTC",
            )
        )
        for slug, title, label in ARTICLES:
            paths.append(make_image(slug, title, label))
        for p in paths:
            print(f"{p} ({p.stat().st_size} bytes)")
        return 0

    if not args.slug or not args.title:
        parser.print_help()
        return 2

    path = make_image(args.slug, args.title, args.label or "NEWS")
    print(f"{path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
