#!/usr/bin/env python3
"""Generate distinct 640x360 homepage card thumbnails for PlainBTC.

Topical thumbs from freely-licensed imagery (Wikimedia / U.S. government
public-domain works) and charts from real public market data (Kraken OHLC).
Article titles are NOT baked into the image.

Usage:
  .venv/bin/python tools/make_card_thumbs.py --all
  .venv/bin/python tools/make_card_thumbs.py <slug> [...]

Writes assets/img/<slug>/{thumb.webp,thumb.jpg,thumb.credits.json}
Unknown slugs: first mid-article figure. build_i18n falls back to OG if missing.
"""
from __future__ import annotations

import argparse, io, json, re, ssl, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cairosvg
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "assets" / "img"
I18N = ROOT / "i18n" / "content"
CACHE = Path("/tmp/thumb-src"); CACHE.mkdir(parents=True, exist_ok=True)
W, H = 640, 360
UA = {"User-Agent": "PlainBTCThumbBot/1.0 (editorial thumbs; https://plainbtc.com)"}
CTX = ssl.create_default_context()
BG, NAVY, ORANGE = (15, 20, 28), (11, 22, 48), (247, 147, 26)
WHITE, MUTED, ACCENT = (255, 255, 255), (148, 163, 184), (59, 130, 246)
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def font(path, size):
    try: return ImageFont.truetype(path, size)
    except OSError: return ImageFont.load_default()

def fetch(url: str, dest: Path) -> Path:
    png_dest = dest.with_suffix(".png") if dest.suffix.lower() == ".svg" else dest
    if png_dest.exists() and png_dest.stat().st_size > 500:
        return png_dest
    if dest.exists() and dest.suffix.lower() != ".svg" and dest.stat().st_size > 500:
        return dest
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        data = r.read()
    if dest.suffix.lower() == ".svg" or url.lower().endswith(".svg") or b"<svg" in data[:300].lower():
        cairosvg.svg2png(bytestring=data, write_to=str(png_dest), output_width=900)
        return png_dest
    dest.write_bytes(data)
    return dest

def open_rgb(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (*BG, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg.convert("RGB")
    return im.convert("RGB")

def cover_fit(im: Image.Image, w=W, h=H, cy=0.45) -> Image.Image:
    return ImageOps.fit(im.convert("RGB"), (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, cy))

def save_thumb(im: Image.Image, slug: str, credits: dict) -> Path:
    out = IMG / slug; out.mkdir(parents=True, exist_ok=True)
    im = cover_fit(im)
    webp, jpg = out / "thumb.webp", out / "thumb.jpg"
    im.save(webp, "WEBP", quality=84, method=6)
    im.save(jpg, "JPEG", quality=88, optimize=True)
    payload = {**credits, "slug": slug, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "size": [W, H], "files": ["thumb.webp", "thumb.jpg"]}
    (out / "thumb.credits.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {webp.relative_to(ROOT)} ({webp.stat().st_size // 1024} KB)")
    return webp

def gradient_bg(w=W, h=H, top=NAVY, bottom=BG) -> Image.Image:
    im = Image.new("RGB", (w, h), top); px = im.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w): px[x, y] = c
    return im

def paste_contain(base: Image.Image, overlay: Image.Image, box, pad=8):
    x, y, bw, bh = box
    ov = overlay.convert("RGBA")
    ow, oh = ov.size
    scale = min((bw - 2 * pad) / ow, (bh - 2 * pad) / oh)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
    ov = ov.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = x + (bw - nw) // 2, y + (bh - nh) // 2
    base_rgba = base.convert("RGBA"); base_rgba.paste(ov, (ox, oy), ov)
    base.paste(base_rgba.convert("RGB"))

def label_chip(im: Image.Image, text: str, xy=(16, 16)):
    rgba = im.convert("RGBA")
    chip = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(chip); f = font(FONT_B, 14)
    bb = cd.textbbox((0, 0), text, font=f); tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x, y = xy
    cd.rounded_rectangle([x, y, x + tw + 18, y + th + 12], radius=10, fill=(15, 23, 42, 220))
    cd.text((x + 9, y + 5), text, font=f, fill=(255, 255, 255, 255))
    im.paste(Image.alpha_composite(rgba, chip).convert("RGB")); return im

def darken(im: Image.Image, alpha=120) -> Image.Image:
    return Image.alpha_composite(im.convert("RGBA"), Image.new("RGBA", im.size, (8, 14, 28, alpha))).convert("RGB")

def kraken_ohlc(interval_min=1440, pair="XBTUSD"):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval_min}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        data = json.load(r)
    if data.get("error"): raise RuntimeError(data["error"])
    result = data["result"]; key = next(k for k in result if k != "last")
    rows = result[key]
    xs = [datetime.fromtimestamp(r[0], tz=timezone.utc) for r in rows]
    closes = [float(r[4]) for r in rows]
    return xs, closes

def chart_to_image(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.12)
    plt.close(fig); buf.seek(0); return Image.open(buf).convert("RGB")

def style_ax(ax, title):
    ax.set_facecolor("#0f1419"); ax.tick_params(colors="#9aa8bc", labelsize=7)
    for spine in ax.spines.values(): spine.set_color("#2d3a4f")
    ax.grid(True, color="#2d3a4f", alpha=0.45, linewidth=0.6)
    ax.set_title(title, color="white", fontsize=11, pad=8, loc="left")

def thumb_occ():
    seal = fetch("https://upload.wikimedia.org/wikipedia/commons/a/a0/Seal_of_the_Office_of_the_Comptroller_of_the_Currency.svg", CACHE/"occ-seal.svg")
    treasury = fetch("https://upload.wikimedia.org/wikipedia/commons/0/0d/Treasury_Building_%281%29.jpg", CACHE/"treasury.jpg")
    coinbase = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    base = darken(cover_fit(open_rgb(treasury), cy=0.4), 90)
    panel = Image.new("RGBA", base.size, (0,0,0,0)); ImageDraw.Draw(panel).rectangle([0,0,310,H], fill=(10,16,28,205))
    base = Image.alpha_composite(base.convert("RGBA"), panel).convert("RGB")
    paste_contain(base, Image.open(seal).convert("RGBA"), (24,50,200,220), pad=4)
    paste_contain(base, Image.open(coinbase).convert("RGBA"), (230,110,100,100), pad=2)
    label_chip(base, "OCC · Coinbase trust")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_Office_of_the_Comptroller_of_the_Currency.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_Office_of_the_Comptroller_of_the_Currency.svg","credit":"OCC"},
        {"file":"Treasury_Building_(1).jpg","license":"CC BY-SA 3.0","url":"https://commons.wikimedia.org/wiki/File:Treasury_Building_(1).jpg","credit":"AutoErich / Wikimedia Commons"},
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
    ],"note":"Editorial composite; trademarks belong to their owners."}

def thumb_fincen():
    fincen = fetch("https://upload.wikimedia.org/wikipedia/commons/c/ce/US-FinancialCrimesEnforcementNetwork-Seal.svg", CACHE/"fincen-seal.svg")
    fed = fetch("https://upload.wikimedia.org/wikipedia/commons/7/73/Seal_of_the_United_States_Federal_Reserve_Board.svg", CACHE/"fed-seal.svg")
    eccles = fetch("https://upload.wikimedia.org/wikipedia/commons/8/89/Eccles_Building_%2826088200676%29.jpg", CACHE/"eccles.jpg")
    base = darken(cover_fit(open_rgb(eccles), cy=0.4), 100)
    panel = Image.new("RGBA", base.size, (0,0,0,0)); ImageDraw.Draw(panel).rounded_rectangle([36,40,W-36,H-40], radius=18, fill=(15,23,42,205))
    base = Image.alpha_composite(base.convert("RGBA"), panel).convert("RGB")
    paste_contain(base, Image.open(fincen).convert("RGBA"), (70,60,220,240), pad=10)
    paste_contain(base, Image.open(fed).convert("RGBA"), (350,60,220,240), pad=10)
    label_chip(base, "FinCEN · Federal Reserve")
    return base, {"kind":"composite","sources":[
        {"file":"US-FinancialCrimesEnforcementNetwork-Seal.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:US-FinancialCrimesEnforcementNetwork-Seal.svg","credit":"FinCEN"},
        {"file":"Seal_of_the_United_States_Federal_Reserve_Board.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Federal_Reserve_Board.svg","credit":"Federal Reserve Board"},
        {"file":"Eccles_Building_(26088200676).jpg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Eccles_Building_(26088200676).jpg","credit":"Federal Reserve / Wikimedia"},
    ]}

def thumb_btc_50w():
    xs, closes = kraken_ohlc(10080); xs, closes = xs[-80:], closes[-80:]
    window=50; ma=[float("nan")]*len(closes)
    for i in range(window-1, len(closes)): ma[i]=sum(closes[i+1-window:i+1])/window
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "BTC weekly close vs 50-week MA")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.8, label="Weekly close")
    ax.plot(xs, ma, color="#60a5fa", linewidth=1.8, linestyle="--", label="50-week MA")
    ax.legend(loc="upper left", facecolor="#1a2332", edgecolor="#2d3a4f", labelcolor="white", fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    return chart_to_image(fig), {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=10080","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Weekly BTC/USD from Kraken; 50-week SMA by PlainBTC"}
    ]}

def thumb_liquidations():
    xs, closes = kraken_ohlc(60); xs, closes = xs[-168:], closes[-168:]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "BTC hourly — weekend whipsaw")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.6)
    if len(xs)>=48: ax.axvspan(xs[-48], xs[-1], color="#f87171", alpha=0.16)
    i_min=int(np.argmin(closes)); ax.scatter([xs[i_min]],[closes[i_min]], color="#f87171", s=40, zorder=5)
    ax.annotate(f"${closes[i_min]:,.0f}", (xs[i_min], closes[i_min]), textcoords="offset points", xytext=(6,-12), color="#fca5a5", fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    im = chart_to_image(fig); d = ImageDraw.Draw(im)
    d.rounded_rectangle([im.width-210,16,im.width-12,76], radius=10, fill=(127,29,29))
    d.text((im.width-198,26), "$1B+", font=font(FONT_B,18), fill=WHITE)
    d.text((im.width-198,50), "liquidations (CoinGlass)", font=font(FONT_R,10), fill=(254,202,202))
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=60","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Hourly BTC/USD from Kraken; $1B+ liquidations from CoinGlass as cited in article"}
    ]}

def thumb_pnc_usdc():
    pnc = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1b/PNClogo.svg", CACHE/"pnc-logo.svg")
    usdc = fetch("https://upload.wikimedia.org/wikipedia/commons/d/d2/USD_Coin_logo_%282024%29.png", CACHE/"usdc-logo.png")
    coinbase = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    building = fetch("https://upload.wikimedia.org/wikipedia/commons/3/36/PNC_Firstside_Center%2C_Pittsburgh.jpg", CACHE/"pnc-building.jpg")
    base = darken(cover_fit(open_rgb(building), cy=0.35), 150)
    logos = [(Image.open(pnc).convert("RGBA"),"PNC"),(Image.open(usdc).convert("RGBA"),"USDC"),(Image.open(coinbase).convert("RGBA"),"Coinbase")]
    card_w, card_h, gap = 170, 200, 16; total = 3*card_w+2*gap; x0,y0=(W-total)//2, 68
    for i,(logo,name) in enumerate(logos):
        x=x0+i*(card_w+gap)
        card=Image.new("RGBA",(card_w,card_h),(26,35,50,235))
        ImageDraw.Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",(card_w,card_h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), (x,y0), mask)
        paste_contain(base, logo, (x,y0+8,card_w,145), pad=14)
        d=ImageDraw.Draw(base); f=font(FONT_B,13); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
        d.text((x+(card_w-tw)//2, y0+165), name, font=f, fill=WHITE)
    label_chip(base, "PNC · USDC · Coinbase")
    return base, {"kind":"composite","sources":[
        {"file":"PNClogo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:PNClogo.svg","credit":"PNC"},
        {"file":"USD_Coin_logo_(2024).png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:USD_Coin_logo_(2024).png","credit":"Circle/USDC"},
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
        {"file":"PNC_Firstside_Center,_Pittsburgh.jpg","license":"CC BY-SA 2.0","url":"https://commons.wikimedia.org/wiki/File:PNC_Firstside_Center,_Pittsburgh.jpg","credit":"Wikimedia Commons"},
    ],"note":"Editorial composite; trademarks belong to their owners."}

def thumb_midterms():
    capitol = fetch("https://upload.wikimedia.org/wikipedia/commons/b/b2/United_States_Capitol_-_west_front.jpg", CACHE/"capitol.jpg")
    base = cover_fit(open_rgb(capitol), cy=0.35)
    overlay = Image.new("RGBA", base.size, (0,0,0,0)); ImageDraw.Draw(overlay).rectangle([0,int(H*0.42),W,H], fill=(8,14,28,215))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    labels=["Jun","Jul","Aug","Sep","Oct","Nov"]; vals=[0.4,0.15,-0.1,0.2,-0.35,-1.0]
    fig, ax = plt.subplots(figsize=(3.5,1.45), dpi=120); fig.patch.set_facecolor("#0f1419"); ax.set_facecolor("#0f1419")
    ax.bar(labels, vals, color=["#34d399" if v>=0 else "#f87171" for v in vals], width=0.65)
    ax.axhline(0, color="#9aa8bc", linewidth=0.8); ax.set_ylim(-1.25,0.7)
    ax.tick_params(colors="white", labelsize=7)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_yticks([]); ax.set_title("Spot BTC ETF weekly flows (schematic)", color="white", fontsize=8, loc="left", pad=2)
    chart = ImageOps.fit(chart_to_image(fig), (340,145), method=Image.Resampling.LANCZOS)
    base.paste(chart, (W-356, H-160)); label_chip(base, "Midterms · ETF outflows")
    return base, {"kind":"composite","sources":[
        {"file":"United_States_Capitol_-_west_front.jpg","license":"Public domain (Architect of the Capitol)","url":"https://commons.wikimedia.org/wiki/File:United_States_Capitol_-_west_front.jpg","credit":"Architect of the Capitol"},
        {"file":"ETF flow schematic","license":"PlainBTC chart","url":"","credit":"Schematic bars for Nov 2026 large weekly outflow; see article sources"},
    ]}

def thumb_howto():
    coinbase = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e1/Bitcoin_logo_clean.svg", CACHE/"btc-logo.svg")
    base = gradient_bg(); d = ImageDraw.Draw(base)
    px,py,pw,ph = 210,28,220,304
    d.rounded_rectangle([px,py,px+pw,py+ph], radius=28, fill=(26,35,50), outline=(45,58,79), width=3)
    d.rounded_rectangle([px+70,py+10,px+pw-70,py+22], radius=6, fill=(15,20,28))
    sx,sy,sw,sh = px+14, py+36, pw-28, ph-50
    d.rounded_rectangle([sx,sy,sx+sw,sy+sh], radius=12, fill=(15,23,42))
    paste_contain(base, Image.open(coinbase).convert("RGBA"), (sx+16,sy+14,sw-32,44), pad=0)
    d = ImageDraw.Draw(base)
    d.text((sx+20,sy+66), "Buy Bitcoin", font=font(FONT_B,14), fill=WHITE)
    d.text((sx+20,sy+88), "BTC · Coinbase", font=font(FONT_R,10), fill=MUTED)
    paste_contain(base, Image.open(btc).convert("RGBA"), (sx+sw-66,sy+66,50,50), pad=0)
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([sx+14,sy+130,sx+sw-14,sy+168], radius=8, fill=(30,41,59))
    d.text((sx+26,sy+140), "$50.00", font=font(FONT_B,16), fill=WHITE)
    d.rounded_rectangle([sx+14,sy+188,sx+sw-14,sy+226], radius=10, fill=ACCENT)
    bb=d.textbbox((0,0),"Preview buy", font=font(FONT_B,12)); tw=bb[2]-bb[0]
    d.text((sx+(sw-tw)//2, sy+198), "Preview buy", font=font(FONT_B,12), fill=WHITE)
    for i,s in enumerate(["Create account","Verify ID","Add payment","Buy BTC"]):
        y=72+i*55; d.ellipse([46,y,70,y+24], fill=ORANGE)
        d.text((52,y+4), str(i+1), font=font(FONT_B,11), fill=(15,20,28))
        d.text((80,y+4), s, font=font(FONT_R,12), fill=WHITE)
    label_chip(base, "Beginner buy guide")
    return base, {"kind":"illustration","sources":[
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
        {"file":"Bitcoin_logo_clean.svg","license":"CC0","url":"https://commons.wikimedia.org/wiki/File:Bitcoin_logo_clean.svg","credit":"Bitcoin logo"},
        {"file":"UI illustration","license":"PlainBTC original","url":"","credit":"Stylized buy-flow mockup — not an official Coinbase screenshot"},
    ]}


def thumb_coinbase_safe():
    coinbase = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    # US Treasury / banking vibe optional — use lock illustration + Coinbase
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # large shield
    d.rounded_rectangle([40, 50, 280, 310], radius=24, fill=(26, 35, 50), outline=(45, 58, 79), width=2)
    # lock body
    d.rounded_rectangle([110, 150, 210, 250], radius=16, fill=ACCENT)
    d.arc([120, 95, 200, 175], start=0, end=180, fill=ORANGE, width=10)
    d.ellipse([145, 185, 175, 215], fill=WHITE)
    d.rectangle([156, 210, 164, 235], fill=WHITE)
    paste_contain(base, Image.open(coinbase).convert("RGBA"), (320, 70, 140, 140), pad=4)
    d = ImageDraw.Draw(base)
    d.text((320, 220), "Cold storage", font=font(FONT_B, 18), fill=WHITE)
    d.text((320, 248), "Coinbase holds >99% of", font=font(FONT_R, 12), fill=MUTED)
    d.text((320, 268), "customer assets offline", font=font(FONT_R, 12), fill=MUTED)
    d.text((320, 288), "(per Coinbase)", font=font(FONT_R, 11), fill=MUTED)
    label_chip(base, "Is Coinbase safe?")
    return base, {"kind":"illustration","sources":[
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
        {"file":"cold-storage illustration","license":"PlainBTC original","url":"","credit":">99% cold-storage figure from Coinbase blog as cited in article"},
    ]}


def thumb_dca():
    # Real weekly BTC chart + DCA annotation
    xs, closes = kraken_ohlc(10080); xs, closes = xs[-104:], closes[-104:]  # ~2y weekly
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "BTC weekly — why DCA smooths entries")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.7)
    # mark a few equal-spaced buy dots
    idxs = list(range(0, len(closes), max(1, len(closes)//8)))[:8]
    ax.scatter([xs[i] for i in idxs], [closes[i] for i in idxs], color="#60a5fa", s=28, zorder=5, label="Example weekly buys")
    ax.legend(loc="upper left", facecolor="#1a2332", edgecolor="#2d3a4f", labelcolor="white", fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    im = chart_to_image(fig)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([im.width-200, 14, im.width-12, 70], radius=10, fill=(30, 58, 138))
    d.text((im.width-188, 22), "DCA", font=font(FONT_B, 16), fill=WHITE)
    d.text((im.width-188, 44), "small regular buys", font=font(FONT_R, 10), fill=(191, 219, 254))
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=10080","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Weekly BTC/USD from Kraken; DCA markers illustrative"},
    ]}


def thumb_wallet():
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # two columns
    for i, (title, color, lines) in enumerate([
        ("Custodial", (59, 130, 246), ["Exchange holds keys", "Login recovery OK", "Counterparty risk"]),
        ("Self-custody", (247, 147, 26), ["You hold the keys", "Seed phrase = access", "No company bailout"]),
    ]):
        x0 = 30 + i * 310
        d.rounded_rectangle([x0, 55, x0+280, 310], radius=18, fill=(26, 35, 50), outline=color, width=3)
        d.rounded_rectangle([x0+16, 70, x0+264, 110], radius=10, fill=color)
        bb = d.textbbox((0,0), title, font=font(FONT_B, 16)); tw=bb[2]-bb[0]
        d.text((x0 + (280-tw)//2, 80), title, font=font(FONT_B, 16), fill=(15,20,28) if i==1 else WHITE)
        # key icon circle
        d.ellipse([x0+105, 130, x0+175, 200], outline=color, width=4)
        d.rectangle([x0+135, 195, x0+145, 240], fill=color)
        for j, line in enumerate(lines):
            d.text((x0+28, 250+j*18), "• "+line, font=font(FONT_R, 12), fill=WHITE)
    label_chip(base, "Crypto wallets")
    return base, {"kind":"illustration","sources":[
        {"file":"wallet comparison illustration","license":"PlainBTC original","url":"","credit":"Concepts from Coinbase Help / Bitcoin.org / FINRA as cited in article"},
    ]}


def thumb_binance_hack():
    binance = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")
    usdc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/4a/Circle_USDC_Logo.svg", CACHE/"circle-usdc-logo.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # schematic wallet trail: dots joined by lines across the bottom
    pts = [(40,300),(130,270),(220,310),(310,262),(400,300),(490,268),(600,296)]
    for a,b in zip(pts,pts[1:]):
        d.line([a,b], fill=(247,147,26), width=3)
    for x,y in pts:
        d.ellipse([x-9,y-9,x+9,y+9], fill=(26,35,50), outline=(247,147,26), width=3)
    logos=[(Image.open(binance).convert("RGBA"),"Binance"),(Image.open(usdc).convert("RGBA"),"USDC")]
    card_w, card_h, gap = 210, 180, 24; total = 2*card_w+gap; x0,y0=(W-total)//2, 56
    for i,(logo,name) in enumerate(logos):
        x=x0+i*(card_w+gap)
        card=Image.new("RGBA",(card_w,card_h),(26,35,50,235))
        ImageDraw.Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",(card_w,card_h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), (x,y0), mask)
        paste_contain(base, logo, (x,y0+8,card_w,125), pad=16)
        d=ImageDraw.Draw(base); f=font(FONT_B,14); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
        d.text((x+(card_w-tw)//2, y0+145), name, font=f, fill=WHITE)
    label_chip(base, "Binance hack · laundering trail")
    return base, {"kind":"composite","sources":[
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
        {"file":"Circle_USDC_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Circle_USDC_Logo.svg","credit":"Circle/USDC"},
        {"file":"wallet-trail illustration","license":"PlainBTC original","url":"","credit":"PlainBTC"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_hot_cpi():
    xs, closes = kraken_ohlc(60); xs, closes = xs[-48:], closes[-48:]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.8)
    cpi = datetime(2026, 11, 10, 13, 30, tzinfo=timezone.utc)
    ax.axvline(cpi, color="#60a5fa", linestyle="--", linewidth=1.4)
    ax.text(cpi, max(closes), " CPI 8:30 ET", color="#93c5fd", fontsize=8, va="top", ha="right")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.1f}k"))
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M"))
    im = chart_to_image(fig)
    label_chip(im, "BTC/USD hourly (Kraken, UTC) · CPI day")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=60","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Hourly BTC/USD closes from Kraken; CPI release time from BLS"}
    ]}


def _logo_cards(base, logos, card_w, card_h, gap, y0, logo_h, name_y, pad=14):
    total = len(logos)*card_w + (len(logos)-1)*gap; x0 = (W-total)//2
    for i,(logo,name) in enumerate(logos):
        x=x0+i*(card_w+gap)
        card=Image.new("RGBA",(card_w,card_h),(26,35,50,235))
        ImageDraw.Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",(card_w,card_h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), (x,y0), mask)
        paste_contain(base, logo, (x,y0+8,card_w,logo_h), pad=pad)
        d=ImageDraw.Draw(base); f=font(FONT_B,13); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
        d.text((x+(card_w-tw)//2, y0+name_y), name, font=f, fill=WHITE)
    return x0, total

def thumb_mexc():
    fincen = fetch("https://upload.wikimedia.org/wikipedia/commons/c/ce/US-FinancialCrimesEnforcementNetwork-Seal.svg", CACHE/"fincen-seal.svg")
    binance = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")
    treasury = fetch("https://upload.wikimedia.org/wikipedia/commons/0/0d/Treasury_Building_%281%29.jpg", CACHE/"treasury.jpg")
    base = darken(cover_fit(open_rgb(treasury), cy=0.4), 150)
    card_w, card_h, gap, y0 = 200, 190, 120, 60
    x0, total = _logo_cards(base, [(Image.open(fincen).convert("RGBA"),"FinCEN"),(Image.open(binance).convert("RGBA"),"Binance")], card_w, card_h, gap, y0, 140, 160)
    # blocked-transfer symbol between the cards
    d = ImageDraw.Draw(base); cx, cy = x0+card_w+gap//2, y0+card_h//2
    d.line([(cx-44,cy),(cx+44,cy)], fill=(148,163,184), width=4)
    d.ellipse([cx-24,cy-24,cx+24,cy+24], outline=(248,113,113), width=5)
    d.line([(cx-17,cy+17),(cx+17,cy-17)], fill=(248,113,113), width=5)
    f = font(FONT_B, 15); t = "Transfers with MEXC blocked"; bb = d.textbbox((0,0),t,font=f)
    d.text(((W-(bb[2]-bb[0]))//2, y0+card_h+26), t, font=f, fill=(254,202,202))
    label_chip(base, "FinCEN order · MEXC")
    return base, {"kind":"composite","sources":[
        {"file":"US-FinancialCrimesEnforcementNetwork-Seal.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:US-FinancialCrimesEnforcementNetwork-Seal.svg","credit":"FinCEN"},
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
        {"file":"Treasury_Building_(1).jpg","license":"CC BY-SA 3.0","url":"https://commons.wikimedia.org/wiki/File:Treasury_Building_(1).jpg","credit":"AutoErich / Wikimedia Commons"},
    ],"note":"Editorial composite; trademarks belong to their owners."}

def thumb_faro():
    gs = fetch("https://upload.wikimedia.org/wikipedia/commons/6/61/Goldman_Sachs.svg", CACHE/"goldman-sachs.svg")
    citi = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1b/Citi.svg", CACHE/"citi.svg")
    san = fetch("https://upload.wikimedia.org/wikipedia/commons/b/b8/Banco_Santander_Logotipo.svg", CACHE/"santander.svg")
    db = fetch("https://upload.wikimedia.org/wikipedia/commons/7/7b/Deutsche_Bank_logo_without_wordmark.svg", CACHE/"deutsche-bank.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # dollar-coin motif along the bottom
    for i,x in enumerate(range(60, W, 104)):
        y = 300 + (8 if i % 2 else 0)
        d.ellipse([x-22,y-22,x+22,y+22], fill=(26,35,50), outline=(52,211,153), width=3)
        fb = font(FONT_B, 20); bb = d.textbbox((0,0),"$",font=fb)
        d.text((x-(bb[2]-bb[0])//2, y-(bb[3]-bb[1])//2-4), "$", font=fb, fill=(52,211,153))
    logos=[(Image.open(gs).convert("RGBA"),"Goldman Sachs"),(Image.open(citi).convert("RGBA"),"Citi"),
           (Image.open(san).convert("RGBA"),"Santander"),(Image.open(db).convert("RGBA"),"Deutsche Bank")]
    # white tiles so dark logos stay visible
    card_w, card_h, gap, y0 = 132, 160, 14, 60
    total = 4*card_w+3*gap; x0=(W-total)//2
    for i,(logo,name) in enumerate(logos):
        x=x0+i*(card_w+gap)
        tile=Image.new("RGBA",(card_w,card_h),(255,255,255,255))
        mask=Image.new("L",(card_w,card_h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(tile.convert("RGB"), (x,y0), mask)
        lg = logo.copy(); bgw = Image.new("RGBA", lg.size, (255,255,255,255)); bgw.paste(lg,(0,0),lg)
        paste_contain(base, bgw, (x,y0+6,card_w,112), pad=14)
        dd=ImageDraw.Draw(base); f=font(FONT_B,12); bb=dd.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
        dd.text((x+(card_w-tw)//2, y0+128), name, font=f, fill=(15,23,42))
    label_chip(base, "Bank stablecoin venture")
    return base, {"kind":"composite","sources":[
        {"file":"Goldman_Sachs.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Goldman_Sachs.svg","credit":"Goldman Sachs"},
        {"file":"Citi.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Citi.svg","credit":"Citigroup"},
        {"file":"Banco_Santander_Logotipo.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Banco_Santander_Logotipo.svg","credit":"Banco Santander"},
        {"file":"Deutsche_Bank_logo_without_wordmark.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Deutsche_Bank_logo_without_wordmark.svg","credit":"Deutsche Bank"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_btc_below_73k():
    xs, closes = kraken_ohlc(1440); xs, closes = xs[-120:], closes[-120:]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.8)
    ax.axhline(73000, color="#f87171", linestyle="--", linewidth=1.3)
    ax.text(xs[2], 73000, " $73,000", color="#fca5a5", fontsize=8, va="bottom")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    im = chart_to_image(fig)
    label_chip(im, "BTC/USD daily closes (Kraken), last 120 days")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Daily BTC/USD closes from Kraken"}
    ]}

def thumb_ios_flaw():
    phone = fetch("https://upload.wikimedia.org/wikipedia/commons/4/42/Front_of_iPhone_15_Pro_Max.jpg", CACHE/"iphone15promax-front.jpg")
    binance = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")
    base = gradient_bg()
    ph = Image.open(phone).convert("RGB")
    pw, phh = ph.size
    ph = ph.crop((int(pw*0.04), int(phh*0.02), int(pw*0.96), int(phh*0.965)))   # trim white photo margins
    ph.thumbnail((10000, 290), Image.Resampling.LANCZOS)
    base.paste(ph, (80, 56))
    d = ImageDraw.Draw(base)
    # warning triangle between phone and logo
    cx, cy = 320, 196
    d.polygon([(cx, cy-46), (cx-52, cy+42), (cx+52, cy+42)], fill=(247,147,26))
    fb = font(FONT_B, 54); bb = d.textbbox((0,0),"!",font=fb)
    d.text((cx-(bb[2]-bb[0])//2-2, cy-34), "!", font=fb, fill=(15,20,28))
    cw, ch, x, y = 210, 180, 400, 106
    card = Image.new("RGB", (cw, ch), (26,35,50))
    mask = Image.new("L", (cw, ch), 0); ImageDraw.Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=14, fill=255)
    base.paste(card, (x, y), mask)
    paste_contain(base, Image.open(binance).convert("RGBA"), (x, y+8, cw, 130), pad=16)
    d = ImageDraw.Draw(base); f = font(FONT_B, 13); t = "Security warning"; bb = d.textbbox((0,0),t,font=f)
    d.text((x+(cw-(bb[2]-bb[0]))//2, y+148), t, font=f, fill=WHITE)
    label_chip(base, "iOS flaw · wallet security")
    return base, {"kind":"composite","sources":[
        {"file":"Front_of_iPhone_15_Pro_Max.jpg","license":"CC BY 4.0","url":"https://commons.wikimedia.org/wiki/File:Front_of_iPhone_15_Pro_Max.jpg","credit":"Ayamano2021 / Wikimedia Commons"},
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_across():
    """Generated graphic: a browser window on across.to swapped for a fake approval prompt (no third-party imagery)."""
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # browser window
    bx, by, bw, bh = 70, 58, 500, 250
    d.rounded_rectangle([bx, by, bx+bw, by+bh], radius=16, fill=(26,35,50), outline=(45,58,79), width=2)
    d.rounded_rectangle([bx, by, bx+bw, by+44], radius=16, fill=(36,48,68))
    d.rectangle([bx, by+28, bx+bw, by+44], fill=(36,48,68))
    for i,c in enumerate([(248,113,113),(251,191,36),(52,211,153)]):
        d.ellipse([bx+16+i*20, by+16, bx+28+i*20, by+28], fill=c)
    # address bar with warning
    ax0 = bx+90; d.rounded_rectangle([ax0, by+10, bx+bw-16, by+36], radius=12, fill=(15,20,28))
    d.polygon([(ax0+16, by+15), (ax0+6, by+32), (ax0+26, by+32)], fill=(248,113,113))
    d.text((ax0+13, by+16), "!", font=font(FONT_B, 13), fill=(15,20,28))
    d.text((ax0+36, by+14), "across.to", font=font(FONT_B, 15), fill=WHITE)
    # fake approval prompt
    px, py = bx+110, by+76
    d.rounded_rectangle([px, py, px+280, py+150], radius=12, fill=(15,23,42), outline=(248,113,113), width=3)
    d.text((px+20, py+16), "Signature request", font=font(FONT_B, 17), fill=WHITE)
    d.text((px+20, py+46), "Approve unlimited token access?", font=font(FONT_R, 13), fill=MUTED)
    d.rounded_rectangle([px+20, py+86, px+130, py+126], radius=10, fill=(45,58,79))
    d.text((px+44, py+97), "Reject", font=font(FONT_B, 14), fill=WHITE)
    d.rounded_rectangle([px+150, py+86, px+260, py+126], radius=10, fill=(248,113,113))
    d.text((px+168, py+97), "Approve", font=font(FONT_B, 14), fill=(15,20,28))
    label_chip(base, "Domain hijack · phishing")
    return base, {"kind":"generated","sources":[
        {"file":"(generated)","license":"PlainBTC original graphic","url":"","credit":"PlainBTC illustration; no third-party imagery"}
    ]}

def thumb_okxice():
    okx = fetch("https://upload.wikimedia.org/wikipedia/commons/2/2c/OKX_logo.svg", CACHE/"okx-logo.svg")
    ice = fetch("https://upload.wikimedia.org/wikipedia/commons/a/a7/Intercontinental_Exchange_logo.svg", CACHE/"ice-logo.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # faint candlestick motif along the bottom
    import random
    rnd = random.Random(23); y = 300
    for x in range(30, W, 26):
        o = y; y = max(270, min(330, y + rnd.randint(-12, 12))); c = (52,211,153) if y < o else (248,113,113)
        d.line([(x+6, min(o,y)-8), (x+6, max(o,y)+8)], fill=c, width=1)
        d.rectangle([x, min(o,y), x+12, max(o,y)+2], fill=c)
    card_w, card_h, gap, y0 = 220, 170, 60, 56
    total = 2*card_w+gap; x0 = (W-total)//2
    for i,(logo,name) in enumerate([(Image.open(okx).convert("RGBA"),"OKX"),(Image.open(ice).convert("RGBA"),"Intercontinental Exchange")]):
        x = x0+i*(card_w+gap)
        tile = Image.new("RGB",(card_w,card_h),(255,255,255))
        mask = Image.new("L",(card_w,card_h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(tile,(x,y0),mask)
        lg = logo.copy(); bgw = Image.new("RGBA", lg.size, (255,255,255,255)); bgw.paste(lg,(0,0),lg)
        paste_contain(base, bgw, (x, y0+6, card_w, 122), pad=18)
        dd = ImageDraw.Draw(base); f = font(FONT_B, 12); bb = dd.textbbox((0,0),name,font=f)
        dd.text((x+(card_w-(bb[2]-bb[0]))//2, y0+140), name, font=f, fill=(15,23,42))
    d = ImageDraw.Draw(base); fb = font(FONT_B, 34); bb = d.textbbox((0,0),"+",font=fb)
    d.text((x0+card_w+(gap-(bb[2]-bb[0]))//2, y0+card_h//2-24), "+", font=fb, fill=ORANGE)
    label_chip(base, "Tokenized stocks · OKXICE")
    return base, {"kind":"composite","sources":[
        {"file":"OKX_logo.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:OKX_logo.svg","credit":"OKX"},
        {"file":"Intercontinental_Exchange_logo.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Intercontinental_Exchange_logo.svg","credit":"Intercontinental Exchange"},
    ],"note":"Editorial composite; trademarks belong to their owners. Candlestick motif is decorative, not market data."}


def thumb_stablecoin_supply():
    """Total USD-pegged stablecoin supply since Jan 1, 2026 (DefiLlama public API)."""
    url = "https://stablecoins.llama.fi/stablecoincharts/all"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = json.load(r)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    rows = [r for r in rows if int(r["date"]) >= start]
    xs = [datetime.fromtimestamp(int(r["date"]), tz=timezone.utc) for r in rows]
    ys = [r["totalCirculatingUSD"]["peggedUSD"] / 1e9 for r in rows]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    ax.plot(xs, ys, color="#34d399", linewidth=1.9)
    ax.fill_between(xs, ys, min(ys) * 0.99, color="#34d399", alpha=0.12)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v:.0f}B"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    im = chart_to_image(fig)
    label_chip(im, "Total stablecoin supply in 2026 (DefiLlama)")
    return im, {"kind":"chart","sources":[
        {"file":"DefiLlama stablecoincharts/all","license":"DefiLlama public API","url":"https://defillama.com/stablecoins","credit":"Total USD-pegged stablecoin supply from DefiLlama"}
    ]}

def thumb_sec_perps():
    sec = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", CACHE/"sec-seal.svg")
    cftc = fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Commodity_Futures_Trading_Commission_seal.svg", CACHE/"cftc-seal.svg")
    hq = fetch("https://upload.wikimedia.org/wikipedia/commons/1/19/U.S._Securities_and_Exchange_Commission_headquarters.JPG", CACHE/"sec-hq.jpg")
    base = darken(cover_fit(open_rgb(hq), cy=0.45), 110)
    panel = Image.new("RGBA", base.size, (0,0,0,0)); ImageDraw.Draw(panel).rounded_rectangle([36,40,W-36,H-40], radius=18, fill=(15,23,42,190))
    base = Image.alpha_composite(base.convert("RGBA"), panel).convert("RGB")
    paste_contain(base, Image.open(sec).convert("RGBA"), (80,60,220,240), pad=10)
    paste_contain(base, Image.open(cftc).convert("RGBA"), (340,60,220,240), pad=10)
    label_chip(base, "SEC · CFTC")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","credit":"SEC"},
        {"file":"Commodity_Futures_Trading_Commission_seal.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Commodity_Futures_Trading_Commission_seal.svg","credit":"CFTC"},
        {"file":"U.S._Securities_and_Exchange_Commission_headquarters.JPG","license":"CC BY-SA 3.0","url":"https://commons.wikimedia.org/wiki/File:U.S._Securities_and_Exchange_Commission_headquarters.JPG","credit":"AgnosticPreachersKid / Wikimedia Commons"},
    ],"note":"Editorial composite."}


def thumb_msci_strategy():
    logo = fetch("https://upload.wikimedia.org/wikipedia/commons/2/2f/MSCI_logo.svg", CACHE/"msci-logo.svg")
    base = Image.new("RGB", (W, H), (15, 20, 25))
    d = ImageDraw.Draw(base)
    for i in range(0, W, 32):
        d.line([(i, 0), (i, H)], fill=(24, 32, 42))
    for j in range(0, H, 32):
        d.line([(0, j), (W, j)], fill=(24, 32, 42))
    card = Image.new("RGBA", (360, 180), (255, 255, 255, 255))
    mask = Image.new("L", card.size, 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, 359, 179], radius=16, fill=255)
    x0, y0 = (W - 360) // 2, (H - 180) // 2 - 10
    base.paste(card, (x0, y0), mask)
    paste_contain(base, Image.open(logo).convert("RGBA"), (x0, y0, 360, 180), pad=34)
    label_chip(base, "Index review · Strategy (MSTR)")
    return base, {"kind":"composite","sources":[
        {"file":"MSCI_logo.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:MSCI_logo.svg","credit":"MSCI"},
    ],"note":"Editorial use of the MSCI logo for identification; trademark belongs to its owner."}


def thumb_doj_binance_seizure():
    doj = fetch("https://upload.wikimedia.org/wikipedia/commons/5/54/Seal_of_the_United_States_Department_of_Justice.svg", CACHE/"doj-seal.svg")
    fbi = fetch("https://upload.wikimedia.org/wikipedia/commons/d/da/Seal_of_the_Federal_Bureau_of_Investigation.svg", CACHE/"fbi-seal.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    # schematic "frozen" trail: wallet dots, the last ones locked behind a bar
    pts = [(60,318),(150,296),(240,322),(330,298),(420,320),(510,300),(590,318)]
    for a,b in zip(pts,pts[1:]):
        d.line([a,b], fill=(247,147,26), width=3)
    for i,(x,y) in enumerate(pts):
        col = (52,211,153) if i >= 4 else (247,147,26)
        d.ellipse([x-9,y-9,x+9,y+9], fill=(26,35,50), outline=col, width=3)
    d.line([(375,280),(375,340)], fill=(52,211,153), width=4)
    paste_contain(base, Image.open(doj).convert("RGBA"), (120,48,190,210), pad=6)
    paste_contain(base, Image.open(fbi).convert("RGBA"), (330,48,190,210), pad=6)
    label_chip(base, "DOJ · FBI · Binance hack funds")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Department_of_Justice.svg","license":"Public domain (U.S. government insignia)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Department_of_Justice.svg","credit":"U.S. Department of Justice"},
        {"file":"Seal_of_the_Federal_Bureau_of_Investigation.svg","license":"Public domain (U.S. government insignia)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_Federal_Bureau_of_Investigation.svg","credit":"FBI"},
        {"file":"wallet-trail illustration","license":"PlainBTC original","url":"","credit":"PlainBTC"},
    ],"note":"Editorial composite for identification; no endorsement by DOJ or FBI implied."}


def thumb_btc_etf_outflows_nov():
    """U.S. spot bitcoin ETF daily net flows, Nov 2-12, 2026 (US$m), as published by Farside Investors."""
    days = ["Nov 2", "Nov 3", "Nov 4", "Nov 5", "Nov 6", "Nov 9", "Nov 10", "Nov 11", "Nov 12"]
    flows = [-398.6, -115.6, 74.6, -430.2, -411.9, -201.0, -95.0, -299.8, -284.1]   # farside.co.uk/btc, read Nov 13, 2026
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    cols = ["#34d399" if v > 0 else "#f87171" for v in flows]
    ax.bar(days, flows, color=cols, width=0.6)
    ax.axhline(0, color="#9aa8bc", linewidth=0.8)
    ax.set_ylim(min(flows) * 1.08, 230)   # headroom so the label chip does not cover the Nov 4 inflow bar
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v:,.0f}M"))
    ax.tick_params(axis="x", labelsize=7)
    im = chart_to_image(fig)
    label_chip(im, "Spot bitcoin ETF net flows, US$m (Farside)")
    return im, {"kind":"chart","sources":[
        {"file":"Farside Investors Bitcoin ETF Flow table","license":"Public data, cited","url":"https://farside.co.uk/btc/","credit":"Daily U.S. spot bitcoin ETF net flows, Nov 2-12, 2026, from Farside Investors"}
    ]}


def thumb_sec_cftc_nominees():
    sec = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", CACHE/"sec-seal.svg")
    cftc = fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Commodity_Futures_Trading_Commission_seal.svg", CACHE/"cftc-seal.svg")
    capitol = fetch("https://upload.wikimedia.org/wikipedia/commons/b/b2/United_States_Capitol_-_west_front.jpg", CACHE/"capitol.jpg")
    base = darken(cover_fit(open_rgb(capitol), cy=0.5), 135)
    for i, (logo, x) in enumerate([(sec, 130), (cftc, 350)]):
        disc = Image.new("RGBA", (170, 170), (0, 0, 0, 0))
        ImageDraw.Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), (x, 70), disc)
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 70, 170, 170), pad=8)
    d = ImageDraw.Draw(base); f = font(FONT_B, 16); t = "4 nominees await Senate confirmation"
    bb = d.textbbox((0,0), t, font=f); d.text(((W-(bb[2]-bb[0]))//2, 268), t, font=f, fill=WHITE)
    label_chip(base, "SEC · CFTC nominations")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","credit":"SEC"},
        {"file":"Commodity_Futures_Trading_Commission_seal.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Commodity_Futures_Trading_Commission_seal.svg","credit":"CFTC"},
        {"file":"United_States_Capitol_-_west_front.jpg","license":"Public domain (Architect of the Capitol)","url":"https://commons.wikimedia.org/wiki/File:United_States_Capitol_-_west_front.jpg","credit":"Architect of the Capitol"},
    ],"note":"Editorial composite for identification; no endorsement implied."}


def thumb_illinois_tax():
    il = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e7/Seal_of_Illinois.svg", CACHE/"illinois-seal.svg")
    doj = fetch("https://upload.wikimedia.org/wikipedia/commons/5/54/Seal_of_the_United_States_Department_of_Justice.svg", CACHE/"doj-seal.svg")
    cap = fetch("https://upload.wikimedia.org/wikipedia/commons/7/70/State_Capitol_in_Springfield%2C_Illinois.jpg", CACHE/"illinois-capitol.jpg")
    base = darken(cover_fit(ImageOps.exif_transpose(Image.open(cap)).convert("RGB"), cy=0.4), 140)
    for logo, x in [(il, 130), (doj, 340)]:
        disc = Image.new("RGBA", (170, 170), (0, 0, 0, 0))
        ImageDraw.Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), (x, 70), disc)
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 70, 170, 170), pad=8)
    d = ImageDraw.Draw(base); f = font(FONT_B, 18); t = "0.2% digital asset tax challenged in court"
    bb = d.textbbox((0,0), t, font=f); d.text(((W-(bb[2]-bb[0]))//2, 268), t, font=f, fill=WHITE)
    label_chip(base, "Illinois crypto tax")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_Illinois.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Seal_of_Illinois.svg","credit":"State of Illinois"},
        {"file":"Seal_of_the_United_States_Department_of_Justice.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Department_of_Justice.svg","credit":"U.S. Department of Justice"},
        {"file":"State_Capitol_in_Springfield,_Illinois.jpg","license":"CC0","url":"https://commons.wikimedia.org/wiki/File:State_Capitol_in_Springfield,_Illinois.jpg","credit":"PhilDaBirdMan / Wikimedia Commons"},
    ],"note":"Editorial composite for identification; no endorsement implied."}


def thumb_dtcc_solana():
    dtcc = fetch("https://upload.wikimedia.org/wikipedia/commons/7/73/Depository_Trust_%26_Clearing_Corporation_logo.svg", CACHE/"dtcc-logo.svg")
    sol = fetch("https://cryptologos.cc/logos/solana-sol-logo.svg", CACHE/"solana-logo.svg")
    base = gradient_bg()
    card_w, card_h, gap, y0 = 220, 170, 110, 70
    x0 = (W - (2*card_w + gap))//2
    for i, (logo, bg) in enumerate([(dtcc, (255,255,255)), (sol, (0,0,0))]):
        x = x0 + i*(card_w+gap)
        tile = Image.new("RGBA", (card_w, card_h), bg+(255,))
        mask = Image.new("L", (card_w, card_h), 0); ImageDraw.Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
        base.paste(tile.convert("RGB"), (x, y0), mask)
        lg = Image.open(logo).convert("RGBA"); bgimg = Image.new("RGBA", lg.size, bg+(255,)); bgimg.paste(lg, (0,0), lg)
        paste_contain(base, bgimg, (x, y0, card_w, card_h), pad=26)
    d = ImageDraw.Draw(base); cx, cy = x0+card_w+gap//2, y0+card_h//2
    d.line([(cx-36,cy),(cx+30,cy)], fill=ORANGE, width=5); d.polygon([(cx+30,cy-11),(cx+46,cy),(cx+30,cy+11)], fill=ORANGE)
    f = font(FONT_B, 17); t = "Stocks, ETFs and Treasuries as tokens, 2H 2027"
    bb = d.textbbox((0,0), t, font=f); d.text(((W-(bb[2]-bb[0]))//2, y0+card_h+34), t, font=f, fill=WHITE)
    label_chip(base, "Tokenization · DTCC")
    return base, {"kind":"composite","sources":[
        {"file":"Depository_Trust_&_Clearing_Corporation_logo.svg","license":"Public domain (text logo)","url":"https://commons.wikimedia.org/wiki/File:Depository_Trust_%26_Clearing_Corporation_logo.svg","credit":"DTCC"},
        {"file":"solana-sol-logo.svg","license":"Logo","url":"https://cryptologos.cc/solana","credit":"Solana Foundation"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


KRAKEN_ICON = "https://assets-cms.kraken.com/images/51n36hrp/facade/c8a90889d470969a2f7864a0bfa1814c28b21310-1024x1024.svg"

def thumb_payward_q3():
    icon = fetch(KRAKEN_ICON, CACHE/"kraken-app-icon-purple.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    paste_contain(base, Image.open(icon).convert("RGBA"), (60, 80, 200, 200), pad=0)
    # Payward Q3 2026 financial highlights (Nov 13, 2026)
    rows = [("Volume", "$353B", "-30% vs. Q3 2025"), ("Funded accounts", "7.1M", "+37% vs. Q3 2025"), ("Adj. EBITDA", "$60M", "vs. $178.6M a year ago")]
    fb, fs = font(FONT_B, 30), font(FONT_R, 15)
    for i, (k, v, sub) in enumerate(rows):
        y = 74 + i * 72
        d.text((300, y), k.upper(), font=font(FONT_B, 13), fill=MUTED)
        d.text((300, y + 16), v, font=fb, fill=WHITE)
        vw = d.textlength(v, font=fb)
        d.text((300 + vw + 14, y + 28), sub, font=fs, fill=ORANGE if sub.startswith("+") else (248, 113, 113) if sub.startswith("-") else MUTED)
    label_chip(base, "Kraken · Q3 2026 results")
    return base, {"kind":"composite","sources":[
        {"file":"Kraken app icon (SVG)","license":"Official press asset","url":"https://www.kraken.com/press/kraken-images","credit":"Kraken / Payward"},
        {"file":"Payward Q3 2026 financial highlights","license":"Figures cited","url":"https://www.payward.com/press-release/payward-q3-2026-financial-highlights","credit":"Payward"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_treasury_loans():
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")
    eth = fetch("https://upload.wikimedia.org/wikipedia/commons/0/05/Ethereum_logo_2014.svg", CACHE/"ethereum-logo-2014.svg")
    base = gradient_bg()
    d = ImageDraw.Draw(base)
    for logo, x in [(btc, 120), (eth, 350)]:
        disc = Image.new("RGBA", (170, 170), (0, 0, 0, 0))
        ImageDraw.Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), (x, 62), disc)
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 62, 170, 170), pad=22)
    # padlock-style chain between the coins
    cx, cy = 320, 147
    for k in (-14, 14):
        d.ellipse([cx + k - 16, cy - 10, cx + k + 16, cy + 10], outline=ORANGE, width=4)
    f = font(FONT_B, 18); t = "Coins pledged as loan collateral"
    bb = d.textbbox((0, 0), t, font=f); d.text(((W - (bb[2] - bb[0])) // 2, 262), t, font=f, fill=WHITE)
    label_chip(base, "Crypto treasury firms")
    return base, {"kind":"composite","sources":[
        {"file":"Bitcoin.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Bitcoin.svg","credit":"Bitcoin logo"},
        {"file":"Ethereum_logo_2014.svg","license":"CC BY 3.0","url":"https://commons.wikimedia.org/wiki/File:Ethereum_logo_2014.svg","credit":"Ethereum Foundation"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


BUILDERS = {
    "is-coinbase-safe-for-beginners": thumb_coinbase_safe,
    "how-much-bitcoin-should-a-beginner-buy-dca": thumb_dca,
    "what-is-a-crypto-wallet-custodial-vs-self-custody": thumb_wallet,
    "coinbase-occ-national-trust-charter-nov-2026": thumb_occ,
    "fincen-fed-withdraw-250-travel-rule-nov-2026": thumb_fincen,
    "bitcoin-loses-50-week-moving-average-nov-2026": thumb_btc_50w,
    "bitcoin-volatility-liquidations-nov-2026": thumb_liquidations,
    "pnc-coinbase-usdc-payments-pilot-nov-2026": thumb_pnc_usdc,
    "us-midterms-crypto-regulation-etf-outflows": thumb_midterms,
    "how-to-buy-first-bitcoin-coinbase": thumb_howto,
    "binance-hack-north-korea-memecoin-laundering-nov-2026": thumb_binance_hack,
    "bitcoin-hot-cpi-etf-outflows-nov-2026": thumb_hot_cpi,
    "binance-blocks-mexc-fincen-order-nov-2026": thumb_mexc,
    "banks-270-million-stablecoin-project-faro-nov-2026": thumb_faro,
    "bitcoin-below-73000-lowest-since-august-nov-2026": thumb_btc_below_73k,
    "binance-warns-iphone-ios-flaw-wallet-keys-nov-2026": thumb_ios_flaw,
    "across-protocol-domain-hijack-phishing-nov-2026": thumb_across,
    "okxice-tokenized-stocks-launch-nov-23-2026": thumb_okxice,
    "stablecoin-supply-shrinks-usdt-tether-nov-2026": thumb_stablecoin_supply,
    "sec-backs-cftc-stock-perps-crypto-etf-options-nov-2026": thumb_sec_perps,
    "msci-drops-strategy-bitcoin-falls-nvidia-nov-2026": thumb_msci_strategy,
    "doj-seizes-1-2-billion-binance-hack-north-korea-nov-2026": thumb_doj_binance_seizure,
    "bitcoin-below-70000-200-week-average-nov-2026": thumb_btc_etf_outflows_nov,
    "trump-nominates-sec-cftc-commissioners-peirce-nov-2026": thumb_sec_cftc_nominees,
    "illinois-crypto-tax-doj-defi-challenge-nov-2026": thumb_illinois_tax,
    "dtcc-tokenized-stocks-solana-2027-nov-2026": thumb_dtcc_solana,
    "kraken-payward-q3-2026-results-nov-2026": thumb_payward_q3,
    "crypto-treasury-firms-loans-nakamoto-btcs-nov-2026": thumb_treasury_loans,
}

def first_figure_source(slug: str) -> Path | None:
    figs = I18N / slug / "figures.json"
    if figs.exists():
        data = json.loads(figs.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("figures", [])
        ordered = sorted(items, key=lambda f: 0 if f.get("kind")=="chart" or str(f.get("id","")).startswith("chart") else 1)
        for f in ordered:
            name = f.get("file") or f.get("src")
            if not name: continue
            p = IMG / slug / Path(name).name
            if p.exists() and not p.name.startswith("thumb"): return p
    d = IMG / slug
    if d.is_dir():
        for p in sorted(d.glob("*")):
            if p.suffix.lower() in {".webp",".png",".jpg",".jpeg"} and not p.name.startswith("thumb"):
                return p
    return None

def fallback_from_figure(slug: str):
    src = first_figure_source(slug)
    if not src: return None, None
    return cover_fit(open_rgb(src)), {"kind":"figure-fallback","sources":[{"file":str(src.relative_to(ROOT)),"license":"See article figures","url":"","credit":"Derived from mid-article figure"}]}

def build_one(slug: str) -> bool:
    print(f"· {slug}")
    try:
        if slug in BUILDERS: im, credits = BUILDERS[slug]()
        else:
            im, credits = fallback_from_figure(slug)
            if im is None: print("  skip"); return False
        save_thumb(im, slug, credits); return True
    except Exception as e:
        print(f"  ERROR {e}")
        try:
            im, credits = fallback_from_figure(slug)
            if im is None: return False
            credits["error"]=str(e); save_thumb(im, slug, credits); return True
        except Exception as e2:
            print(f"  FALLBACK ERROR {e2}"); return False

def published_slugs():
    idx = (ROOT/"index.html").read_text(encoding="utf-8"); seen=[]
    for m in re.finditer(r'href="(?:/articles/|articles/)([a-z0-9-]+)(?:\.html)?"', idx):
        s=m.group(1)
        if s not in seen: seen.append(s)
    return seen

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*"); ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    slugs = published_slugs() if args.all or not args.slugs else args.slugs
    ok = sum(1 for s in slugs if build_one(s))
    print(f"done: {ok}/{len(slugs)}"); return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
