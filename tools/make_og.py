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
    max_title_width = 700
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
