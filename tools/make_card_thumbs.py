#!/usr/bin/env python3
"""Generate distinct 640x360 homepage card thumbnails for PlainBTC.

Topical thumbs from freely-licensed imagery (Wikimedia / U.S. government
public-domain works) and charts from real public market data (Kraken OHLC).
Article titles are NOT baked into the image.

Usage:
  .venv/bin/python tools/make_card_thumbs.py --all
  .venv/bin/python tools/make_card_thumbs.py <slug> [...]
  .venv/bin/python tools/make_card_thumbs.py --og [--all | <slug> ...]

Writes assets/img/<slug>/{thumb.webp,thumb.jpg,thumb.credits.json}
Unknown slugs: first mid-article figure. build_i18n falls back to OG if missing.

--og renders the SAME designs natively at 1200x630 (S=1.875, no upscaling) as the
per-article link preview assets/og/<slug>-v2.jpg used for og:image / twitter:image.
Builders therefore draw in 640x360 design units: use Draw(...) (not ImageDraw.Draw),
sz((w, h)) for Image.new / paste positions / resize, font(), paste_contain(), dw(im).
Crop coordinates on source images stay in source pixels.
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
W, H = 640, 360          # design units: every thumb_* builder draws in this 640x360 space
S = 1.0                  # render scale; --og renders the same designs natively at S=1.875 (1200x675)
OG_W, OG_H = 1200, 630   # link-preview size (X / Facebook)
OG_DIR = ROOT / "assets" / "og"
OG_SUFFIX = "-v2"
DATA_END = None          # --og: freeze live market data at the thumb's original "generated" time        # bump when previews change so X/Facebook refetch instead of using cached cards
UA = {"User-Agent": "PlainBTCThumbBot/1.0 (editorial thumbs; https://plainbtc.com)"}
CTX = ssl.create_default_context()
BG, NAVY, ORANGE = (15, 20, 28), (11, 22, 48), (247, 147, 26)
WHITE, MUTED, ACCENT = (255, 255, 255), (148, 163, 184), (59, 130, 246)
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def font(path, size):
    try: return ImageFont.truetype(path, max(1, round(size * S)))
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

def sz(t):
    """Design-unit tuple -> pixel tuple at the current render scale."""
    return tuple(int(round(v * S)) for v in t)

def _s(v):
    if isinstance(v, (int, float)): return v * S
    if isinstance(v, (list, tuple)): return type(v)(_s(x) for x in v)
    return v

def dw(im): return im.width / S
def dh(im): return im.height / S

class Draw:
    """ImageDraw.Draw that takes design-unit coordinates and scales them by S."""
    _SHAPES = {"rectangle", "rounded_rectangle", "ellipse", "arc", "chord", "pieslice", "polygon"}
    def __init__(self, im, mode=None):
        self._d = ImageDraw.Draw(im, mode) if mode else ImageDraw.Draw(im)
    def textbbox(self, xy, text, font=None, **kw):
        return tuple(v / S for v in self._d.textbbox(_s(xy), text, font=font, **kw))
    def textlength(self, text, font=None, **kw):
        return self._d.textlength(text, font=font, **kw) / S
    def __getattr__(self, name):
        fn = getattr(self._d, name)
        def call(*a, **kw):
            if a: a = (_s(a[0]),) + a[1:]
            if "xy" in kw: kw["xy"] = _s(kw["xy"])
            for k in ("width", "radius", "stroke_width", "spacing"):
                if kw.get(k): kw[k] = max(1, round(kw[k] * S))
            if S > 1 and name in self._SHAPES and kw.get("outline") is not None and "width" not in kw:
                kw["width"] = max(1, round(S))
            return fn(*a, **kw)
        return call

def cover_fit(im: Image.Image, w=None, h=None, cy=0.45) -> Image.Image:
    w = w or round(W * S); h = h or round(H * S)
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

def gradient_bg(w=None, h=None, top=NAVY, bottom=BG) -> Image.Image:
    w = w or round(W * S); h = h or round(H * S)
    t = np.linspace(0, 1, h)[:, None]
    col = (np.array(top)[None, :] * (1 - t) + np.array(bottom)[None, :] * t).astype(np.uint8)
    return Image.fromarray(np.repeat(col[:, None, :], w, axis=1), "RGB")

def paste_contain(base: Image.Image, overlay: Image.Image, box, pad=8):
    x, y, bw, bh = sz(box); pad = pad * S
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
    cd = Draw(chip); f = font(FONT_B, 14)
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
    if DATA_END: rows = [r for r in rows if r[0] <= DATA_END.timestamp()]
    xs = [datetime.fromtimestamp(r[0], tz=timezone.utc) for r in rows]
    closes = [float(r[4]) for r in rows]
    return xs, closes

def chart_to_image(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140 * S, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.12)
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
    panel = Image.new("RGBA", base.size, (0,0,0,0)); Draw(panel).rectangle([0,0,310,H], fill=(10,16,28,205))
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
    panel = Image.new("RGBA", base.size, (0,0,0,0)); Draw(panel).rounded_rectangle([36,40,W-36,H-40], radius=18, fill=(15,23,42,205))
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
    im = chart_to_image(fig); d = Draw(im)
    d.rounded_rectangle([dw(im)-210,16,dw(im)-12,76], radius=10, fill=(127,29,29))
    d.text((dw(im)-198,26), "$1B+", font=font(FONT_B,18), fill=WHITE)
    d.text((dw(im)-198,50), "liquidations (CoinGlass)", font=font(FONT_R,10), fill=(254,202,202))
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
        card=Image.new("RGBA",sz((card_w,card_h)),(26,35,50,235))
        Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",sz((card_w,card_h)),0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), sz((x,y0)), mask)
        paste_contain(base, logo, (x,y0+8,card_w,145), pad=14)
        d=Draw(base); f=font(FONT_B,13); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
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
    overlay = Image.new("RGBA", base.size, (0,0,0,0)); Draw(overlay).rectangle([0,int(H*0.42),W,H], fill=(8,14,28,215))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    labels=["Jun","Jul","Aug","Sep","Oct","Nov"]; vals=[0.4,0.15,-0.1,0.2,-0.35,-1.0]
    fig, ax = plt.subplots(figsize=(3.5,1.45), dpi=120); fig.patch.set_facecolor("#0f1419"); ax.set_facecolor("#0f1419")
    ax.bar(labels, vals, color=["#34d399" if v>=0 else "#f87171" for v in vals], width=0.65)
    ax.axhline(0, color="#9aa8bc", linewidth=0.8); ax.set_ylim(-1.25,0.7)
    ax.tick_params(colors="white", labelsize=7)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_yticks([]); ax.set_title("Spot BTC ETF weekly flows (schematic)", color="white", fontsize=8, loc="left", pad=2)
    chart = ImageOps.fit(chart_to_image(fig), sz((340,145)), method=Image.Resampling.LANCZOS)
    base.paste(chart, sz((W-356, H-160))); label_chip(base, "Midterms · ETF outflows")
    return base, {"kind":"composite","sources":[
        {"file":"United_States_Capitol_-_west_front.jpg","license":"Public domain (Architect of the Capitol)","url":"https://commons.wikimedia.org/wiki/File:United_States_Capitol_-_west_front.jpg","credit":"Architect of the Capitol"},
        {"file":"ETF flow schematic","license":"PlainBTC chart","url":"","credit":"Schematic bars for Nov 2026 large weekly outflow; see article sources"},
    ]}

def thumb_howto():
    coinbase = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e1/Bitcoin_logo_clean.svg", CACHE/"btc-logo.svg")
    base = gradient_bg(); d = Draw(base)
    px,py,pw,ph = 210,28,220,304
    d.rounded_rectangle([px,py,px+pw,py+ph], radius=28, fill=(26,35,50), outline=(45,58,79), width=3)
    d.rounded_rectangle([px+70,py+10,px+pw-70,py+22], radius=6, fill=(15,20,28))
    sx,sy,sw,sh = px+14, py+36, pw-28, ph-50
    d.rounded_rectangle([sx,sy,sx+sw,sy+sh], radius=12, fill=(15,23,42))
    paste_contain(base, Image.open(coinbase).convert("RGBA"), (sx+16,sy+14,sw-32,44), pad=0)
    d = Draw(base)
    d.text((sx+20,sy+66), "Buy Bitcoin", font=font(FONT_B,14), fill=WHITE)
    d.text((sx+20,sy+88), "BTC · Coinbase", font=font(FONT_R,10), fill=MUTED)
    paste_contain(base, Image.open(btc).convert("RGBA"), (sx+sw-66,sy+66,50,50), pad=0)
    d = Draw(base)
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
    d = Draw(base)
    # large shield
    d.rounded_rectangle([40, 50, 280, 310], radius=24, fill=(26, 35, 50), outline=(45, 58, 79), width=2)
    # lock body
    d.rounded_rectangle([110, 150, 210, 250], radius=16, fill=ACCENT)
    d.arc([120, 95, 200, 175], start=0, end=180, fill=ORANGE, width=10)
    d.ellipse([145, 185, 175, 215], fill=WHITE)
    d.rectangle([156, 210, 164, 235], fill=WHITE)
    paste_contain(base, Image.open(coinbase).convert("RGBA"), (320, 70, 140, 140), pad=4)
    d = Draw(base)
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
    d = Draw(im)
    d.rounded_rectangle([dw(im)-200, 14, dw(im)-12, 70], radius=10, fill=(30, 58, 138))
    d.text((dw(im)-188, 22), "DCA", font=font(FONT_B, 16), fill=WHITE)
    d.text((dw(im)-188, 44), "small regular buys", font=font(FONT_R, 10), fill=(191, 219, 254))
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=10080","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Weekly BTC/USD from Kraken; DCA markers illustrative"},
    ]}


def thumb_wallet():
    base = gradient_bg()
    d = Draw(base)
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
    d = Draw(base)
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
        card=Image.new("RGBA",sz((card_w,card_h)),(26,35,50,235))
        Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",sz((card_w,card_h)),0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), sz((x,y0)), mask)
        paste_contain(base, logo, (x,y0+8,card_w,125), pad=16)
        d=Draw(base); f=font(FONT_B,14); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
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
        card=Image.new("RGBA",sz((card_w,card_h)),(26,35,50,235))
        Draw(card).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, outline=(45,58,79,255), width=2)
        mask=Image.new("L",sz((card_w,card_h)),0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(card.convert("RGB"), sz((x,y0)), mask)
        paste_contain(base, logo, (x,y0+8,card_w,logo_h), pad=pad)
        d=Draw(base); f=font(FONT_B,13); bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
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
    d = Draw(base); cx, cy = x0+card_w+gap//2, y0+card_h//2
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
    d = Draw(base)
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
        tile=Image.new("RGBA",sz((card_w,card_h)),(255,255,255,255))
        mask=Image.new("L",sz((card_w,card_h)),0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(tile.convert("RGB"), sz((x,y0)), mask)
        lg = logo.copy(); bgw = Image.new("RGBA", lg.size, (255,255,255,255)); bgw.paste(lg,sz((0,0)),lg)
        paste_contain(base, bgw, (x,y0+6,card_w,112), pad=14)
        dd=Draw(base); f=font(FONT_B,12); bb=dd.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
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
    ph.thumbnail(sz((10000, 290)), Image.Resampling.LANCZOS)
    base.paste(ph, sz((80, 56)))
    d = Draw(base)
    # warning triangle between phone and logo
    cx, cy = 320, 196
    d.polygon([(cx, cy-46), (cx-52, cy+42), (cx+52, cy+42)], fill=(247,147,26))
    fb = font(FONT_B, 54); bb = d.textbbox((0,0),"!",font=fb)
    d.text((cx-(bb[2]-bb[0])//2-2, cy-34), "!", font=fb, fill=(15,20,28))
    cw, ch, x, y = 210, 180, 400, 106
    card = Image.new("RGB", sz((cw, ch)), (26,35,50))
    mask = Image.new("L", sz((cw, ch)), 0); Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=14, fill=255)
    base.paste(card, sz((x, y)), mask)
    paste_contain(base, Image.open(binance).convert("RGBA"), (x, y+8, cw, 130), pad=16)
    d = Draw(base); f = font(FONT_B, 13); t = "Security warning"; bb = d.textbbox((0,0),t,font=f)
    d.text((x+(cw-(bb[2]-bb[0]))//2, y+148), t, font=f, fill=WHITE)
    label_chip(base, "iOS flaw · wallet security")
    return base, {"kind":"composite","sources":[
        {"file":"Front_of_iPhone_15_Pro_Max.jpg","license":"CC BY 4.0","url":"https://commons.wikimedia.org/wiki/File:Front_of_iPhone_15_Pro_Max.jpg","credit":"Ayamano2021 / Wikimedia Commons"},
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_across():
    """Generated graphic: a browser window on across.to swapped for a fake approval prompt (no third-party imagery)."""
    base = gradient_bg()
    d = Draw(base)
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
    d = Draw(base)
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
        tile = Image.new("RGB",sz((card_w,card_h)),(255,255,255))
        mask = Image.new("L",sz((card_w,card_h)),0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(tile,sz((x,y0)),mask)
        lg = logo.copy(); bgw = Image.new("RGBA", lg.size, (255,255,255,255)); bgw.paste(lg,sz((0,0)),lg)
        paste_contain(base, bgw, (x, y0+6, card_w, 122), pad=18)
        dd = Draw(base); f = font(FONT_B, 12); bb = dd.textbbox((0,0),name,font=f)
        dd.text((x+(card_w-(bb[2]-bb[0]))//2, y0+140), name, font=f, fill=(15,23,42))
    d = Draw(base); fb = font(FONT_B, 34); bb = d.textbbox((0,0),"+",font=fb)
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
    rows = [r for r in rows if int(r["date"]) >= start and (not DATA_END or int(r["date"]) <= DATA_END.timestamp())]
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
    panel = Image.new("RGBA", base.size, (0,0,0,0)); Draw(panel).rounded_rectangle([36,40,W-36,H-40], radius=18, fill=(15,23,42,190))
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
    base = Image.new("RGB", sz((W, H)), (15, 20, 25))
    d = Draw(base)
    for i in range(0, W, 32):
        d.line([(i, 0), (i, H)], fill=(24, 32, 42))
    for j in range(0, H, 32):
        d.line([(0, j), (W, j)], fill=(24, 32, 42))
    card = Image.new("RGBA", sz((360, 180)), (255, 255, 255, 255))
    mask = Image.new("L", card.size, 0); Draw(mask).rounded_rectangle([0, 0, 359, 179], radius=16, fill=255)
    x0, y0 = (W - 360) // 2, (H - 180) // 2 - 10
    base.paste(card, sz((x0, y0)), mask)
    paste_contain(base, Image.open(logo).convert("RGBA"), (x0, y0, 360, 180), pad=34)
    label_chip(base, "Index review · Strategy (MSTR)")
    return base, {"kind":"composite","sources":[
        {"file":"MSCI_logo.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:MSCI_logo.svg","credit":"MSCI"},
    ],"note":"Editorial use of the MSCI logo for identification; trademark belongs to its owner."}


def thumb_doj_binance_seizure():
    doj = fetch("https://upload.wikimedia.org/wikipedia/commons/5/54/Seal_of_the_United_States_Department_of_Justice.svg", CACHE/"doj-seal.svg")
    fbi = fetch("https://upload.wikimedia.org/wikipedia/commons/d/da/Seal_of_the_Federal_Bureau_of_Investigation.svg", CACHE/"fbi-seal.svg")
    base = gradient_bg()
    d = Draw(base)
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
        disc = Image.new("RGBA", sz((170, 170)), (0, 0, 0, 0))
        Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), sz((x, 70)), disc)
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 70, 170, 170), pad=8)
    d = Draw(base); f = font(FONT_B, 16); t = "4 nominees await Senate confirmation"
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
        disc = Image.new("RGBA", sz((170, 170)), (0, 0, 0, 0))
        Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), sz((x, 70)), disc)
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 70, 170, 170), pad=8)
    d = Draw(base); f = font(FONT_B, 18); t = "0.2% digital asset tax challenged in court"
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
        tile = Image.new("RGBA", sz((card_w, card_h)), bg+(255,))
        mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
        base.paste(tile.convert("RGB"), sz((x, y0)), mask)
        lg = Image.open(logo).convert("RGBA"); bgimg = Image.new("RGBA", lg.size, bg+(255,)); bgimg.paste(lg, sz((0,0)), lg)
        paste_contain(base, bgimg, (x, y0, card_w, card_h), pad=26)
    d = Draw(base); cx, cy = x0+card_w+gap//2, y0+card_h//2
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
    d = Draw(base)
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
    d = Draw(base)
    for logo, x in [(btc, 120), (eth, 350)]:
        disc = Image.new("RGBA", sz((170, 170)), (0, 0, 0, 0))
        Draw(disc).ellipse([0, 0, 169, 169], fill=(255, 255, 255, 255))
        base.paste(disc.convert("RGB"), sz((x, 62)), disc)
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


def thumb_btc_below_67k():
    """Kraken XBTUSD daily closes, Oct 1 - Nov 14, 2026 (Nov 14 = latest trade at build time)."""
    xs, closes = kraken_ohlc(1440)
    start = datetime(2026, 10, 1, tzinfo=timezone.utc); end = datetime(2026, 11, 15, tzinfo=timezone.utc)
    pts = [(x, c) for x, c in zip(xs, closes) if start <= x < end]
    xs, closes = [p[0] for p in pts], [p[1] for p in pts]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    ax.plot(xs, closes, color="#f7931a", linewidth=2.0)
    ax.fill_between(xs, closes, min(closes) * 0.97, color="#f87171", alpha=0.18)
    ax.set_ylim(min(closes) * 0.97, max(closes) * 1.06)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    im = chart_to_image(fig)
    label_chip(im, "Bitcoin daily close since Oct. 1 (Kraken)")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Daily BTC/USD closes, Oct 1 - Nov 14, 2026, from Kraken"}
    ]}


def thumb_unocoin_keys():
    """Original 2-of-3 multisig diagram with Unocoin and BitGo logos (identification only)."""
    uno = fetch("https://upload.wikimedia.org/wikipedia/commons/f/f8/Unocoin-logo.png", CACHE/"unocoin-logo.png")
    bitgo = fetch("https://upload.wikimedia.org/wikipedia/commons/b/be/BitGo_Color_Large.png", CACHE/"bitgo-logo.png")
    base = gradient_bg(); d = Draw(base)
    RED, GRAYC = (248, 113, 113), (100, 116, 139)
    cols = [(60, "User key", "Unocoin", RED, "used"), (245, "Backup key", "Unocoin", RED, "used"), (430, "BitGo key", "BitGo", GRAYC, "not used")]
    for x, name, owner, col, status in cols:
        tile = Image.new("RGBA", sz((150, 150)), (0, 0, 0, 0))
        Draw(tile).rounded_rectangle([0, 0, 149, 149], radius=18, fill=(255, 255, 255, 255))
        base.paste(tile.convert("RGB"), sz((x, 62)), tile)
        logo = uno if owner == "Unocoin" else bitgo
        paste_contain(base, Image.open(logo).convert("RGBA"), (x, 62, 150, 70), pad=12)
        # simple key glyph
        kx, ky = x + 52, 160
        d.ellipse([kx - 18, ky - 18, kx + 18, ky + 18], outline=col, width=6)
        d.line([(kx + 18, ky), (kx + 66, ky)], fill=col, width=6)
        d.line([(kx + 50, ky), (kx + 50, ky + 14)], fill=col, width=6)
        d.line([(kx + 62, ky), (kx + 62, ky + 12)], fill=col, width=6)
        f = font(FONT_B, 16); tw = d.textlength(name, font=f); d.text((x + 75 - tw / 2, 226), name, font=f, fill=WHITE)
        f2 = font(FONT_R, 13); t2 = f"{owner} · {status}"; tw = d.textlength(t2, font=f2); d.text((x + 75 - tw / 2, 250), t2, font=f2, fill=col)
    f = font(FONT_B, 18); t = "2 of 3 keys signed, so a BitGo freeze could not stop it"
    tw = d.textlength(t, font=f); d.text(((W - tw) / 2, 296), t, font=f, fill=ORANGE)
    label_chip(base, "Unocoin · 2-of-3 multisig wallet")
    return base, {"kind":"composite","sources":[
        {"file":"Unocoin-logo.png","license":"CC BY-SA 4.0","url":"https://commons.wikimedia.org/wiki/File:Unocoin-logo.png","credit":"Unocoin / Wikimedia Commons"},
        {"file":"BitGo_Color_Large.png","license":"CC BY-SA 4.0","url":"https://commons.wikimedia.org/wiki/File:BitGo_Color_Large.png","credit":"BitGo / Wikimedia Commons"},
        {"file":"2-of-3 key diagram","license":"PlainBTC original","url":"https://www.bitgo.com/resources/blog/unocoin-security-incident/","credit":"PlainBTC, based on BitGo's Nov. 13, 2026 description"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_alt_selloff():
    """Kraken hourly closes for BTC, ETH, XRP, SOL as % change from Nov 13 19:00 UTC to Nov 14 19:00 UTC."""
    t0 = datetime(2026, 11, 13, 19, tzinfo=timezone.utc); t1 = datetime(2026, 11, 14, 19, tzinfo=timezone.utc)
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    for name, pair, col in [("BTC", "XBTUSD", "#f7931a"), ("ETH", "ETHUSD", "#818cf8"), ("XRP", "XRPUSD", "#cbd5e1"), ("SOL", "SOLUSD", "#f87171")]:
        xs, closes = kraken_ohlc(60, pair)
        pts = [(x, c) for x, c in zip(xs, closes) if t0 <= x <= t1]
        base_px = pts[0][1]
        ys = [(c / base_px - 1) * 100 for _, c in pts]
        ax.plot([p[0] for p in pts], ys, color=col, linewidth=2.0, label=name)
    ax.axhline(0, color="#475569", linewidth=1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{v:.0f}%"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    leg = ax.legend(loc="lower left", fontsize=9, frameon=False)
    for t in leg.get_texts(): t.set_color("#e2e8f0")
    im = chart_to_image(fig)
    label_chip(im, "24-hour change, Nov. 13-14 (Kraken, UTC)")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD/ETHUSD/XRPUSD/SOLUSD interval=60","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Hourly closes, Nov 13 19:00 - Nov 14 19:00 UTC, from Kraken"}
    ]}


def thumb_binance_reopen():
    """Binance logo (identification) with the figure from Binance's Nov 14, 2026 X post."""
    binance = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")
    base = gradient_bg()
    card_w, card_h = 230, 200
    x, y = 70, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (26,35,50,235))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(binance).convert("RGBA"), (x, y, card_w, card_h), pad=24)
    d = Draw(base)
    d.text((350, 92), "87", font=font(FONT_B, 92), fill=ORANGE)
    d.text((352, 200), "networks reopened", font=font(FONT_B, 22), fill=WHITE)
    d.text((352, 232), "for withdrawals this week", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Binance · withdrawals")
    return base, {"kind":"composite","sources":[
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
        {"file":"Binance post on X, Nov. 14, 2026","license":"Figure cited","url":"https://x.com/binance/status/2121452596171010552","credit":"Binance"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_btc_below_64k():
    """Kraken XBTUSD daily lows, Aug 1 - Nov 14, 2026: back to the mid-August lows."""
    xs, _c = kraken_ohlc(1440)
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = next(v for k, v in json.load(r)["result"].items() if k != "last")
    start = datetime(2026, 8, 1, tzinfo=timezone.utc); end = datetime(2026, 11, 15, tzinfo=timezone.utc)
    pts = [(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[3])) for r in rows]
    pts = [p for p in pts if start <= p[0] < end]
    xs, lows = [p[0] for p in pts], [p[1] for p in pts]
    fig, ax = plt.subplots(figsize=(6.4,3.6), dpi=100); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "")
    ax.plot(xs, lows, color="#f7931a", linewidth=2.0)
    ax.axhline(lows[-1], color="#38bdf8", linestyle="--", linewidth=1.2)
    ax.set_ylim(min(lows) * 0.97, max(lows) * 1.04)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    im = chart_to_image(fig)
    label_chip(im, "Bitcoin daily low since Aug. 1 (Kraken)")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Daily BTC/USD lows, Aug 1 - Nov 14, 2026, from Kraken"}
    ]}


def thumb_kava_hack():
    """Kava logo (identification) with the drained amount from The Block's Nov 14, 2026 report."""
    kava = fetch("https://cryptologos.cc/logos/kava-kava-logo.svg", CACHE/"kava-logo.svg")
    base = gradient_bg()
    card_w, card_h = 230, 200
    x, y = 70, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (255,255,255,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(kava).convert("RGBA"), (x, y, card_w, card_h), pad=30)
    d = Draw(base)
    d.text((350, 92), "55.2M", font=font(FONT_B, 80), fill=ORANGE)
    d.text((352, 200), "KAVA drained", font=font(FONT_B, 22), fill=WHITE)
    d.text((352, 232), "from Kava Lend, about $3.76M", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Kava Lend · exploit")
    return base, {"kind":"composite","sources":[
        {"file":"kava-kava-logo.svg","license":"Logo","url":"https://cryptologos.cc/kava","credit":"Kava"},
        {"file":"The Block, Nov. 14, 2026","license":"Figure cited","url":"https://www.theblock.co/news/defi/2026-11-14-kava-lend-loses-roughly-3-8-million-to-hack-sending-kava-token-down-nearly-40-440350","credit":"The Block"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_btc_62k_low():
    """Bitcoin logo (public domain, identification) with the Kraken low from Kraken's public OHLC data."""
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")
    base = gradient_bg()
    card_w, card_h = 230, 200
    x, y = 60, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (255,255,255,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(btc).convert("RGBA"), (x, y, card_w, card_h), pad=30)
    d = Draw(base)
    d.text((320, 100), "$61,970", font=font(FONT_B, 60), fill=ORANGE)
    d.text((322, 192), "Bitcoin low on Kraken", font=font(FONT_B, 22), fill=WHITE)
    d.text((322, 224), "lowest price since July 13", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Bitcoin · four-month low")
    return base, {"kind":"composite","sources":[
        {"file":"Bitcoin.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Bitcoin.svg","credit":"Bitcoin logo"},
        {"file":"Kraken OHLC XBTUSD","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Kraken BTC/USD low, Nov. 15, 2026 (UTC)"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_coinone_breach():
    """Coinone logo (cropped from Coinone's official share image, identification) with the count from Coinone's notice."""
    src = fetch("https://image-public.coinone.co.kr/og/og_talk.png", CACHE/"coinone-og.png")
    logo = Image.open(src).convert("RGBA").crop((261, 233, 917, 380))
    base = gradient_bg()
    card_w, card_h = 250, 200
    x, y = 50, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (0,68,210,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, card_w, card_h), pad=18)
    d = Draw(base)
    d.text((340, 92), "11", font=font(FONT_B, 92), fill=ORANGE)
    d.text((342, 200), "kinds of personal data", font=font(FONT_B, 22), fill=WHITE)
    d.text((342, 232), "may have leaked from support", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Coinone · data breach")
    return base, {"kind":"composite","sources":[
        {"file":"og_talk.png","license":"Logo","url":"https://image-public.coinone.co.kr/og/og_talk.png","credit":"Coinone"},
        {"file":"Coinone notice, Nov. 15, 2026","license":"Figure cited","url":"https://coinone.co.kr/info/notice/5950","credit":"Coinone"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_stusdt_wind_down():
    """stUSDT logo from stusdt.io (identification) with DefiLlama's value-locked figure."""
    logo = fetch("https://stusdt.io/logo192.png", CACHE/"stusdt-logo192.png")
    base = gradient_bg()
    card_w, card_h = 230, 200
    x, y = 60, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (255,255,255,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(logo).convert("RGBA"), (x, y, card_w, card_h), pad=24)
    d = Draw(base)
    d.text((330, 100), "$8.4M", font=font(FONT_B, 76), fill=ORANGE)
    d.text((332, 200), "value locked in stUSDT", font=font(FONT_B, 22), fill=WHITE)
    d.text((332, 232), "down from a $2.3B peak in 2023", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "stUSDT · wind down")
    return base, {"kind":"composite","sources":[
        {"file":"logo192.png","license":"Logo","url":"https://stusdt.io/logo192.png","credit":"stUSDT"},
        {"file":"DefiLlama stUSDT TVL, Nov. 15, 2026","license":"Figure cited","url":"https://defillama.com/protocol/stusdt","credit":"DefiLlama"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_luxor_hashrate_hijack():
    """Luxor logo (cropped from Luxor's official share image) and OCEAN logotype (ocean.xyz), identification only."""
    src = fetch("https://storage.googleapis.com/luxcorp-assets/images/corp-site-premium/product-banners/default-og.png", CACHE/"luxor-og.png")
    luxor = Image.open(src).convert("RGBA").crop((250, 226, 934, 400))
    ocean = Image.open(fetch("https://ocean.xyz/static/assets/home/logotype.svg", CACHE/"ocean-logotype.svg")).convert("RGBA")
    base = gradient_bg()
    card_w, card_h = 250, 110
    for (img, bg, y) in ((luxor, (10,10,10,255), 70), (ocean, (10,22,40,255), 196)):
        x = 40
        tile = Image.new("RGBA", sz((card_w, card_h)), bg)
        mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=14, fill=255)
        base.paste(tile.convert("RGB"), sz((x, y)), mask)
        paste_contain(base, img, (x, y, card_w, card_h), pad=16)
    d = Draw(base)
    d.text((320, 100), "13 EH/s", font=font(FONT_B, 54), fill=ORANGE)
    d.text((322, 180), "of mining power", font=font(FONT_B, 22), fill=WHITE)
    d.text((322, 212), "sent to OCEAN, reports say", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Luxor Commander · hijack")
    return base, {"kind":"composite","sources":[
        {"file":"default-og.png","license":"Logo","url":"https://storage.googleapis.com/luxcorp-assets/images/corp-site-premium/product-banners/default-og.png","credit":"Luxor Technology"},
        {"file":"logotype.svg","license":"Logo","url":"https://ocean.xyz/static/assets/home/logotype.svg","credit":"OCEAN"},
        {"file":"CoreX Hosting estimate via Bitcoin.com News, Nov. 15, 2026","license":"Figure cited","url":"https://news.bitcoin.com/security/luxor-confirms-bitcoin-mining-hack-and-reveals-ai-enabled-attack/","credit":"Bitcoin.com News"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_germany_customs_crypto():
    """German customs (Zoll) logo, public domain on Wikimedia Commons, with the bill's threshold."""
    logo = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/1/11/Zoll.svg", CACHE/"zoll.svg")).convert("RGBA")
    base = gradient_bg()
    card_w, card_h = 250, 200
    x, y = 50, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (255,255,255,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, card_w, card_h), pad=20)
    d = Draw(base)
    d.text((320, 100), "€100,000", font=font(FONT_B, 50), fill=ORANGE)
    d.text((322, 180), "crypto, unclear origin", font=font(FONT_B, 22), fill=WHITE)
    d.text((322, 212), "held up to 180 days", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Germany · customs law")
    return base, {"kind":"composite","sources":[
        {"file":"Zoll.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Zoll.svg","credit":"German Federal Customs Service logo"},
        {"file":"Bundestag bill, Drucksache 21/9136","license":"Figure cited","url":"https://bundestag.parlamente.org/drucksache/21/9136","credit":"Deutscher Bundestag"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}



def thumb_strategy_485_btc():
    """Strategy logo (2025, public domain on Wikimedia Commons) with the holdings from Strategy's Nov. 16, 2026 Form 8-K."""
    logo = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Strategy_logo_%282025%29.svg", CACHE/"strategy-logo-2025.svg")).convert("RGBA")
    base = gradient_bg()
    card_w, card_h = 250, 200
    x, y = 50, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (255,255,255,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, card_w, card_h), pad=24)
    d = Draw(base)
    d.text((326, 104), "+485 BTC", font=font(FONT_B, 48), fill=ORANGE)
    d.text((332, 180), "850,849 BTC in total", font=font(FONT_B, 22), fill=WHITE)
    d.text((332, 212), "average cost $75,452 per coin", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Strategy · weekly buy")
    return base, {"kind":"composite","sources":[
        {"file":"Strategy_logo_(2025).svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Strategy_logo_(2025).svg","credit":"Strategy logo"},
        {"file":"Strategy Form 8-K, Nov. 16, 2026","license":"Figure cited","url":"https://www.strategy.com/press/strategy-acquires-485-btc-and-repurchases-228-million-of-strc_11-16-2026","credit":"Strategy"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_fear_greed_10():
    """Original gauge graphic drawn from Alternative.me's Crypto Fear & Greed Index value (10 on Nov. 16, 2026)."""
    import math
    base = gradient_bg()
    d = Draw(base)
    cx, cy, r = 190, 270, 150
    bands = [(0, 25, (220, 38, 38)), (25, 46, (249, 115, 22)), (46, 55, (234, 179, 8)), (55, 75, (132, 204, 22)), (75, 100, (22, 163, 74))]
    for lo, hi, col in bands:
        d.arc([cx-r, cy-r, cx+r, cy+r], start=180 + lo*1.8, end=180 + hi*1.8, fill=col, width=34)
    val = 10
    ang = math.radians(180 + val*1.8)
    nx, ny = cx + (r-30)*math.cos(ang), cy + (r-30)*math.sin(ang)
    d.line([cx, cy, nx, ny], fill=WHITE, width=7)
    d.ellipse([cx-12, cy-12, cx+12, cy+12], fill=WHITE)
    d.text((cx-r-6, cy+12), "0", font=font(FONT_R, 16), fill=(203,213,225))
    d.text((cx+r-22, cy+12), "100", font=font(FONT_R, 16), fill=(203,213,225))
    d.text((390, 96), "10", font=font(FONT_B, 96), fill=ORANGE)
    d.text((392, 214), "Extreme fear", font=font(FONT_B, 24), fill=WHITE)
    d.text((392, 248), "lowest since June 10", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Crypto Fear & Greed Index")
    return base, {"kind":"graphic","sources":[
        {"file":"Alternative.me Crypto Fear & Greed Index, Nov. 16, 2026","license":"Data with attribution","url":"https://alternative.me/crypto/fear-and-greed-index/","credit":"Alternative.me"},
    ],"note":"Original PlainBTC gauge graphic; value from Alternative.me."}


def thumb_lighter_api_key():
    """Lighter logo (identification) with the withdrawn amount traced by Bitquery on Nov. 16, 2026."""
    logo = fetch("https://coin-images.coingecko.com/coins/images/71121/large/lighter.png", CACHE/"lighter-logo.png")
    base = gradient_bg()
    card_w, card_h = 230, 200
    x, y = 70, 80
    tile = Image.new("RGBA", sz((card_w, card_h)), (6,6,6,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(logo).convert("RGBA"), (x, y, card_w, card_h), pad=20)
    d = Draw(base)
    d.text((350, 100), "$10.4M", font=font(FONT_B, 66), fill=ORANGE)
    d.text((352, 200), "USDC withdrawn", font=font(FONT_B, 22), fill=WHITE)
    d.text((352, 232), "via one trader's leaked API key", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Lighter · leaked API key")
    return base, {"kind":"composite","sources":[
        {"file":"lighter.png","license":"Logo","url":"https://www.coingecko.com/en/coins/lighter","credit":"Lighter (logo via CoinGecko)"},
        {"file":"Bitquery, Nov. 16, 2026","license":"Figure cited","url":"https://bitquery.io/investigations/lighter-hack","credit":"Bitquery"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_chainflip_vault_drain():
    """Chainflip logo (identification) + vault diagram; amounts from the Ethereum transaction
    0xc928950f... (block 26,461,896, Nov. 21, 2026 07:10:59 UTC) and the $4.86M estimate cited by The Block / CoinDesk."""
    logo = fetch("https://coin-images.coingecko.com/coins/images/25576/large/kdt_AgmT_400x400.png", CACHE/"chainflip-logo.png")
    base = gradient_bg(top=(28, 14, 40), bottom=(8, 10, 16))
    d = Draw(base)
    GREEN, PINK = (70, 218, 150), (255, 76, 160)
    # logo tile
    lx, ly, ls = 34, 70, 128
    tile = Image.new("RGBA", sz((ls, ls)), (0, 0, 0, 255))
    mask = Image.new("L", sz((ls, ls)), 0); Draw(mask).rounded_rectangle([0, 0, ls-1, ls-1], radius=18, fill=255)
    base.paste(tile.convert("RGB"), sz((lx, ly)), mask)
    paste_contain(base, Image.open(logo).convert("RGBA"), (lx, ly, ls, ls), pad=4)
    d = Draw(base)
    d.text((lx + 4, ly + ls + 14), "Chainflip", font=font(FONT_B, 20), fill=WHITE)
    d.text((lx + 4, ly + ls + 42), "cross-chain swaps", font=font(FONT_R, 13), fill=MUTED)
    # vault box
    vx0, vy0, vx1, vy1 = 190, 62, 392, 300
    d.rounded_rectangle([vx0, vy0, vx1, vy1], radius=16, fill=(18, 22, 32), outline=GREEN, width=2)
    d.text((vx0 + 16, vy0 + 14), "ETHEREUM VAULT", font=font(FONT_B, 14), fill=GREEN)
    rows = [("520.22", "ETH"), ("3,249,631", "USDC"), ("758,141", "USDT")]
    y = vy0 + 50
    for amt, sym in rows:
        d.rounded_rectangle([vx0 + 14, y, vx1 - 14, y + 50], radius=10, fill=(32, 38, 54))
        d.text((vx0 + 26, y + 8), amt, font=font(FONT_B, 22), fill=WHITE)
        d.text((vx0 + 26, y + 33), sym, font=font(FONT_R, 11), fill=MUTED)
        y += 60
    # arrow
    ay = 181
    d.line([(vx1 + 6, ay), (440, ay)], fill=PINK, width=4)
    d.polygon([(440, ay - 11), (458, ay), (440, ay + 11)], fill=PINK)
    # outflow box
    ox0 = 466
    d.text((ox0, 110), "≈ $4.86M", font=font(FONT_B, 27), fill=ORANGE)
    d.text((ox0, 150), "out in one", font=font(FONT_B, 16), fill=WHITE)
    d.text((ox0, 172), "validly signed", font=font(FONT_B, 16), fill=WHITE)
    d.text((ox0, 194), "transaction", font=font(FONT_B, 16), fill=WHITE)
    d.text((ox0, 232), "then into", font=font(FONT_R, 14), fill=(203, 213, 225))
    d.text((ox0, 252), "Tornado Cash", font=font(FONT_R, 14), fill=(203, 213, 225))
    d.text((ox0, 272), "within ~9 minutes", font=font(FONT_R, 14), fill=(203, 213, 225))
    label_chip(base, "Chainflip · Nov. 21, 2026 · vault drain")
    return base, {"kind": "composite", "sources": [
        {"file": "chainflip-logo.png", "license": "Logo", "url": "https://www.coingecko.com/en/coins/chainflip", "credit": "Chainflip (logo via CoinGecko)"},
        {"file": "Ethereum tx 0xc928950f79b4e4697af674310d1f3a08c2659adc4d60e719f3af90ab023ff20f", "license": "Public blockchain data", "url": "https://eth.blockscout.com/tx/0xc928950f79b4e4697af674310d1f3a08c2659adc4d60e719f3af90ab023ff20f", "credit": "Blockscout"},
        {"file": "The Block / CoinDesk, Nov. 21, 2026", "license": "Figure cited", "url": "https://www.theblock.co/news/defi/2026-11-21-chainflips-flip-drops-34-after-attacker-drains-4-86-million-from-vault-with-suspected-key-compromise-444804", "credit": "The Block"},
    ], "note": "Editorial composite for identification; trademarks belong to their owners."}


def thumb_custodia_scotus():
    """U.S. Supreme Court building (Joe Ravi, CC BY-SA 3.0) with the Fed seal for identification."""
    court = fetch("https://upload.wikimedia.org/wikipedia/commons/d/da/Panorama_of_United_States_Supreme_Court_Building_at_Dusk.jpg", CACHE/"scotus-dusk.jpg")
    fed = fetch("https://upload.wikimedia.org/wikipedia/commons/7/73/Seal_of_the_United_States_Federal_Reserve_Board.svg", CACHE/"fed-seal.svg")
    base = cover_fit(open_rgb(court), cy=0.5)
    overlay = Image.new("RGBA", base.size, (0,0,0,0)); Draw(overlay).rectangle([0,int(H*0.70),W,H], fill=(8,14,28,200))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    tile = Image.new("RGBA", sz((96, 96)), (255,255,255,255))
    mask = Image.new("L", sz((96, 96)), 0); Draw(mask).ellipse([0,0,95,95], fill=255)
    base.paste(tile.convert("RGB"), sz((W-116, H-112)), mask)
    paste_contain(base, Image.open(fed).convert("RGBA"), (W-116, H-112, 96, 96), pad=6)
    d = Draw(base)
    d.text((20, H-84), "Certiorari denied", font=font(FONT_B, 30), fill=WHITE)
    d.text((22, H-44), "Custodia Bank v. Fed Board, No. 26-62", font=font(FONT_R, 17), fill=(203,213,225))
    label_chip(base, "Supreme Court · Fed master account")
    return base, {"kind":"composite","sources":[
        {"file":"Panorama_of_United_States_Supreme_Court_Building_at_Dusk.jpg","license":"CC BY-SA 3.0","url":"https://commons.wikimedia.org/wiki/File:Panorama_of_United_States_Supreme_Court_Building_at_Dusk.jpg","credit":"Joe Ravi / Wikimedia Commons"},
        {"file":"Seal_of_the_United_States_Federal_Reserve_Board.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Federal_Reserve_Board.svg","credit":"Federal Reserve Board"},
        {"file":"Supreme Court order list, Nov. 16, 2026","license":"Fact cited","url":"https://www.supremecourt.gov/orders/courtorders/111626zor_cb7d.pdf","credit":"Supreme Court of the United States"},
    ],"note":"Editorial composite; seal used for identification."}


def thumb_solana_1_0():
    """Solana logo (identification) with a SOL/USD daily chart from Kraken OHLC."""
    sol = fetch("https://cryptologos.cc/logos/solana-sol-logo.svg", CACHE/"solana-logo.svg")
    xs, closes = kraken_ohlc(1440, "SOLUSD")
    xs, closes = xs[-75:], closes[-75:]
    base = gradient_bg()
    tile = Image.new("RGBA", sz((170, 170)), (0,0,0,255))
    mask = Image.new("L", sz((170, 170)), 0); Draw(mask).rounded_rectangle([0,0,169,169], radius=18, fill=255)
    base.paste(tile.convert("RGB"), sz((36, 70)), mask)
    paste_contain(base, Image.open(sol).convert("RGBA"), (36, 70, 170, 170), pad=26)
    d = Draw(base)
    d.text((44, 262), "mainnet beta", font=font(FONT_R, 22), fill=MUTED)
    tw = d.textlength("mainnet beta", font=font(FONT_R, 22))
    d.line([(44, 276), (44+tw, 276)], fill=(248,113,113), width=3)
    d.text((44, 294), "→ Solana 1.0", font=font(FONT_B, 28), fill=ORANGE)
    fig, ax = plt.subplots(figsize=(3.4, 2.4), dpi=120); fig.patch.set_facecolor("#0f1419")
    style_ax(ax, "SOL/USD daily close (Kraken)")
    ax.plot(xs, closes, color="#f7931a", linewidth=1.8)
    ax.fill_between(xs, closes, min(closes)*0.97, color="#f7931a", alpha=0.12)
    ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b")); ax.yaxis.set_major_formatter(lambda v, _p: f"${v:,.0f}")
    chart = ImageOps.fit(chart_to_image(fig), sz((372, 262)), method=Image.Resampling.LANCZOS)
    base.paste(chart, sz((W-392, 58)))
    label_chip(base, "Solana · protocol version 1.0")
    return base, {"kind":"composite","sources":[
        {"file":"solana-sol-logo.svg","license":"Logo","url":"https://cryptologos.cc/solana","credit":"Solana Foundation"},
        {"file":"Kraken SOLUSD daily OHLC","license":"Public market data","url":"https://api.kraken.com/0/public/OHLC?pair=SOLUSD&interval=1440","credit":"Kraken"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_optimizely_clipper():
    """Optimizely wordmark (identification, cropped from optimizely.com's share image) with Report URI's count."""
    src = fetch("https://images3.cmp.optimizely.com/Zz1hOTU5MjFjNDY5MWYxMWYxOTU5NmZlODFjZDBjMWExMg==?width=1200", CACHE/"optimizely-og.png")
    logo = Image.open(src).convert("RGBA").crop((130, 200, 1060, 430))
    base = gradient_bg()
    card_w, card_h = 270, 170
    x, y = 40, 95
    tile = Image.new("RGBA", sz((card_w, card_h)), (228,240,218,255))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, card_w, card_h), pad=18)
    d = Draw(base)
    d.text((340, 96), "178", font=font(FONT_B, 72), fill=ORANGE)
    d.text((342, 190), "organizations' sites", font=font(FONT_B, 22), fill=WHITE)
    d.text((342, 222), "served wallet-address-", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((342, 246), "swapping code on Nov. 16", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Optimizely · supply-chain attack")
    return base, {"kind":"composite","sources":[
        {"file":"optimizely.com og:image","license":"Logo","url":"https://www.optimizely.com/","credit":"Optimizely (logo, identification only)"},
        {"file":"Report URI, Nov. 16, 2026","license":"Figure cited","url":"https://blog.report-uri.com/worlds-largest-brands-infected-with-malware-via-optimizely/","credit":"Report URI (Scott Helme)"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_coingecko_solana():
    """CoinGecko logo (cropped from coingecko.com's share image) and Solana logo, identification only."""
    src = fetch("https://static.coingecko.com/s/social_image_cards/social_image_card_standard-152325d6e2be21a5365b167d97eee4819d9565e232425c65ad47f3d2d7b2ea79.png", CACHE/"coingecko-og.png")
    cg = Image.open(src).convert("RGBA").crop((95, 125, 385, 200))
    sol = fetch("https://cryptologos.cc/logos/solana-sol-logo.svg", CACHE/"solana-logo.svg")
    base = gradient_bg()
    for (x, y, w, h, col, im, pad) in [(40, 70, 300, 120, (13,18,22,255), cg, 16), (40, 210, 300, 110, (0,0,0,255), Image.open(sol).convert("RGBA"), 22)]:
        tile = Image.new("RGBA", sz((w, h)), col)
        mask = Image.new("L", sz((w, h)), 0); Draw(mask).rounded_rectangle([0,0,w-1,h-1], radius=16, fill=255)
        base.paste(tile.convert("RGB"), sz((x, y)), mask)
        paste_contain(base, im, (x, y, w, h), pad=pad)
    d = Draw(base)
    d.text((372, 100), "18M", font=font(FONT_B, 72), fill=ORANGE)
    d.text((374, 192), "registered users", font=font(FONT_B, 22), fill=WHITE)
    d.text((374, 224), "majority interest, terms", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((374, 248), "not disclosed", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Solana Foundation · CoinGecko")
    return base, {"kind":"composite","sources":[
        {"file":"coingecko.com og:image","license":"Logo","url":"https://www.coingecko.com/","credit":"CoinGecko (logo, identification only)"},
        {"file":"solana-sol-logo.svg","license":"Logo","url":"https://cryptologos.cc/solana","credit":"Solana Foundation"},
        {"file":"Solana Foundation via CoinDesk, Nov. 17, 2026","license":"Figure cited","url":"https://www.coindesk.com/business/2026/11/17/solana-foundation-takes-majority-stake-in-crypto-data-provider-coingecko","credit":"CoinDesk"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}



def thumb_trezor_skladon():
    """Trezor logo mark (official favicon from trezor.io, identification only) with Trezor's order count."""
    src = fetch("https://trezor.io/favicon/android-chrome-512x512.png", CACHE/"trezor-512.png")
    logo = Image.open(src).convert("RGBA")
    base = gradient_bg()
    x, y, cw, ch = 40, 80, 220, 200
    tile = Image.new("RGBA", sz((cw, ch)), (255,255,255,255))
    mask = Image.new("L", sz((cw, ch)), 0); Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, cw, ch), pad=10)
    d = Draw(base)
    d.text((292, 96), "~27,000", font=font(FONT_B, 64), fill=ORANGE)
    d.text((294, 182), "orders exposed", font=font(FONT_B, 22), fill=WHITE)
    d.text((294, 214), "at shipping partner", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((294, 238), "Skladon (Aug. 9 to Nov. 7)", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Trezor · shipping data breach")
    return base, {"kind":"composite","sources":[
        {"file":"trezor.io android-chrome-512x512.png","license":"Logo","url":"https://trezor.io/","credit":"Trezor (logo, identification only)"},
        {"file":"Trezor blog, Nov. 16, 2026","license":"Figure cited","url":"https://trezor.io/blog/news/data-breach-at-trezor-shipping-partner-skladon","credit":"Trezor"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_coinbase_borrow_ny():
    """Coinbase icon (Wikimedia Commons) and Morpho logo (as listed on CoinGecko), identification only."""
    cb = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    mo = fetch("https://coin-images.coingecko.com/coins/images/29837/large/Morpho-token-icon.png", CACHE/"morpho-logo.png")
    base = gradient_bg()
    for (x, y, w, h, col, im, pad) in [(40, 70, 130, 130, (255,255,255,255), Image.open(cb).convert("RGBA"), 14), (190, 70, 130, 130, (255,255,255,255), Image.open(mo).convert("RGBA"), 18)]:
        tile = Image.new("RGBA", sz((w, h)), col)
        mask = Image.new("L", sz((w, h)), 0); Draw(mask).rounded_rectangle([0,0,w-1,h-1], radius=16, fill=255)
        base.paste(tile.convert("RGB"), sz((x, y)), mask)
        paste_contain(base, im, (x, y, w, h), pad=pad)
    d = Draw(base)
    d.text((44, 222), "Borrow USDC against BTC, ETH, SOL", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((44, 250), "New York added Nov. 16", font=font(FONT_B, 20), fill=WHITE)
    d.text((372, 82), "50", font=font(FONT_B, 96), fill=ORANGE)
    d.text((376, 196), "of 50 U.S. states", font=font(FONT_B, 22), fill=WHITE)
    label_chip(base, "Coinbase Borrow · Morpho on Base")
    return base, {"kind":"composite","sources":[
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
        {"file":"Morpho-token-icon.png","license":"Logo","url":"https://www.coingecko.com/en/coins/morpho","credit":"Morpho (logo, identification only)"},
        {"file":"The Block / Coinbase, Nov. 16-17, 2026","license":"Fact cited","url":"https://www.theblock.co/news/business/2026-11-17-coinbase-borrow-new-york-morpho-442842","credit":"The Block"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}



def thumb_cftc_backpack():
    """CFTC seal (public domain, Wikimedia Commons) and Backpack logo mark (official favicon, identification only)."""
    cftc = fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Commodity_Futures_Trading_Commission_seal.svg", CACHE/"cftc-seal.svg")
    bp = fetch("https://backpack.exchange/favicon/favicon-bb988748.svg", CACHE/"backpack-favicon.svg")
    base = gradient_bg()
    paste_contain(base, Image.open(cftc).convert("RGBA"), (34, 62, 210, 210), pad=6)
    x, y, cw, ch = 262, 92, 150, 150
    tile = Image.new("RGBA", sz((cw, ch)), (255,255,255,255))
    mask = Image.new("L", sz((cw, ch)), 0); Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(bp).convert("RGBA"), (x, y, cw, ch), pad=18)
    d = Draw(base)
    d.text((440, 104), "DCM", font=font(FONT_B, 40), fill=ORANGE)
    d.text((440, 156), "+ DCO", font=font(FONT_B, 40), fill=ORANGE)
    d.text((440, 214), "Nov. 13-16", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((44, 300), "Exchange + clearinghouse approvals for blockchain-based derivatives", font=font(FONT_R, 16), fill=(203,213,225))
    label_chip(base, "CFTC · Backpack · tZERO")
    return base, {"kind":"composite","sources":[
        {"file":"Commodity_Futures_Trading_Commission_seal.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Commodity_Futures_Trading_Commission_seal.svg","credit":"CFTC"},
        {"file":"backpack.exchange favicon.svg","license":"Logo","url":"https://backpack.exchange/","credit":"Backpack (logo, identification only)"},
        {"file":"CFTC statement and orders, Nov. 13-16, 2026","license":"Fact cited","url":"https://www.cftc.gov/PressRoom/SpeechesTestimony/seligstatement111626","credit":"CFTC"},
    ],"note":"Editorial composite for identification; no endorsement by the CFTC implied; trademarks belong to their owners."}


def thumb_banks_btc_etf_13f():
    """Goldman Sachs and Wells Fargo logos (Wikimedia Commons, public domain) with 13F figures (Sept. 30, 2026)."""
    gs = fetch("https://upload.wikimedia.org/wikipedia/commons/6/61/Goldman_Sachs.svg", CACHE/"goldman-sachs.svg")
    wf = fetch("https://upload.wikimedia.org/wikipedia/commons/b/b3/Wells_Fargo_Bank.svg", CACHE/"wells-fargo.svg")
    base = gradient_bg()
    d = Draw(base)
    for (x, im, big, sub) in [(40, gs, "$1.28B", "bitcoin ETFs (Goldman)"), (340, wf, "$2.35B", "IBIT (Wells Fargo)")]:
        cw, ch = 130, 130
        tile = Image.new("RGBA", sz((cw, ch)), (255,255,255,255))
        mask = Image.new("L", sz((cw, ch)), 0); Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=16, fill=255)
        base.paste(tile.convert("RGB"), sz((x, 70)), mask)
        paste_contain(base, Image.open(im).convert("RGBA"), (x, 70, cw, ch), pad=14)
        d = Draw(base)
        d.text((x, 216), big, font=font(FONT_B, 46), fill=ORANGE)
        d.text((x + 2, 272), sub, font=font(FONT_R, 18), fill=(203,213,225))
    d.text((44, 316), "13F filings, holdings as of Sept. 30, 2026", font=font(FONT_R, 15), fill=(148,163,184))
    label_chip(base, "Wall Street banks · bitcoin ETF 13Fs")
    return base, {"kind":"composite","sources":[
        {"file":"Goldman_Sachs.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Goldman_Sachs.svg","credit":"Goldman Sachs"},
        {"file":"Wells_Fargo_Bank.svg","license":"Public domain (logo)","url":"https://commons.wikimedia.org/wiki/File:Wells_Fargo_Bank.svg","credit":"Wells Fargo"},
        {"file":"Bitcoin Magazine / CoinDesk, Nov. 17, 2026","license":"Figures cited","url":"https://bitcoinmagazine.com/news/goldman-sachs-bitcoin-etf-holdings","credit":"Bitcoin Magazine, CoinDesk"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_russia_retail_crypto():
    """Flag of Russia (public domain, Wikimedia Commons) with Bitcoin logo (public domain) and the Bank of Russia cap."""
    flag = fetch("https://upload.wikimedia.org/wikipedia/commons/f/f3/Flag_of_Russia.svg", CACHE/"flag-russia.svg")
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")
    base = gradient_bg()
    fl = Image.open(flag).convert("RGB").resize(sz((210, 140)))
    base.paste(fl, sz((40, 74)))
    disc = Image.new("RGBA", sz((140, 140)), (0, 0, 0, 0))
    Draw(disc).ellipse([0, 0, 139, 139], fill=(255, 255, 255, 255))
    base.paste(disc.convert("RGB"), sz((210, 150)), disc)
    paste_contain(base, Image.open(btc).convert("RGBA"), (210, 150, 140, 140), pad=16)
    d = Draw(base)
    d.text((384, 84), "\u20bd300K", font=font(FONT_B, 60), fill=ORANGE)
    d.text((386, 160), "per year, per intermediary", font=font(FONT_R, 17), fill=(203,213,225))
    d.text((386, 200), "BTC \u00b7 ETH \u00b7 USDT", font=font(FONT_B, 24), fill=WHITE)
    d.text((386, 236), "from Nov. 17, 2026", font=font(FONT_R, 17), fill=(203,213,225))
    d.text((44, 316), "Ordinary investors must pass a knowledge test first", font=font(FONT_R, 16), fill=(148,163,184))
    label_chip(base, "Bank of Russia \u00b7 retail crypto rules")
    return base, {"kind":"composite","sources":[
        {"file":"Flag_of_Russia.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Flag_of_Russia.svg","credit":"Flag of Russia"},
        {"file":"Bitcoin.svg","license":"Public domain","url":"https://commons.wikimedia.org/wiki/File:Bitcoin.svg","credit":"Bitcoin logo"},
        {"file":"Bank of Russia press release, Nov. 6, 2026","license":"Fact cited","url":"https://www.cbr.ru/eng/press/event/?id=32966","credit":"Bank of Russia"},
    ],"note":"Editorial composite; no endorsement implied; trademarks belong to their owners."}


def thumb_mev_acquittal():
    """Ethereum logo (CC BY 3.0, Wikimedia Commons) with case figures from the court opinion as reported by CoinDesk."""
    eth = fetch("https://upload.wikimedia.org/wikipedia/commons/0/05/Ethereum_logo_2014.svg", CACHE/"ethereum-logo-2014.svg")
    base = gradient_bg()
    disc = Image.new("RGBA", sz((200, 200)), (0, 0, 0, 0))
    Draw(disc).ellipse([0, 0, 199, 199], fill=(255, 255, 255, 255))
    base.paste(disc.convert("RGB"), sz((50, 76)), disc)
    paste_contain(base, Image.open(eth).convert("RGBA"), (50, 76, 200, 200), pad=26)
    d = Draw(base)
    d.text((300, 80), "$25M", font=font(FONT_B, 72), fill=ORANGE)
    d.text((304, 170), "from trading bots in 12 seconds", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((304, 212), "Acquitted", font=font(FONT_B, 34), fill=WHITE)
    d.text((304, 258), "Federal judge, Nov. 16, 2026", font=font(FONT_R, 17), fill=(203,213,225))
    d.text((44, 318), "First U.S. criminal case over an MEV exploit", font=font(FONT_R, 16), fill=(148,163,184))
    label_chip(base, "Ethereum \u00b7 MEV court ruling")
    return base, {"kind":"composite","sources":[
        {"file":"Ethereum_logo_2014.svg","license":"CC BY 3.0","url":"https://commons.wikimedia.org/wiki/File:Ethereum_logo_2014.svg","credit":"Ethereum Foundation"},
        {"file":"CoinDesk, Nov. 18, 2026","license":"Figures cited","url":"https://www.coindesk.com/policy/2026/11/18/u-s-judge-says-ethereum-has-no-terms-of-use-clears-mit-brothers-of-usd25-million-fraud","credit":"CoinDesk"},
    ],"note":"Editorial composite; trademarks belong to their owners."}


def thumb_fed_minutes_btc_63k():
    """Federal Reserve seal (public domain) with the fed funds range from the Oct. 27-28, 2026 minutes."""
    fed = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1a/Seal_of_the_United_States_Federal_Reserve_System.svg", CACHE/"fed-seal.svg")
    base = gradient_bg()
    paste_contain(base, Image.open(fed).convert("RGBA"), (36, 70, 200, 200), pad=6)
    d = Draw(base)
    d.text((262, 88), "3.75-4%", font=font(FONT_B, 58), fill=ORANGE)
    d.text((264, 166), "Fed rate range, held Oct. 28", font=font(FONT_B, 19), fill=WHITE)
    d.text((264, 200), "Minutes: almost all officials", font=font(FONT_R, 17), fill=(203,213,225))
    d.text((264, 224), "see more hikes as likely", font=font(FONT_R, 17), fill=(203,213,225))
    label_chip(base, "Federal Reserve · FOMC minutes")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Federal_Reserve_System.svg","license":"Public domain (U.S. government insignia)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Federal_Reserve_System.svg","credit":"Federal Reserve"},
        {"file":"FOMC minutes, Oct. 27-28, 2026","license":"Fact cited","url":"https://www.federalreserve.gov/monetarypolicy/fomcminutes20261028.htm","credit":"Federal Reserve"},
    ],"note":"Editorial composite for identification; no endorsement by the Federal Reserve implied."}


def thumb_binance_adgm_order():
    """Binance logo (identification) with the frozen amount from Binance's incident report (via Reuters)."""
    binance = fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")
    base = gradient_bg()
    card_w, card_h = 200, 190
    x, y = 46, 84
    tile = Image.new("RGBA", sz((card_w, card_h)), (26,35,50,235))
    mask = Image.new("L", sz((card_w, card_h)), 0); Draw(mask).rounded_rectangle([0,0,card_w-1,card_h-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(binance).convert("RGBA"), (x, y, card_w, card_h), pad=22)
    d = Draw(base)
    d.text((278, 96), "$2.85B", font=font(FONT_B, 64), fill=ORANGE)
    d.text((280, 186), "frozen or intercepted", font=font(FONT_B, 21), fill=WHITE)
    d.text((280, 220), "Abu Dhabi court order", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((280, 244), "to help recover it", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Binance · hack recovery")
    return base, {"kind":"composite","sources":[
        {"file":"Binance_Logo.svg","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Binance_Logo.svg","credit":"Binance"},
        {"file":"Reuters, Nov. 18, 2026","license":"Figure cited","url":"https://www.investing.com/news/economy-news/binance-says-it-has-court-order-to-get-back-crypto-frozen-after-63-billion-heist-5036806","credit":"Reuters / Binance"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_ledger_berlin_dubai():
    """Ledger mark (official favicon from ledger.com, identification only) with the locations from Ledger's Nov. 18 update."""
    src = fetch("https://ledger-wp-website-s3-prd.ledger.com/uploads/2021/11/Ledger_favicon.png", CACHE/"ledger-favicon.png")
    logo = Image.open(src).convert("RGBA")
    base = gradient_bg()
    x, y, cw, ch = 40, 84, 200, 190
    tile = Image.new("RGBA", sz((cw, ch)), (255,255,255,255))
    mask = Image.new("L", sz((cw, ch)), 0); Draw(mask).rounded_rectangle([0,0,cw-1,ch-1], radius=16, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, logo, (x, y, cw, ch), pad=34)
    d = Draw(base)
    d.text((272, 92), "Berlin", font=font(FONT_B, 54), fill=ORANGE)
    d.text((272, 156), "+ 2 suspected in Dubai", font=font(FONT_B, 22), fill=WHITE)
    d.text((274, 196), "Tampered wallets built to", font=font(FONT_R, 18), fill=(203,213,225))
    d.text((274, 220), "capture recovery phrases", font=font(FONT_R, 18), fill=(203,213,225))
    label_chip(base, "Ledger · hardware implant probe")
    return base, {"kind":"composite","sources":[
        {"file":"ledger.com Ledger_favicon.png","license":"Logo","url":"https://www.ledger.com/","credit":"Ledger (logo, identification only)"},
        {"file":"Ledger support update, Nov. 18, 2026 (via Decrypt)","license":"Fact cited","url":"https://decrypt.co/383586/ledger-confirms-tampered-bitcoin-wallets-berlin-spreads-beyond-asia","credit":"Ledger / Decrypt"},
    ],"note":"Editorial composite for identification; trademarks belong to their owners."}


def thumb_genius_state_safe_harbor():
    """U.S. Treasury seal (public domain) with the GENIUS Act start date and state issuer threshold."""
    seal = fetch("https://upload.wikimedia.org/wikipedia/commons/c/cb/Seal_of_the_United_States_Department_of_the_Treasury.svg", CACHE/"treasury-seal.svg")
    base = gradient_bg()
    paste_contain(base, Image.open(seal).convert("RGBA"), (36, 70, 200, 200), pad=6)
    d = Draw(base)
    d.text((262, 88), "6 senators", font=font(FONT_B, 54), fill=ORANGE)
    d.text((264, 160), "ask Treasury for a state", font=font(FONT_B, 20), fill=WHITE)
    d.text((264, 188), "stablecoin safe harbor", font=font(FONT_B, 20), fill=WHITE)
    d.text((264, 224), "GENIUS Act starts Jan. 18, 2027", font=font(FONT_R, 17), fill=(203,213,225))
    label_chip(base, "GENIUS Act · stablecoins")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Department_of_the_Treasury.svg","license":"Public domain (U.S. government insignia)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Department_of_the_Treasury.svg","credit":"U.S. Department of the Treasury"},
        {"file":"Sen. Lummis press release, Nov. 18, 2026","license":"Fact cited","url":"https://www.lummis.senate.gov/press-releases/lummis-gillibrand-colleagues-urge-treasury-to-give-state-stablecoin-issuers-equal-footing-with-federal-issuers/","credit":"Office of Sen. Cynthia Lummis"},
    ],"note":"Editorial composite for identification; no endorsement by the U.S. Treasury implied."}


def thumb_threat_disruption_center():
    """DHS seal (public domain) with FBI IC3 2025 loss figure."""
    seal = fetch("https://upload.wikimedia.org/wikipedia/commons/8/8a/Seal_of_the_United_States_Department_of_Homeland_Security.svg", CACHE/"dhs-seal.svg")
    base = gradient_bg()
    paste_contain(base, Image.open(seal).convert("RGBA"), (36, 70, 200, 200), pad=6)
    d = Draw(base)
    d.text((262, 88), "$20.9B", font=font(FONT_B, 54), fill=ORANGE)
    d.text((264, 160), "lost to cybercrime in 2025,", font=font(FONT_B, 20), fill=WHITE)
    d.text((264, 188), "FBI's IC3 reports", font=font(FONT_B, 20), fill=WHITE)
    d.text((264, 224), "New center: 30+ agencies, 440+ partners", font=font(FONT_R, 16), fill=(203,213,225))
    label_chip(base, "DHS · DOJ · Threat Disruption Center")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Department_of_Homeland_Security.svg","license":"Public domain (U.S. government insignia)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Department_of_Homeland_Security.svg","credit":"U.S. Department of Homeland Security"},
        {"file":"FBI 2025 Internet Crime Report; HSTF press release, Nov. 18, 2026","license":"Facts cited","url":"https://www.hstf.gov/press/threat-disruption-center/","credit":"FBI IC3 / Homeland Security Task Force"},
    ],"note":"Editorial composite for identification; no endorsement by DHS implied."}


def thumb_sky_psm_illicit():
    """Generated flow graphic: USDC -> Sky PSM -> DAI/USDS with the Inca Digital figures (via CoinDesk)."""
    base = gradient_bg()
    d = Draw(base)
    def box(x, y, w, h, title, sub, col):
        d.rounded_rectangle([x, y, x+w, y+h], radius=14, fill=(20, 32, 60), outline=col, width=3)
        tw = d.textlength(title, font=font(FONT_B, 26))
        d.text((x + (w - tw)/2, y + 18), title, font=font(FONT_B, 26), fill=WHITE)
        sw = d.textlength(sub, font=font(FONT_R, 14))
        d.text((x + (w - sw)/2, y + 56), sub, font=font(FONT_R, 14), fill=(203,213,225))
    box(24, 70, 160, 90, "USDC", "freezable", (96,165,250))
    box(234, 70, 160, 90, "Sky PSM", "1:1 swap", ORANGE)
    box(444, 70, 176, 90, "DAI/USDS", "not freezable", (52,211,153))
    for x0 in (188, 398):
        d.line([(x0, 115), (x0+40, 115)], fill=WHITE, width=4)
        d.polygon([(x0+40, 107), (x0+40, 123), (x0+46, 115)], fill=WHITE)
    d.text((30, 196), "$518M", font=font(FONT_B, 54), fill=ORANGE)
    d.text((250, 204), "flagged, $101.9M tied", font=font(FONT_B, 19), fill=WHITE)
    d.text((250, 232), "to North Korea (Inca Digital)", font=font(FONT_B, 19), fill=WHITE)
    d.text((32, 276), "Reserve at risk of a freeze: about $2.7B in USDC", font=font(FONT_R, 17), fill=(203,213,225))
    label_chip(base, "Sky · stablecoin swap module")
    return base, {"kind":"generated","sources":[
        {"file":"Inca Digital report via CoinDesk, Nov. 19, 2026","license":"Facts cited","url":"https://www.coindesk.com/business/2026/11/19/north-korean-hackers-used-sky-s-stablecoin-system-putting-billions-at-freeze-risk","credit":"Inca Digital / CoinDesk"},
    ],"note":"PlainBTC-generated diagram; no logos or photos used."}



def thumb_btc_below_62k_july():
    """Paper-style chart: Kraken XBTUSD daily closes Jun 15 - Nov 19, 2026 and the Nov 19 intraday low ($61,353.20)."""
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = next(v for k, v in json.load(r)["result"].items() if k != "last")
    start = datetime(2026, 6, 15, tzinfo=timezone.utc); end = datetime(2026, 11, 20, tzinfo=timezone.utc)
    pts = [(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[4]), float(r[3])) for r in rows]
    pts = [p for p in pts if start <= p[0] < end]
    xs, closes = [p[0] for p in pts], [p[1] for p in pts]
    low_x, low_v = pts[-1][0], pts[-1][2]          # Nov 19 (UTC) daily low
    paper, ink = "#f6f1e7", "#1c1917"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(paper)
    ax = fig.add_axes([0.06, 0.12, 0.90, 0.52]); ax.set_facecolor(paper)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#a8a29e")
    ax.tick_params(colors="#57534e", labelsize=7, length=0)
    ax.grid(True, axis="y", color="#d6d3d1", linewidth=0.6)
    ax.plot(xs, closes, color="#f7931a", linewidth=2.2)
    ax.fill_between(xs, closes, min(closes + [low_v]) * 0.96, color="#f7931a", alpha=0.10)
    ax.axhline(low_v, color="#b91c1c", linestyle=(0, (4, 3)), linewidth=1.0)
    ax.scatter([low_x], [low_v], s=38, color="#b91c1c", zorder=5, edgecolors="white", linewidths=1.2)
    ax.set_ylim(min(closes + [low_v]) * 0.96, max(closes) * 1.03)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.text(0.06, 0.86, "$61,353", color="#b91c1c", fontsize=30, fontweight="bold", va="center")
    fig.text(0.42, 0.89, "Bitcoin low on Kraken, Nov. 19", color=ink, fontsize=11, fontweight="bold", va="center")
    fig.text(0.42, 0.81, "lowest price since July 6, 2026", color="#57534e", fontsize=10, va="center")
    fig.text(0.06, 0.70, "Daily close since mid-June", color="#78716c", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=paper); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Daily BTC/USD closes Jun 15 - Nov 19, 2026 and the Nov 19 low, from Kraken"}
    ]}


def thumb_coinbase_options_intl():
    """Coinbase icon (Wikimedia Commons, identification) on Coinbase blue, an illustrative option payoff line, and the six launch assets."""
    cb = fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")
    base = Image.new("RGB", sz((W, H)), (0, 82, 255))
    d = Draw(base)
    # tile with the Coinbase icon
    w = h = 116; x, y = 40, 46
    tile = Image.new("RGBA", sz((w, h)), (255, 255, 255, 255))
    mask = Image.new("L", sz((w, h)), 0); Draw(mask).rounded_rectangle([0, 0, w-1, h-1], radius=22, fill=255)
    base.paste(tile.convert("RGB"), sz((x, y)), mask)
    paste_contain(base, Image.open(cb).convert("RGBA"), (x, y, w, h), pad=14)
    d.text((176, 58), "Crypto options", font=font(FONT_B, 34), fill=WHITE)
    d.text((178, 104), "live outside the U.S. · settled in USDC", font=font(FONT_R, 17), fill=(219, 234, 254))
    d.text((178, 130), "powered by Deribit", font=font(FONT_R, 17), fill=(219, 234, 254))
    # illustrative long-call payoff ("hockey stick"), no numbers
    ox, oy = 420, 300
    d.line([(ox - 10, oy), (ox + 190, oy)], fill=(147, 197, 253), width=1)
    d.line([(ox, oy - 14), (ox + 90, oy - 14), (ox + 180, oy - 104)], fill=WHITE, width=4, joint="curve")
    d.text((ox, oy + 8), "call option payoff (illustration)", font=font(FONT_R, 11), fill=(191, 219, 254))
    # six asset pills
    px, py = 40, 200
    for i, sym in enumerate(["BTC", "ETH", "SOL", "AVAX", "HYPE", "XRP"]):
        f = font(FONT_B, 17); tw = d.textlength(sym, font=f)
        cx = px + (i % 3) * 112; cy = py + (i // 3) * 50
        d.rounded_rectangle([cx, cy, cx + 100, cy + 38], radius=19, fill=(255, 255, 255))
        d.text((cx + (100 - tw) / 2, cy + 9), sym, font=f, fill=(0, 52, 170))
    label_chip(base, "Coinbase · options via Deribit", xy=(16, 18))
    return base, {"kind":"composite","sources":[
        {"file":"Coinbase_Icon.png","license":"Logo","url":"https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png","credit":"Coinbase"},
        {"file":"Coinbase on X, Nov. 19, 2026","license":"Fact cited","url":"https://x.com/coinbase/status/2123416234373067020","credit":"Coinbase"},
        {"file":"crypto.news, Nov. 19, 2026","license":"Fact cited","url":"https://crypto.news/coinbase-crypto-options-non-us-traders/","credit":"crypto.news (six assets, USDC settlement)"},
    ],"note":"Editorial composite for identification; payoff line is a generic illustration; trademarks belong to their owners."}



def thumb_ibit_record_outflow():
    """Black horizontal-bar ranking of IBIT's five largest daily net outflows (Farside Investors, read Nov 20, 2026)."""
    rows = [("Nov 14, 2025", 463.1), ("Nov 18, 2025", 523.2), ("May 27, 2026", 527.8), ("Jan 30, 2026", 528.3), ("Nov 19, 2026", 541.1)]
    bg, ink = "#070707", "#f5f5f4"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.25, 0.08, 0.62, 0.50]); ax.set_facecolor(bg)
    labels = [r[0] for r in rows]; vals = [r[1] for r in rows]
    cols = ["#57534e"] * 4 + ["#ef4444"]
    ax.barh(labels, vals, color=cols, height=0.62)
    for i, v in enumerate(vals):
        ax.text(v + 6, i, f"-${v:,.1f}M", va="center", color=ink if i == 4 else "#a8a29e",
                fontsize=9 if i == 4 else 8, fontweight="bold" if i == 4 else "normal")
    ax.set_xlim(0, 640)
    for s in ("top", "right", "bottom"): ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#44403c")
    ax.tick_params(axis="y", colors="#d6d3d1", labelsize=8, length=0)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    ax.get_yticklabels()[-1].set_color("#fca5a5"); ax.get_yticklabels()[-1].set_fontweight("bold")
    fig.text(0.05, 0.84, "-$541.1M", color="#ef4444", fontsize=34, fontweight="bold", va="center")
    fig.text(0.53, 0.88, "BlackRock IBIT, Nov. 19, 2026", color=ink, fontsize=11, fontweight="bold", va="center")
    fig.text(0.53, 0.80, "biggest one-day outflow since launch", color="#a8a29e", fontsize=9.5, va="center")
    fig.text(0.05, 0.66, "IBIT's five largest daily net outflows", color="#78716c", fontsize=8, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind":"chart","sources":[
        {"file":"Farside Investors Bitcoin ETF Flow - All Data","license":"Public data, cited","url":"https://farside.co.uk/bitcoin-etf-flow-all-data/","credit":"IBIT daily net flows since Jan 2024, from Farside Investors (read Nov 20, 2026)"}
    ]}


def thumb_sec_fake_platforms():
    """Generated scam-chain graphic with the SEC seal (public domain) and the complaint's totals."""
    sec = fetch("https://upload.wikimedia.org/wikipedia/commons/1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", CACHE/"sec-seal.svg")
    base = gradient_bg(top=(69, 10, 10), bottom=(24, 8, 12))
    d = Draw(base)
    paste_contain(base, Image.open(sec).convert("RGBA"), (536, 18, 88, 88), pad=2)
    d.text((28, 70), "$37.4M", font=font(FONT_B, 58), fill=(254, 202, 202))
    d.text((32, 140), "taken from 1,500+ U.S. investors, the SEC says", font=font(FONT_B, 17), fill=WHITE)
    steps = [("Social ad", (96,165,250)), ("WhatsApp chat", (52,211,153)), ("Fake adviser", ORANGE), ("Fake crypto app", (248,113,113))]
    x, y, bw, bh, gap = 24, 214, 128, 64, 22
    for i, (t, col) in enumerate(steps):
        x0 = x + i * (bw + gap)
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=12, fill=(30, 12, 18), outline=col, width=3)
        f = font(FONT_B, 15)
        words = t.split(" ")
        lines = [t] if d.textlength(t, font=f) < bw - 14 else [words[0], " ".join(words[1:])]
        for j, ln in enumerate(lines):
            tw = d.textlength(ln, font=f)
            d.text((x0 + (bw - tw) / 2, y + bh / 2 - 9 * len(lines) + j * 19), ln, font=f, fill=WHITE)
        if i < 3:
            ax0 = x0 + bw + 3
            d.line([(ax0, y + bh / 2), (ax0 + gap - 9, y + bh / 2)], fill=(254, 202, 202), width=3)
            d.polygon([(ax0 + gap - 9, y + bh / 2 - 6), (ax0 + gap - 9, y + bh / 2 + 6), (ax0 + gap - 3, y + bh / 2)], fill=(254, 202, 202))
    d.text((26, 300), "A fee was demanded to withdraw, then the sites and chats went dark", font=font(FONT_R, 14), fill=(252, 165, 165))
    label_chip(base, "SEC complaint · Aug. 2024 - May 2026")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","license":"Public domain (U.S. government)","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Securities_and_Exchange_Commission.svg","credit":"SEC"},
        {"file":"SEC press release 2026-115 and complaint, Nov. 19, 2026","license":"Facts cited","url":"https://www.sec.gov/newsroom/press-releases/2026-115-sec-eight-entities-used-fake-crypto-asset-trading-platforms-steal-more-37-million-us-investors","credit":"U.S. Securities and Exchange Commission"},
    ],"note":"Editorial graphic; no endorsement by the SEC implied."}



def thumb_btc_below_59k_2026_low():
    """Crimson full-year chart: Kraken XBTUSD daily closes Jan 1 - Nov 19, 2026, the 2026 low line ($57,740, Jul 1) and the Nov 20 intraday low ($58,005.00)."""
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = next(v for k, v in json.load(r)["result"].items() if k != "last")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc); end = datetime(2026, 11, 20, tzinfo=timezone.utc)
    pts = [(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[4])) for r in rows]
    pts = [p for p in pts if start <= p[0] < end]
    xs, closes = [p[0] for p in pts], [p[1] for p in pts]
    year_low, low_now, x_now = 57740.0, 58005.0, datetime(2026, 11, 20, 18, tzinfo=timezone.utc)
    bg, ink = "#3b0a12", "#fff7ed"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.07, 0.12, 0.89, 0.50]); ax.set_facecolor(bg)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#9f5f68")
    ax.tick_params(colors="#fecdd3", labelsize=7, length=0)
    ax.grid(True, axis="y", color="#5b1a24", linewidth=0.6)
    ax.plot(xs + [x_now], closes + [low_now], color=ink, linewidth=1.8)
    ax.axhline(year_low, color="#fb923c", linestyle=(0, (4, 3)), linewidth=1.1)
    ax.text(datetime(2026, 1, 8, tzinfo=timezone.utc), year_low * 1.025, "2026 low $57,740 (Jul 1)", color="#fb923c", fontsize=7.5, fontweight="bold")
    ax.scatter([x_now], [low_now], s=40, color="#f87171", zorder=5, edgecolors="white", linewidths=1.2)
    ax.set_ylim(year_low * 0.95, max(closes) * 1.04)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.text(0.07, 0.86, "$58,005", color="#fca5a5", fontsize=30, fontweight="bold", va="center")
    fig.text(0.46, 0.89, "Bitcoin low on Kraken, Nov. 20", color=ink, fontsize=11, fontweight="bold", va="center")
    fig.text(0.46, 0.81, "less than 0.5% above the 2026 low", color="#fecdd3", fontsize=10, va="center")
    fig.text(0.07, 0.70, "Daily close, 2026", color="#fda4af", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440 and interval=60","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Daily BTC/USD closes Jan 1 - Nov 19, 2026, the Jul 1 low and the Nov 20 low, from Kraken"}
    ]}


def thumb_btc_new_2026_low():
    """Violet 'price ladder': the previous 2026 low ($57,740 on Kraken, Jul 1) vs the new Nov 20 low ($57,661.10, 1:26 p.m. CST), plus MSTR and Nasdaq daily moves (Yahoo Finance closes)."""
    base = gradient_bg(top=(46, 16, 101), bottom=(15, 10, 30))
    d = Draw(base)
    d.text((30, 50), "$57,661", font=font(FONT_B, 66), fill=(251, 191, 36))
    d.text((34, 136), "Bitcoin's new 2026 low on Kraken", font=font(FONT_B, 18), fill=WHITE)
    d.text((34, 162), "Nov. 20, 2026 · 1:26 p.m. Central time", font=font(FONT_R, 14), fill=(221, 214, 254))
    # previous low: dashed line
    y1, y2 = 214, 268
    x = 30
    while x < 600:
        d.line([(x, y1), (min(x + 14, 600), y1)], fill=(167, 139, 250), width=3); x += 22
    d.text((30, y1 - 24), "Previous low · July 1 · $57,740", font=font(FONT_R, 14), fill=(196, 181, 253))
    d.line([(30, y2), (600, y2)], fill=(251, 191, 36), width=5)
    d.text((30, y2 + 8), "New low · Nov. 20 · $57,661", font=font(FONT_B, 15), fill=(253, 230, 138))
    # down arrow between the two levels
    ax = 560
    d.line([(ax, y1 + 6), (ax, y2 - 12)], fill=(248, 113, 113), width=4)
    d.polygon([(ax - 9, y2 - 16), (ax + 9, y2 - 16), (ax, y2 - 4)], fill=(248, 113, 113))
    d.text((ax - 118, (y1 + y2) // 2 - 9), "−$78.90", font=font(FONT_B, 15), fill=(254, 202, 202))
    f = font(FONT_B, 14); px = 30
    for t in ("Strategy (MSTR) −9.7%", "Nasdaq −5.3%"):
        w = d.textlength(t, font=f) + 26
        d.rounded_rectangle([px, 306, px + w, 336], radius=15, fill=(40, 12, 24), outline=(248, 113, 113), width=2)
        d.text((px + 13, 313), t, font=f, fill=(254, 226, 226)); px += w + 12
    label_chip(base, "Bitcoin · new 2026 low")
    return base, {"kind":"diagram","sources":[
        {"file":"Kraken OHLC XBTUSD interval=1440 and interval=1","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Jul 1 and Nov 20, 2026 daily lows and the 1:26 p.m. CST minute low, from Kraken"},
        {"file":"MSTR and ^IXIC daily closes Nov 19-20, 2026","license":"Public market data, cited","url":"https://finance.yahoo.com/quote/MSTR/","credit":"Yahoo Finance"}
    ]}


def thumb_abraxas_withdrawals():
    """Emerald 'flow' diagram: 17,597 BTC (about $1.04B, average $59,206) withdrawn from Binance and Kraken
    to wallets Arkham labels Abraxas Capital / Heka Funds (Lookonchain, Nov. 22, 2026), plus Kraken's Sunday high."""
    base = gradient_bg(top=(6, 78, 59), bottom=(4, 20, 18))
    d = Draw(base)
    d.text((30, 52), "17,597 BTC", font=font(FONT_B, 58), fill=(110, 231, 183))
    d.text((34, 128), "moved off two exchanges in about a day", font=font(FONT_B, 17), fill=WHITE)
    d.text((34, 153), "≈ $1.04 billion · average price $59,206 · Lookonchain", font=font(FONT_R, 13), fill=(167, 243, 208))
    # exchanges -> wallet flow
    fb = font(FONT_B, 17)
    for i, name in enumerate(("Binance", "Kraken")):
        y = 200 + i * 62
        d.rounded_rectangle([30, y, 190, y + 44], radius=12, fill=(6, 40, 34), outline=(52, 211, 153), width=2)
        tw = d.textlength(name, font=fb); d.text((110 - tw / 2, y + 12), name, font=fb, fill=WHITE)
        # arrow
        ay = y + 22; ty = 253
        d.line([(196, ay), (380, ty)], fill=(247, 147, 26), width=4)
    d.polygon([(372, 241), (396, 253), (372, 265)], fill=(247, 147, 26))
    d.rounded_rectangle([400, 214, 610, 292], radius=14, fill=(15, 23, 42), outline=(247, 147, 26), width=3)
    d.text((416, 226), "Wallets Arkham labels", font=font(FONT_R, 13), fill=(203, 213, 225))
    d.text((416, 246), "Abraxas Capital", font=font(FONT_B, 18), fill=WHITE)
    d.text((416, 270), "(Heka Funds)", font=font(FONT_R, 12), fill=(203, 213, 225))
    d.text((30, 322), "Bitcoin on Kraken: Sunday high $61,590 (6:15 a.m. CT)", font=font(FONT_B, 13), fill=(253, 230, 138))
    label_chip(base, "On-chain · whale withdrawals")
    return base, {"kind":"diagram","sources":[
        {"file":"Lookonchain feed 83499 / Arkham entity abraxas-capital-heka-funds","license":"Figures cited","url":"https://www.lookonchain.com/feeds/83499","credit":"17,597 BTC, $1.04B, average $59,206, Binance and Kraken: Lookonchain (Arkham Intelligence labels)"},
        {"file":"Kraken OHLC XBTUSD interval=15","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"Nov. 22, 2026 high $61,590 at 6:15 a.m. CST, from Kraken"}
    ]}


def thumb_btc_55100_rebound():
    """Graphite 'V' chart: Kraken XBTUSD 15-minute closes Nov 20 6 p.m. - Nov 21 8 a.m. CST (frozen in chart-data.json),
    the overnight low ($55,100 at 12:17 a.m. CST) and the morning high ($60,883.40 at 8:03 a.m. CST)."""
    rows = json.loads((I18N / "bitcoin-crashes-to-55100-rebounds-above-60000-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    t0 = datetime(2026, 11, 21, 0, tzinfo=timezone.utc).timestamp()          # Nov 20 6 p.m. CST
    pts = [(datetime.fromtimestamp(r[0] - 6 * 3600, tz=timezone.utc), r[1]) for r in rows if r[0] >= t0]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    low_x, low_v = datetime(2026, 11, 21, 0, 17, tzinfo=timezone.utc), 55100.0     # CST wall-clock on a UTC axis
    hi_x, hi_v = datetime(2026, 11, 21, 8, 3, tzinfo=timezone.utc), 60883.4
    xs2, ys2 = xs[:], ys[:]
    for x, v in ((low_x, low_v), (hi_x, hi_v)):
        i = next((k for k, xx in enumerate(xs2) if xx > x), len(xs2)); xs2.insert(i, x); ys2.insert(i, v)
    bg, ink, teal = "#141414", "#fafafa", "#2dd4bf"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.07, 0.12, 0.89, 0.50]); ax.set_facecolor(bg)
    for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#525252")
    ax.tick_params(colors="#a3a3a3", labelsize=7, length=0)
    ax.grid(True, axis="y", color="#2a2a2a", linewidth=0.6)
    ax.plot(xs2, ys2, color=teal, linewidth=2.2)
    ax.fill_between(xs2, ys2, 54000, color=teal, alpha=0.10)
    ax.scatter([low_x], [low_v], s=40, color="#f87171", zorder=5, edgecolors="white", linewidths=1.2)
    ax.scatter([hi_x], [hi_v], s=40, color="#a3e635", zorder=5, edgecolors="white", linewidths=1.2)
    ax.annotate("$55,100 · 12:17 a.m.", (low_x, low_v), xytext=(10, -2), textcoords="offset points", color="#fca5a5", fontsize=8, fontweight="bold", va="center")
    ax.annotate("$60,883 · 8:03 a.m.", (hi_x, hi_v), xytext=(-8, 8), textcoords="offset points", color="#d9f99d", fontsize=8, fontweight="bold", ha="right")
    ax.set_ylim(54000, 62200)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-I %p"))
    fig.text(0.07, 0.86, "+10.5%", color="#a3e635", fontsize=30, fontweight="bold", va="center")
    fig.text(0.40, 0.89, "Bitcoin's overnight bounce on Kraken", color=ink, fontsize=11, fontweight="bold", va="center")
    fig.text(0.40, 0.81, "from a low not seen since September 2024", color="#d4d4d4", fontsize=10, va="center")
    fig.text(0.07, 0.70, "15-minute closes, Nov. 20-21, 2026 (Central time)", color="#a3a3a3", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind":"chart","sources":[
        {"file":"Kraken OHLC XBTUSD interval=15 and interval=1","license":"Kraken public API","url":"https://docs.kraken.com/api/docs/rest-api/get-ohlc-data","credit":"BTC/USD 15-minute closes Nov 20-21, 2026, the 12:17 a.m. CST low and 8:03 a.m. CST high, from Kraken"}
    ]}


def thumb_kraken_cad_crash():
    """Paper-white 'gap' chart: Kraken XBTCAD 15-minute lows vs XBTUSD closes x 1.4325 (Bank of Canada USD/CAD, Nov 20, 2026),
    Nov 20 noon - Nov 21 7:45 a.m. CST (frozen in chart-data.json). Low C$24,250 at 2:00 a.m. CST (08:00 UTC candle)."""
    rows = json.loads((I18N / "kraken-bitcoin-cad-flash-crash-24250-trades-stand-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    xs = [datetime.fromtimestamp(r[0] - 6 * 3600, tz=timezone.utc) for r in rows]
    cad = [r[1] for r in rows]; ref = [r[2] * 1.4325 for r in rows]
    bg, ink, red = "#f6efe3", "#1f2937", "#c8102e"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.08, 0.12, 0.88, 0.50]); ax.set_facecolor(bg)
    for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#a8a29e")
    ax.tick_params(colors="#57534e", labelsize=7, length=0)
    ax.grid(True, axis="y", color="#e7dccb", linewidth=0.6)
    ax.plot(xs, ref, color=ink, linewidth=1.4, linestyle=(0, (4, 2)))
    ax.plot(xs, cad, color=red, linewidth=2.0)
    ax.fill_between(xs, cad, ref, color=red, alpha=0.10)
    i = cad.index(min(cad))
    ax.scatter([xs[i]], [cad[i]], s=36, color=red, zorder=5, edgecolors="white", linewidths=1.2)
    ax.annotate("2 a.m. Central", (xs[i], cad[i]), xytext=(9, 0), textcoords="offset points", color=red, fontsize=7.5, fontweight="bold", va="center")
    ax.text(xs[2], 87500, "dollar price in C$", color=ink, fontsize=7, va="bottom")
    ax.set_ylim(18000, 95000)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"C${v/1000:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-I %p"))
    fig.text(0.08, 0.86, "C$24,250", color=red, fontsize=30, fontweight="bold", va="center")
    fig.text(0.47, 0.89, "Bitcoin's lowest trade on Kraken's", color=ink, fontsize=10.5, fontweight="bold", va="center")
    fig.text(0.47, 0.81, "Canadian-dollar market, Nov. 21", color=ink, fontsize=10.5, fontweight="bold", va="center")
    fig.text(0.08, 0.70, "about 71% below its dollar price at the time · trades stand", color="#57534e", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind": "chart", "sources": [
        {"file": "Kraken OHLC XBTCAD and XBTUSD interval=15", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "BTC/CAD 15-minute lows and BTC/USD closes Nov 20-21, 2026, from Kraken"},
        {"file": "FXUSDCAD 2026-11-20 = 1.4325", "license": "Public data", "url": "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=5", "credit": "Bank of Canada"},
    ]}


def thumb_death_bets_act():
    """U.S. Senate seal (Wikimedia Commons, CC BY-SA 2.5) with the five event-contract categories S. 4035 would ban."""
    seal = fetch("https://upload.wikimedia.org/wikipedia/commons/f/f0/Seal_of_the_United_States_Senate.svg", CACHE/"senate-seal.svg")
    base = gradient_bg(top=(10, 48, 44), bottom=(6, 20, 22))
    paste_contain(base, Image.open(seal).convert("RGBA"), (30, 56, 132, 132), pad=4)
    d = Draw(base)
    d.text((184, 66), "Passed the Senate", font=font(FONT_B, 36), fill=WHITE)
    d.text((186, 116), "S. 4035 · voice vote · Nov. 19, 2026", font=font(FONT_R, 17), fill=(253, 186, 116))
    d.text((186, 144), "next: the House", font=font(FONT_R, 15), fill=(167, 243, 208))
    items = ["Terrorism", "Assassination", "War", "Military ops", "A person's death"]
    f = font(FONT_B, 16)
    x, y = 30, 222
    for t in items:
        tw = d.textlength(t, font=f)
        w = tw + 28
        if x + w > 612: x, y = 30, y + 50
        d.rounded_rectangle([x, y, x + w, y + 38], radius=19, fill=(36, 14, 18), outline=(248, 113, 113), width=2)
        d.text((x + 14, y + 9), t, font=f, fill=(254, 226, 226))
        d.line([(x + 10, y + 19), (x + w - 10, y + 19)], fill=(248, 113, 113), width=3)
        x += w + 12
    d.text((30, 326), "Event contracts the bill would bar on CFTC-registered exchanges", font=font(FONT_R, 13), fill=(203, 213, 225))
    label_chip(base, "DEATH BETS Act · prediction markets")
    return base, {"kind":"composite","sources":[
        {"file":"Seal_of_the_United_States_Senate.svg","license":"CC BY-SA 2.5","url":"https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Senate.svg","credit":"Wikimedia Commons (vectorized U.S. Senate seal)"},
        {"file":"S.4035 as passed by the Senate, Nov. 19, 2026","license":"Facts cited (U.S. government work)","url":"https://www.govinfo.gov/content/pkg/BILLS-119s4035es/html/BILLS-119s4035es.htm","credit":"U.S. Senate / GovInfo"},
    ],"note":"Editorial composite for identification; no endorsement by the U.S. Senate implied."}


def thumb_chainflip_bounty():
    """Two vaults -> about $12M; 10%/90% bounty split. Amounts from Chainflip Labs (chainflip.io/return) and
    Bitcoin tx ac38a5ae... (block 976,865) / Ethereum tx 0xc928950f... (block 26,461,896); USD total at Kraken
    07:00 UTC Nov 21, 2026 prices (BTC 57,965.5, ETH 1,637.68)."""
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")
    logo = fetch("https://coin-images.coingecko.com/coins/images/25576/large/kdt_AgmT_400x400.png", CACHE/"chainflip-logo.png")
    base = gradient_bg(top=(44, 24, 8), bottom=(10, 8, 6))
    d = Draw(base)
    RED, BLUE = (248, 113, 113), (129, 140, 248)
    # two vault boxes on the left
    boxes = [(btc, "BITCOIN SIDE", "122.86 BTC", ORANGE, 58), (None, "ETHEREUM VAULT", "520.22 ETH", BLUE, 188)]
    for img, title, amt, col, y in boxes:
        d.rounded_rectangle([28, y, 300, y + 112], radius=14, fill=(24, 20, 18), outline=col, width=2)
        if img is not None:
            paste_contain(base, Image.open(img).convert("RGBA"), (40, y + 26, 60, 60), pad=0)
        else:
            tile = Image.new("RGBA", sz((60, 60)), (0, 0, 0, 255))
            mask = Image.new("L", sz((60, 60)), 0); Draw(mask).rounded_rectangle([0, 0, 59, 59], radius=10, fill=255)
            base.paste(tile.convert("RGB"), sz((40, y + 26)), mask)
            paste_contain(base, Image.open(logo).convert("RGBA"), (40, y + 26, 60, 60), pad=2)
        d = Draw(base)
        d.text((114, y + 22), title, font=font(FONT_B, 13), fill=col)
        d.text((114, y + 46), amt, font=font(FONT_B, 19), fill=WHITE)
        if title.startswith("ETH"):
            d.text((114, y + 74), "+ 3.25M USDC, 758K USDT", font=font(FONT_R, 11), fill=(203, 213, 225))
    # arrows into the total
    for y in (114, 244):
        d.line([(306, y), (346, 179)], fill=RED, width=4)
    d.polygon([(342, 168), (362, 179), (342, 190)], fill=RED)
    d.text((372, 132), "≈ $12M", font=font(FONT_B, 40), fill=WHITE)
    d.text((374, 186), "taken Nov. 21", font=font(FONT_R, 15), fill=(214, 211, 209))
    # bounty split bar
    bx0, bx1, by = 372, 612, 232
    split = bx0 + (bx1 - bx0) * 0.9
    d.rounded_rectangle([bx0, by, bx1, by + 30], radius=8, fill=(34, 197, 94))
    d.rectangle([split, by, bx1, by + 30], fill=ORANGE)
    d.text((bx0 + 10, by + 6), "return 90%", font=font(FONT_B, 14), fill=(5, 46, 22))
    kw = d.textlength("keep 10%", font=font(FONT_B, 12))
    d.text((bx1 - kw, by + 38), "keep 10%", font=font(FONT_B, 12), fill=ORANGE)
    d.text((372, 292), "Offer ends 18:38 UTC, Nov. 23", font=font(FONT_R, 14), fill=(214, 211, 209))
    label_chip(base, "Chainflip · bounty offer")
    return base, {"kind": "composite", "sources": [
        {"file": "Bitcoin.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "chainflip-logo.png", "license": "Logo", "url": "https://www.coingecko.com/en/coins/chainflip", "credit": "Chainflip (logo via CoinGecko)"},
        {"file": "Message from Chainflip Labs", "license": "Figures cited", "url": "https://chainflip.io/return", "credit": "Chainflip Labs"},
        {"file": "Bitcoin tx ac38a5aea1ed81b84307a3709f502abd4c4d3af5502493f883c6d19624fd2cb4", "license": "Public blockchain data", "url": "https://mempool.space/tx/ac38a5aea1ed81b84307a3709f502abd4c4d3af5502493f883c6d19624fd2cb4", "credit": "mempool.space"},
    ], "note": "Editorial composite for identification; trademarks belong to their owners."}


def thumb_core_node_stall():
    """Bitcoin logo + 'inv x 50,000' stall diagram; versions from the Bitcoin Core advisory CVE-2026-117348 (Nov. 20, 2026)."""
    btc = fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")
    base = gradient_bg(top=(16, 32, 40), bottom=(6, 12, 16))
    d = Draw(base)
    TEAL, RED, GREEN = (94, 234, 212), (248, 113, 113), (52, 211, 153)
    # stacked "inv" messages
    for i in range(6):
        x, y = 30 + i * 7, 64 + i * 9
        d.rounded_rectangle([x, y, x + 196, y + 46], radius=8, fill=(20, 40, 48), outline=TEAL, width=1)
    x, y = 65, 109
    d.text((x + 10, y + 6), "inv: same tx ID", font=font(FONT_B, 14), fill=WHITE)
    d.text((x + 10, y + 26), "× 50,000", font=font(FONT_B, 14), fill=TEAL)
    # arrow to node
    d.line([(272, 132), (316, 132)], fill=RED, width=4)
    d.polygon([(314, 122), (332, 132), (314, 142)], fill=RED)
    # node circle with bitcoin logo
    paste_contain(base, Image.open(btc).convert("RGBA"), (340, 72, 120, 120), pad=0)
    d = Draw(base)
    d.text((474, 92), "node stalls", font=font(FONT_B, 22), fill=WHITE)
    d.text((474, 122), "12+ seconds", font=font(FONT_B, 22), fill=RED)
    d.text((474, 154), "per message", font=font(FONT_R, 14), fill=(203, 213, 225))
    # version chips
    chips = [("30.5", GREEN), ("31.3", GREEN), ("32.1", GREEN), ("29.x: no fix", RED)]
    x = 30
    f = font(FONT_B, 17)
    d.text((30, 222), "Update to a fixed Bitcoin Core version:", font=font(FONT_R, 15), fill=(203, 213, 225))
    for t, col in chips:
        w = d.textlength(t, font=f) + 30
        d.rounded_rectangle([x, 254, x + w, 294], radius=20, fill=(12, 24, 28), outline=col, width=2)
        d.text((x + 15, 264), t, font=f, fill=col)
        x += w + 12
    d.text((30, 314), "CVE-2026-117348 · medium severity · found by an AI scan", font=font(FONT_R, 13), fill=(148, 163, 184))
    label_chip(base, "Bitcoin Core · security fix")
    return base, {"kind": "composite", "sources": [
        {"file": "Bitcoin.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "CVE-2026-117348 advisory", "license": "Facts cited", "url": "https://bitcoincore.org/en/2026/11/20/disclose-orphan-inv-stall/", "credit": "Bitcoin Core"},
    ], "note": "Editorial diagram; no endorsement by Bitcoin Core implied."}



def thumb_fusionist_ace():
    """Indigo 'supply blow-up' diagram: ACE supply on BNB Chain before (about 53.7M) vs after Sunday's unbacked mints
    (about 10.02 quintillion, read from the BscScan/BNB Chain contract on Nov. 22, 2026) and the bridge reserve (53.7M -> 0.08 ACE, The Block)."""
    base = gradient_bg(top=(49, 18, 92), bottom=(12, 8, 28))
    d = Draw(base)
    d.text((30, 50), "10 quintillion", font=font(FONT_B, 54), fill=(196, 181, 253))
    d.text((34, 118), "fake ACE tokens minted on BNB Chain on Sunday", font=font(FONT_B, 17), fill=WHITE)
    d.text((34, 143), "Fusionist bridge exploit · Nov. 22, 2026", font=font(FONT_R, 13), fill=(221, 214, 254))
    fl, fv = font(FONT_R, 13), font(FONT_B, 14)
    # before: a sliver; after: full width
    d.text((30, 180), "Supply before", font=fl, fill=(221, 214, 254))
    d.rectangle([150, 182, 153, 198], fill=(52, 211, 153))
    d.text((162, 181), "≈ 53.7 million", font=fv, fill=(167, 243, 208))
    d.text((30, 214), "Supply after", font=fl, fill=(221, 214, 254))
    d.rectangle([150, 210, 610, 232], fill=(248, 113, 113))
    d.text((160, 213), "≈ 10,020,000,000,000,000,000", font=fv, fill=WHITE)
    # bridge reserve chip
    d.rounded_rectangle([30, 262, 610, 330], radius=14, fill=(20, 12, 40), outline=(247, 147, 26), width=2)
    d.text((48, 274), "Bridge reserve of real ACE", font=font(FONT_R, 13), fill=(203, 213, 225))
    d.text((48, 296), "53.7 million  →  0.08", font=font(FONT_B, 20), fill=(253, 230, 138))
    d.text((360, 296), "about $3.7M drained", font=font(FONT_B, 15), fill=(254, 202, 202))
    label_chip(base, "Security · bridge exploit")
    return base, {"kind": "diagram", "sources": [
        {"file": "BNB Chain ACE token 0xc27a719105a987b4c34116223cae8bd8f4b5def4 totalSupply()", "license": "Public blockchain data", "url": "https://bscscan.com/token/0xc27a719105a987b4c34116223cae8bd8f4b5def4", "credit": "Total supply about 10.02 quintillion ACE, read Nov. 22, 2026"},
        {"file": "The Block, Nov. 22, 2026", "license": "Figures cited", "url": "https://www.theblock.co/news/defi/2026-11-22-a-2-million-exploit-leads-to-a-3-7-million-free-for-all-as-traders-empty-fusionists-ace-bridge-444838", "credit": "53.7M ACE bridge reserve, 0.08 ACE left, about $3.7M"}
    ]}


def thumb_trump_dinner():
    """Gold-on-stone area chart: Kraken TRUMPUSD daily closes Jan 2025 - Nov 22, 2026 (frozen in chart-data.json), log scale,
    highest close $46.59 (Jan 19, 2025), first-dinner close $14.72 (May 22, 2025), latest about $0.88."""
    rows = json.loads((I18N / "trump-memecoin-second-dinner-token-down-99-percent-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    xs = [datetime.fromtimestamp(r[0], tz=timezone.utc) for r in rows]; ys = [r[1] for r in rows]
    bg, ink, gold = "#1c1917", "#fafaf9", "#fbbf24"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.08, 0.12, 0.88, 0.50]); ax.set_facecolor(bg)
    for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#57534e")
    ax.tick_params(colors="#d6d3d1", labelsize=7, length=0)
    ax.set_yscale("log")
    ax.grid(True, axis="y", color="#2e2a27", linewidth=0.6)
    ax.plot(xs, ys, color=gold, linewidth=1.8)
    ax.fill_between(xs, ys, 0.6, color=gold, alpha=0.16); ax.set_ylim(0.6, 60)
    d1 = datetime(2025, 5, 22, tzinfo=timezone.utc)
    ax.scatter([d1], [14.717], s=36, color="#fde68a", zorder=5, edgecolors="white", linewidths=1.1)
    ax.annotate("1st dinner · $14.72", (d1, 14.717), xytext=(8, 6), textcoords="offset points", color="#fde68a", fontsize=7.5, fontweight="bold")
    ax.scatter([xs[-1]], [ys[-1]], s=36, color="#f87171", zorder=5, edgecolors="white", linewidths=1.1)
    ax.annotate(f"Nov. 22 · ${ys[-1]:.2f}", (xs[-1], ys[-1]), xytext=(-12, -1), textcoords="offset points", color="#fca5a5", fontsize=7.5, fontweight="bold", ha="right", va="center")
    ax.set_yticks([1, 3, 10, 30]); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:g}"))
    ax.yaxis.set_minor_formatter(plt.NullFormatter())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.text(0.95, 0.85, "−99%", color="#f87171", fontsize=34, fontweight="bold", va="center", ha="right")
    fig.text(0.07, 0.90, "TRUMP memecoin from its peak", color=ink, fontsize=12, fontweight="bold", va="center")
    fig.text(0.07, 0.82, "as top holders gather for a second dinner", color="#fcd34d", fontsize=10, va="center")
    fig.text(0.07, 0.70, "Daily close on Kraken, log scale, Jan. 2025 - Nov. 22, 2026", color="#a8a29e", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind": "chart", "sources": [
        {"file": "Kraken OHLC TRUMPUSD interval=1440", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "TRUMP/USD daily closes Jan 2025 - Nov 22, 2026, from Kraken"},
        {"file": "The Block, Nov. 22, 2026", "license": "Figure cited", "url": "https://www.theblock.co/news/ecosystems/2026-11-22-trump-to-host-second-memecoin-dinner-tonight-with-trump-down-99-from-peak-444828", "credit": "All-time high $73.43; down about 99%"}
    ]}

def thumb_etf_weekly_179():
    """Cream 'newspaper' chart: U.S. spot bitcoin ETF daily net flows for the week of Nov. 16-20, 2026
    (Farside Investors, read Nov. 23, 2026) with the week's total of -$1.79B."""
    days = ["Mon\nNov 16", "Tue\nNov 17", "Wed\nNov 18", "Thu\nNov 19", "Fri\nNov 20"]
    flows = [7.9, -239.9, -306.5, -582.3, -669.2]
    bg, ink, red, green = "#f4efe6", "#1c1917", "#b91c1c", "#15803d"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.47, 0.17, 0.50, 0.70]); ax.set_facecolor(bg)
    cols = [green if v > 0 else red for v in flows]
    ax.bar(range(5), flows, color=cols, width=0.62)
    ax.axhline(0, color=ink, linewidth=0.9)
    for i, v in enumerate(flows):
        ax.text(i, v - 18 if v < 0 else v + 12, (f"+{v:,.1f}" if v > 0 else f"{v:,.0f}"), ha="center",
                va="top" if v < 0 else "bottom", color=ink, fontsize=7.5, fontweight="bold")
    ax.set_ylim(-760, 60)
    ax.set_xticks(range(5)); ax.set_xticklabels(days)
    for sp in ("top", "right", "left", "bottom"): ax.spines[sp].set_visible(False)
    ax.tick_params(axis="x", colors="#44403c", labelsize=7, length=0, pad=4)
    ax.tick_params(axis="y", left=False, labelleft=False)
    ax.xaxis.set_ticks_position("top")
    fig.text(0.05, 0.80, "WEEKLY OUTFLOW", color=red, fontsize=9, fontweight="bold", va="center")
    fig.text(0.05, 0.64, "-$1.79B", color=ink, fontsize=40, fontweight="bold", va="center")
    fig.text(0.05, 0.47, "U.S. spot bitcoin ETFs", color=ink, fontsize=11, fontweight="bold", va="center")
    fig.text(0.05, 0.39, "Nov. 16-20, 2026", color="#57534e", fontsize=10, va="center")
    fig.text(0.05, 0.25, "4th losing week in a row", color=red, fontsize=10, fontweight="bold", va="center")
    fig.text(0.05, 0.10, "Daily net flows, US$ millions (Farside Investors)", color="#78716c", fontsize=6.8, va="center")
    fig.add_artist(plt.Line2D([0.43, 0.43], [0.10, 0.90], color="#d6cfc2", linewidth=1))
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind": "chart", "sources": [
        {"file": "Farside Investors Bitcoin ETF Flow - All Data", "license": "Public data, cited", "url": "https://farside.co.uk/bitcoin-etf-flow-all-data/", "credit": "Daily U.S. spot bitcoin ETF net flows, Nov. 16-20, 2026 (read Nov. 23, 2026)"}
    ]}


def thumb_strategy_457_btc():
    """Light 'money flow' diagram from Strategy's Nov. 23, 2026 Form 8-K: $176.7M raised from MSTR sales ->
    $29.6M bitcoin (457 BTC) vs $147.0M STRC buybacks (+$64.8M from USD Cash = $211.8M). Strategy logo (public domain, Wikimedia)."""
    logo = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Strategy_logo_%282025%29.svg", CACHE/"strategy-logo-2025.svg")).convert("RGBA")
    base = gradient_bg(top=(255, 250, 243), bottom=(250, 236, 218))
    d = Draw(base)
    ink, mute, orange, blue = (28, 25, 23), (87, 83, 78), (234, 88, 12), (3, 105, 161)
    paste_contain(base, logo, (22, 18, 170, 52), pad=4)
    d.text((206, 30), "Form 8-K · week of Nov. 16-22, 2026", font=font(FONT_R, 13), fill=mute)
    # source box
    d.rounded_rectangle([24, 120, 214, 236], radius=14, fill=(255, 255, 255), outline=(214, 211, 209), width=2)
    d.text((40, 134), "MSTR stock sold", font=font(FONT_R, 13), fill=mute)
    d.text((40, 156), "$176.7M", font=font(FONT_B, 34), fill=ink)
    d.text((40, 204), "1,925,676 shares", font=font(FONT_R, 12), fill=mute)
    # arrows
    d.line([(214, 160), (300, 112)], fill=orange, width=4)
    d.line([(214, 200), (300, 262)], fill=blue, width=10)
    # targets
    d.rounded_rectangle([300, 70, 616, 156], radius=14, fill=(255, 237, 213), outline=orange, width=2)
    d.text((318, 80), "Bitcoin bought", font=font(FONT_R, 13), fill=mute)
    d.text((318, 100), "$29.6M", font=font(FONT_B, 30), fill=orange)
    d.text((462, 108), "= 457 BTC", font=font(FONT_B, 17), fill=ink)
    d.rounded_rectangle([300, 196, 616, 300], radius=14, fill=(224, 242, 254), outline=blue, width=2)
    d.text((318, 206), "STRC preferred bought back", font=font(FONT_R, 13), fill=mute)
    d.text((318, 226), "$147.0M", font=font(FONT_B, 30), fill=blue)
    d.text((318, 270), "+ $64.8M from cash = $211.8M total", font=font(FONT_B, 13), fill=ink)
    d.text((24, 322), "Now holds 851,305 BTC · average cost $75,446", font=font(FONT_B, 15), fill=ink)
    return base, {"kind": "diagram", "sources": [
        {"file": "Strategy_logo_(2025).svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Strategy_logo_(2025).svg", "credit": "Strategy logo"},
        {"file": "Strategy Form 8-K, Nov. 23, 2026", "license": "Figures cited", "url": "https://www.sec.gov/Archives/edgar/data/1050446/000119312526470961/mstr-20261123.htm", "credit": "Strategy Inc"}
    ], "note": "Editorial diagram; logo for identification; trademarks belong to their owners."}


def thumb_binance_security_review():
    """Black/yellow 'outside reviewers' diagram: Binance logo (Wikimedia) and the three firms it engaged on Nov. 23, 2026
    (Binance blog / PR Newswire). Mandiant logo is public domain on Wikimedia; SlowMist and Verichains as text."""
    binance = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")).convert("RGBA")
    mandiant = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/d/d3/Mandiant_logo.svg", CACHE/"mandiant-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(24, 26, 32), bottom=(6, 7, 9))
    d = Draw(base)
    yellow, ink = (240, 185, 11), (30, 32, 38)
    # faint scan grid
    for x in range(0, W, 32): d.line([(x, 0), (x, H)], fill=(34, 37, 44), width=1)
    for y in range(0, H, 32): d.line([(0, y), (W, y)], fill=(34, 37, 44), width=1)
    # Binance tile on the left
    d.rounded_rectangle([28, 96, 228, 266], radius=18, fill=ink, outline=yellow, width=3)
    paste_contain(base, binance, (28, 96, 200, 170), pad=26)
    d = Draw(base)
    # magnifier over the tile
    d.ellipse([170, 58, 250, 138], outline=yellow, width=6)
    d.line([(240, 128), (270, 158)], fill=yellow, width=9)
    # three reviewer cards on the right
    rows = [("Incident response, threat intel", None), ("Blockchain security", "SlowMist"), ("Offensive research, Web3", "Verichains")]
    y0 = 52
    for i, (role, name) in enumerate(rows):
        y = y0 + i * 92
        d.rounded_rectangle([300, y, 612, y + 76], radius=14, fill=(245, 245, 244) if i == 0 else ink, outline=(70, 74, 84), width=2)
        if name is None:
            paste_contain(base, mandiant, (312, y + 4, 170, 46), pad=4)
            d = Draw(base)
            d.text((316, y + 50), role, font=font(FONT_R, 13), fill=(68, 64, 60))
        else:
            d.text((316, y + 10), name, font=font(FONT_B, 26), fill=WHITE)
            d.text((316, y + 50), role, font=font(FONT_R, 13), fill=(203, 213, 225))
        d.line([(270, 181), (300, y + 38)], fill=(120, 110, 60), width=2)
    d.text((28, 290), "3 outside firms", font=font(FONT_B, 24), fill=yellow)
    d.text((28, 322), "engaged Nov. 23, 2026 · findings not yet published", font=font(FONT_R, 13), fill=(203, 213, 225))
    label_chip(base, "Binance · security review")
    return base, {"kind": "composite", "sources": [
        {"file": "Binance_Logo.svg", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:Binance_Logo.svg", "credit": "Binance"},
        {"file": "Mandiant_logo.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Mandiant_logo.svg", "credit": "Mandiant"},
        {"file": "Binance announcement, Nov. 23, 2026", "license": "Facts cited", "url": "https://www.prnewswire.com/news-releases/binance-engages-mandiant-slowmist-and-verichains-for-independent-third-party-security-review-302948286.html", "credit": "Binance / PR Newswire"},
    ], "note": "Editorial diagram; logos for identification; trademarks belong to their owners."}


def thumb_ark_withdraws_cd20_etfs():
    """Light 'filing paper' diagram: ARK Invest logo and SEC seal (both public domain on Wikimedia) with the two Form RW
    withdrawal requests dated Nov. 20, 2026 (SEC EDGAR, File Nos. 333-292914 and 333-292915, S-1s filed Jan. 23, 2026)."""
    ark = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/9/90/Ark_Invest_logo.svg", CACHE/"ark-invest-logo.svg")).convert("RGBA")
    sec = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", CACHE/"sec-seal.svg")).convert("RGBA")
    base = gradient_bg(top=(236, 241, 247), bottom=(214, 223, 234))
    d = Draw(base)
    ink, mute, red = (15, 23, 42), (71, 85, 105), (190, 18, 60)
    paste_contain(base, ark, (24, 22, 150, 56), pad=4)
    paste_contain(base, sec, (540, 14, 80, 80), pad=2)
    d = Draw(base)
    d.text((24, 88), "Form RW · request for withdrawal · Nov. 20, 2026", font=font(FONT_B, 14), fill=mute)
    docs = [("ARK CoinDesk 20", "Crypto ETF", "File No. 333-292914"), ("ARK CoinDesk 20", "ex-Bitcoin Crypto ETF", "File No. 333-292915")]
    for i, (a, b, c) in enumerate(docs):
        x = 24 + i * 302
        # paper shadow + sheet
        d.rounded_rectangle([x + 5, 125, x + 290, 315], radius=8, fill=(180, 192, 207))
        d.rounded_rectangle([x, 120, x + 285, 310], radius=8, fill=WHITE, outline=(203, 213, 225), width=2)
        d.text((x + 16, 134), "FORM S-1 · filed Jan. 23, 2026", font=font(FONT_R, 11), fill=mute)
        d.text((x + 16, 156), a, font=font(FONT_B, 19), fill=ink)
        d.text((x + 16, 182), b, font=font(FONT_B, 17), fill=ink)
        for k in range(3):
            d.line([(x + 16, 214 + k * 12), (x + 260 - k * 40, 214 + k * 12)], fill=(226, 232, 240), width=4)
        d.text((x + 16, 284), c, font=font(FONT_R, 12), fill=mute)
        # stamp
        stamp = Image.new("RGBA", sz((176, 56)), (0, 0, 0, 0)); sd = Draw(stamp)
        sd.rounded_rectangle([2, 2, 173, 53], radius=6, outline=(*red, 230), width=4)
        sd.text((14, 7), "WITHDRAWAL", font=font(FONT_B, 19), fill=(*red, 235))
        sd.text((24, 30), "REQUESTED", font=font(FONT_B, 17), fill=(*red, 235))
        stamp = stamp.rotate(-12, expand=True, resample=Image.Resampling.BICUBIC)
        base.paste(stamp, sz((x + 86, 196)), stamp)
        d = Draw(base)
    d.text((24, 326), "Never effective · no shares ever sold · ARKB not affected", font=font(FONT_B, 14), fill=ink)
    label_chip(base, "ARK Invest · crypto index ETFs", xy=(200, 30))
    return base, {"kind": "diagram", "sources": [
        {"file": "Ark_Invest_logo.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Ark_Invest_logo.svg", "credit": "ARK Invest"},
        {"file": "Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", "license": "Public domain (U.S. government)", "url": "https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Securities_and_Exchange_Commission.svg", "credit": "SEC"},
        {"file": "ARK Form RW filings, Nov. 20, 2026", "license": "Facts cited", "url": "https://www.sec.gov/Archives/edgar/data/2106116/000121390026122577/ea0313104-01_rw.htm", "credit": "SEC EDGAR"},
    ], "note": "Editorial diagram; logos for identification; trademarks belong to their owners."}


def thumb_huang_btc_fade():
    """Cream split card: Nvidia logo (Wikimedia, identification only) with the Nasdaq's +6.51% close (The Motley Fool) vs
    the Bitcoin logo (Wikimedia) with Kraken XBTUSD 15-minute closes for Nov 23, 2026 (frozen in chart-data.json):
    the $64,520 high after Huang's reinstatement and the fade back to about $61,200."""
    nv = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/2/21/Nvidia_logo.svg", CACHE/"nvidia-logo.svg")).convert("RGBA")
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-wiki.svg")).convert("RGBA")
    data = json.loads((I18N / "bitcoin-spikes-to-64500-on-huang-return-then-fades-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))["rows"]
    base = gradient_bg(top=(250, 247, 240), bottom=(238, 232, 220))
    d = Draw(base)
    ink, mute, green, orange = (28, 25, 23), (87, 83, 78), (118, 185, 0), (247, 147, 26)
    # left panel: stocks
    d.rounded_rectangle([20, 52, 300, 336], radius=16, fill=(255, 255, 255), outline=(214, 211, 209), width=2)
    paste_contain(base, nv, (40, 70, 240, 90), pad=4)
    d = Draw(base)
    d.text((44, 176), "Nasdaq", font=font(FONT_B, 20), fill=mute)
    d.text((44, 204), "+6.51%", font=font(FONT_B, 54), fill=(77, 124, 15))
    # small rising bars
    for k, hgt in enumerate((18, 30, 44, 62)):
        d.rounded_rectangle([196 + k * 22, 318 - hgt, 212 + k * 22, 318], radius=3, fill=green)
    d.text((44, 290), "Huang back as CEO", font=font(FONT_R, 13), fill=mute)
    # right panel: bitcoin round trip
    d.rounded_rectangle([320, 52, 620, 336], radius=16, fill=(28, 25, 23))
    paste_contain(base, btc, (336, 64, 52, 52), pad=2)
    d = Draw(base)
    d.text((396, 70), "Bitcoin", font=font(FONT_B, 20), fill=(250, 250, 249))
    d.text((396, 94), "+0.08% on the day", font=font(FONT_R, 13), fill=(214, 211, 209))
    ys = [r[1] for r in data]; n = len(ys)
    lo, hi = 60400, 64800
    x0, x1, y0, y1 = 340, 600, 140, 300
    pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * (v - lo) / (hi - lo)) for i, v in enumerate(ys)]
    d.line(pts + [], fill=orange, width=3, joint="curve")
    hi_i = max(range(n), key=lambda i: data[i][2]); hx = x0 + (x1 - x0) * hi_i / (n - 1); hy = y1 - (y1 - y0) * (data[hi_i][2] - lo) / (hi - lo)
    d.ellipse([hx - 5, hy - 5, hx + 5, hy + 5], fill=(52, 211, 153))
    d.text((hx + 8, hy - 8), "$64,520", font=font(FONT_B, 16), fill=(110, 231, 183))
    d.text((x1 - 70, pts[-1][1] - 26), "$61,2xx".replace("xx", f"{int(ys[-1]) % 100:02d}"), font=font(FONT_B, 15), fill=(253, 186, 116))
    d.text((340, 310), "Kraken · Nov. 23 · Central time", font=font(FONT_R, 12), fill=(168, 162, 158))
    label_chip(base, "Nvidia rally vs. bitcoin")
    return base, {"kind": "composite", "sources": [
        {"file": "Nvidia_logo.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Nvidia_logo.svg", "credit": "NVIDIA"},
        {"file": "Bitcoin.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "Kraken OHLC XBTUSD interval=15, Nov 23, 2026", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Kraken"},
        {"file": "Nasdaq +6.51%, bitcoin +0.08%", "license": "Facts cited", "url": "https://www.fool.com/coverage/stock-market-today/2026/11/23/crypto-market-today-nov-23-bitcoin-sits-out-wall-street-s-historic-rally-as-usd1-8-billion-etf-exodus-weighs-on-prices/", "credit": "The Motley Fool"},
    ], "note": "Editorial composite; logos for identification; trademarks belong to their owners."}


def thumb_cftc_crypto_reserves():
    """Light 'reserve ledger': CFTC seal (public domain, Wikimedia) with bitcoin, ether and a generic payment-stablecoin token,
    each tagged with the minimum haircut from CFTC Letter No. 26-31 (20%, 20%, 2%), over a 12-month reserve bar
    (6 months cash or liquid for DCMs/DCOs)."""
    cftc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/3/3e/Commodity_Futures_Trading_Commission_seal.svg", CACHE/"cftc-seal.svg")).convert("RGBA")
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-wiki.svg")).convert("RGBA")
    eth = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/0/05/Ethereum_logo_2014.svg", CACHE/"ethereum-logo-2014.svg")).convert("RGBA")
    base = gradient_bg(top=(232, 240, 248), bottom=(208, 222, 236))
    d = Draw(base)
    ink, mute, navy, red = (15, 23, 42), (71, 85, 105), (30, 58, 138), (185, 28, 28)
    paste_contain(base, cftc, (22, 40, 170, 170), pad=4)
    d = Draw(base)
    tiles = [(btc, "BTC", "-20%"), (eth, "ETH", "-20%"), (None, "Stablecoin", "-2%")]
    for i, (logo, name, cut) in enumerate(tiles):
        x = 214 + i * 136
        d.rounded_rectangle([x, 50, x + 120, 196], radius=14, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
        if logo is not None:
            paste_contain(base, logo, (x + 22, 58, 76, 76), pad=4)
            d = Draw(base)
        else:
            d.ellipse([x + 26, 62, x + 94, 130], fill=(22, 163, 74))
            d.text((x + 46, 72), "$", font=font(FONT_B, 40), fill=(255, 255, 255))
        d.text((x + 60 - d.textlength(name, font=font(FONT_B, 14)) / 2, 140), name, font=font(FONT_B, 14), fill=ink)
        tag = font(FONT_B, 18); tw = d.textlength(cut, font=tag)
        d.rounded_rectangle([x + 60 - tw / 2 - 10, 164, x + 60 + tw / 2 + 10, 190], radius=8, fill=red)
        d.text((x + 60 - tw / 2, 166), cut, font=tag, fill=(255, 255, 255))
    # 12-month reserve bar
    d.text((24, 228), "A year of operating costs (futures exchanges and clearinghouses)", font=font(FONT_B, 14), fill=ink)
    bw = 592 / 12
    for m in range(12):
        x = 24 + m * bw
        d.rounded_rectangle([x + 2, 254, x + bw - 2, 292], radius=5, fill=(100, 116, 139) if m < 6 else (247, 147, 26))
    d.text((28, 300), "6 months: cash or liquid securities only", font=font(FONT_R, 13), fill=mute)
    d.text((330, 300), "6 months: may include crypto", font=font(FONT_R, 13), fill=(154, 52, 18))
    d.text((24, 326), "CFTC staff advisory · Nov. 23, 2026", font=font(FONT_R, 12), fill=mute)
    label_chip(base, "CFTC · crypto in reserves", xy=(380, 14))
    return base, {"kind": "composite", "sources": [
        {"file": "Commodity_Futures_Trading_Commission_seal.svg", "license": "Public domain (U.S. government)", "url": "https://commons.wikimedia.org/wiki/File:Commodity_Futures_Trading_Commission_seal.svg", "credit": "CFTC"},
        {"file": "Bitcoin.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "Ethereum_logo_2014.svg", "license": "CC BY 3.0 (logo)", "url": "https://commons.wikimedia.org/wiki/File:Ethereum_logo_2014.svg", "credit": "Ethereum Foundation"},
        {"file": "CFTC Letter No. 26-31, Nov. 23, 2026", "license": "Facts cited", "url": "https://www.cftc.gov/csl/26-31/download", "credit": "CFTC"},
    ], "note": "Editorial diagram; seal and logos for identification; no endorsement by the CFTC implied."}


def thumb_etf_nov_record_471():
    """Warm-paper 'November calendar': one tile per U.S. trading day Nov. 2-23, 2026, red for net outflow and green for
    inflow (Farside daily Total column, frozen in chart-data.json), the record -$4.71B month total and the Bitcoin logo (Wikimedia)."""
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-wiki.svg")).convert("RGBA")
    data = json.loads((I18N / "bitcoin-etfs-record-4-71-billion-november-outflows-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    days = data["nov_days"]; assert len(days) == 16
    base = gradient_bg(top=(253, 246, 236), bottom=(244, 228, 214))
    d = Draw(base)
    ink, mute, red, green = (41, 22, 17), (120, 86, 72), (190, 30, 45), (21, 128, 61)
    paste_contain(base, btc, (24, 54, 64, 64), pad=2)
    d = Draw(base)
    d.text((100, 58), "U.S. spot bitcoin ETFs", font=font(FONT_B, 18), fill=ink)
    d.text((100, 84), "November 2026, day by day", font=font(FONT_R, 14), fill=mute)
    # weekday header and tiles (Mon-Fri columns, 4 weeks)
    cols = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    x0, y0, cw, ch, gap = 24, 138, 64, 38, 6
    for i, c in enumerate(cols):
        d.text((x0 + i * (cw + gap) + 16, y0 - 22), c, font=font(FONT_B, 12), fill=mute)
    import datetime as _dt
    for lab, v in days:
        dt_ = _dt.datetime.strptime(lab, "%d %b %Y"); wk = (dt_.day - 2) // 7; wd = dt_.weekday()
        x = x0 + wd * (cw + gap); y = y0 + wk * (ch + gap)
        d.rounded_rectangle([x, y, x + cw, y + ch], radius=7, fill=red if v < 0 else green)
        d.text((x + 6, y + 3), str(dt_.day), font=font(FONT_B, 11), fill=(255, 235, 230))
        txt = f"{v:+,.0f}"; f = font(FONT_B, 13)
        d.text((x + cw - 6 - d.textlength(txt, font=f), y + 21), txt, font=f, fill=(255, 255, 255))
    d.text((x0, y0 + 4 * (ch + gap) + 4), "Daily net flows, US$ millions · Farside Investors", font=font(FONT_R, 11), fill=mute)
    # right: record total
    rx = 392
    d.rounded_rectangle([rx, 54, 620, 336], radius=16, fill=(41, 22, 17))
    d.text((rx + 20, 74), "RECORD MONTH", font=font(FONT_B, 14), fill=(251, 146, 60))
    d.text((rx + 18, 100), "-$4.71B", font=font(FONT_B, 46), fill=(255, 255, 255))
    d.text((rx + 20, 160), "Nov. 1-23 net outflow", font=font(FONT_R, 14), fill=(231, 214, 205))
    # comparison bars vs prior worst months
    bars = [("Nov 2026", 4706.7, (239, 68, 68)), ("Jun 2026", 4509.7, (168, 120, 100)), ("Feb 2025", 3560.4, (168, 120, 100))]
    for k, (lab, v, colr) in enumerate(bars):
        y = 198 + k * 42
        d.text((rx + 20, y), lab, font=font(FONT_R, 12), fill=(231, 214, 205))
        wpx = 188 * v / 4706.7
        d.rounded_rectangle([rx + 20, y + 17, rx + 20 + wpx, y + 31], radius=4, fill=colr)
        d.text((rx + 20 + wpx - 50, y), f"-${v/1000:.2f}B", font=font(FONT_B, 12), fill=(255, 255, 255))
    label_chip(base, "ETF outflows · record month", xy=(392, 14))
    return base, {"kind": "composite", "sources": [
        {"file": "Bitcoin.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "Farside Investors Bitcoin ETF Flow - All Data", "license": "Public data, cited", "url": "https://farside.co.uk/bitcoin-etf-flow-all-data/", "credit": "Daily U.S. spot bitcoin ETF net flows, Nov. 2-23, 2026, and monthly totals (read Nov. 24, 2026)"},
    ]}


def thumb_korea_digital_asset_bill():
    """Light diagram: Flag of South Korea (public domain, Wikimedia) with a donut for the bank-majority stablecoin rule
    (>50% banks) and an ownership bar for the exchange cap (20%, up to 34% with approval), from the FSC's Nov. 24, 2026 press release."""
    flag = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/0/09/Flag_of_South_Korea.svg", CACHE/"flag-south-korea.svg")).convert("RGBA")
    base = gradient_bg(top=(246, 248, 252), bottom=(226, 232, 242))
    d = Draw(base)
    ink, mute, kred, kblue = (17, 24, 39), (75, 85, 99), (205, 46, 58), (0, 71, 160)
    d.rounded_rectangle([20, 50, 196, 170], radius=10, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
    paste_contain(base, flag, (26, 56, 164, 108), pad=2)
    d = Draw(base)
    d.text((22, 184), "Draft digital", font=font(FONT_B, 18), fill=ink)
    d.text((22, 208), "asset law", font=font(FONT_B, 18), fill=ink)
    d.text((22, 236), "FSC · Nov. 24, 2026", font=font(FONT_R, 13), fill=mute)
    d.text((22, 300), "Still needs the", font=font(FONT_R, 13), fill=mute)
    d.text((22, 318), "National Assembly", font=font(FONT_R, 13), fill=mute)
    # donut: banks > 50%
    cx, cy, r = 300, 170, 78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(203, 213, 225))
    d.pieslice([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * 0.55, fill=kblue)
    d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], fill=(240, 243, 249))
    t1 = ">50%"; f1 = font(FONT_B, 24); d.text((cx - d.textlength(t1, font=f1) / 2, cy - 22), t1, font=f1, fill=kblue)
    t2 = "banks"; f2 = font(FONT_R, 13); d.text((cx - d.textlength(t2, font=f2) / 2, cy + 8), t2, font=f2, fill=mute)
    d.text((cx - 92, 264), "Won stablecoin issuers", font=font(FONT_B, 14), fill=ink)
    d.text((cx - 92, 284), "fintech may be top holder", font=font(FONT_R, 12), fill=mute)
    # exchange ownership cap bar
    bx = 420
    d.text((bx, 64), "Exchange owners", font=font(FONT_B, 16), fill=ink)
    d.text((bx, 88), "max stake per shareholder", font=font(FONT_R, 12), fill=mute)
    top, bot = 120, 300
    d.rounded_rectangle([bx + 40, top, bx + 120, bot], radius=8, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
    h = bot - top
    y34 = bot - h * 0.34; y20 = bot - h * 0.20
    d.rectangle([bx + 42, y34, bx + 118, y20], fill=(252, 165, 165))
    d.rounded_rectangle([bx + 42, y20, bx + 118, bot - 2], radius=6, fill=kred)
    d.line([(bx + 34, y20), (bx + 126, y20)], fill=ink, width=2)
    d.line([(bx + 34, y34), (bx + 126, y34)], fill=ink, width=1)
    d.text((bx + 132, y20 - 10), "20%", font=font(FONT_B, 20), fill=kred)
    d.text((bx + 132, y34 - 16), "34%", font=font(FONT_B, 16), fill=(185, 28, 28))
    d.text((bx + 132, y34 + 4), "with OK", font=font(FONT_R, 11), fill=mute)
    d.text((bx + 132, top - 4), "100%", font=font(FONT_R, 11), fill=mute)
    d.text((bx, 312), "3-year grace period", font=font(FONT_R, 12), fill=mute)
    label_chip(base, "South Korea · crypto bill", xy=(420, 14))
    return base, {"kind": "composite", "sources": [
        {"file": "Flag_of_South_Korea.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Flag_of_South_Korea.svg", "credit": "Flag of South Korea"},
        {"file": "FSC press release, Nov. 24, 2026", "license": "Facts cited", "url": "https://www.fsc.go.kr/comm/getFile?fileNo=2&fileTy=ATTACH&srvcId=BBSTY1&upperNo=88199", "credit": "Financial Services Commission (Korea)"},
    ], "note": "Editorial diagram; flag for identification; no endorsement by the FSC implied."}


def thumb_krak_credit_cards():
    """Light lavender illustration: two drawn credit cards (generic editorial drawing, not the real card design)
    with the Kraken app icon (official press asset) and the Bitcoin logo (public domain), plus facts from
    Payward's Nov. 24, 2026 statement to The Block (up to 4% cashback, $350 to $5,000 USDC deposit, early 2027)."""
    icon = Image.open(fetch(KRAKEN_ICON, CACHE/"kraken-app-icon-purple.svg")).convert("RGBA")
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(245, 242, 255), bottom=(226, 219, 250))
    ink, mute, purple, deep = (30, 27, 75), (88, 80, 130), (112, 66, 255), (52, 30, 140)

    def card(box, top, bottom, title, sub, top_title=False):
        x0, y0, x1, y1 = box
        w, h = round((x1 - x0) * S), round((y1 - y0) * S)
        layer = gradient_bg(w, h, top=top, bottom=bottom).convert("RGBA")
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=round(14 * S), fill=255)
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        Draw(shadow).rounded_rectangle([x0 + 4, y0 + 8, x1 + 4, y1 + 8], radius=14, fill=(40, 20, 90, 70))
        b = Image.alpha_composite(base.convert("RGBA"), shadow)
        b.paste(layer, sz((x0, y0)), mask)
        base.paste(b.convert("RGB"))
        d = Draw(base)
        d.rounded_rectangle([x0 + 22, y0 + 58, x0 + 62, y0 + 88], radius=6, fill=(236, 201, 120), outline=(190, 150, 70))
        d.line([(x0 + 22, y0 + 73), (x0 + 62, y0 + 73)], fill=(190, 150, 70), width=1)
        d.text((x0 + 22, y0 + 18), "krak", font=font(FONT_B, 22), fill=WHITE)
        if top_title:
            tw = d.textlength(title, font=font(FONT_B, 13))
            d.text((x1 - 18 - tw, y0 + 24), title, font=font(FONT_B, 13), fill=WHITE)
            sw = d.textlength(sub, font=font(FONT_R, 10))
            d.text((x1 - 18 - sw, y0 + 42), sub, font=font(FONT_R, 10), fill=(225, 215, 255))
        else:
            d.text((x0 + 22, y1 - 46), title, font=font(FONT_B, 15), fill=WHITE)
            d.text((x0 + 22, y1 - 26), sub, font=font(FONT_R, 11), fill=(225, 215, 255))

    card((40, 92, 300, 252), (150, 110, 255), (88, 40, 200), "CREDIT CARD", "for established credit", top_title=True)
    card((96, 150, 356, 310), (60, 40, 120), (24, 16, 60), "SECURED CARD", "backed by a USDC deposit")
    d = Draw(base)
    paste_contain(base, icon, (40, 26, 50, 50), pad=0)
    d = Draw(base)
    d.text((100, 30), "Krak by Kraken", font=font(FONT_B, 18), fill=ink)
    d.text((100, 54), "U.S. credit card waitlist · Nov. 24, 2026", font=font(FONT_R, 12), fill=mute)
    # facts column
    x = 392
    disc = Image.new("RGBA", sz((58, 58)), (0, 0, 0, 0)); ImageDraw.Draw(disc).ellipse([0, 0, disc.width - 1, disc.height - 1], fill=(255, 255, 255, 255))
    base.paste(disc.convert("RGB"), sz((x, 96)), disc)
    paste_contain(base, btc, (x, 96, 58, 58), pad=4)
    d = Draw(base)
    d.text((x + 70, 96), "Up to 4%", font=font(FONT_B, 30), fill=deep)
    d.text((x + 70, 134), "cashback in USD or BTC", font=font(FONT_R, 12), fill=mute)
    rows = [("$350 to $5,000", "USDC deposit backs the secured card"), ("$6.29 / month", "Krakpass, billed yearly"), ("Early 2027", "expected shipping; APR not yet set")]
    for i, (big, small) in enumerate(rows):
        y = 180 + i * 54
        d.rounded_rectangle([x, y, x + 6, y + 40], radius=3, fill=purple)
        d.text((x + 16, y), big, font=font(FONT_B, 18), fill=ink)
        d.text((x + 16, y + 24), small, font=font(FONT_R, 11), fill=mute)
    d.text((40, 330), "Illustration, not the actual card design", font=font(FONT_R, 10), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Kraken app icon (SVG)", "license": "Official press asset", "url": "https://www.kraken.com/press/kraken-images", "credit": "Kraken / Payward"},
        {"file": "Bitcoin.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "Payward statement via The Block, Nov. 24, 2026", "license": "Facts cited", "url": "https://www.theblock.co/news/business/2026-11-24-kraken-krak-early-2027-launch-us-credit-cards-bitcoin-cashback-usdc-collateral-445498", "credit": "Payward / The Block"},
    ], "note": "Editorial illustration; cards are drawn by PlainBTC and are not the real card design; trademarks belong to their owners."}



def thumb_fidelity_defi_tokens():
    """Light green editorial board: official Aave (public domain), Chainlink (CC BY 4.0) and Uniswap (GPLv3)
    logos from Wikimedia Commons as the three new tokens, plus Fidelity Crypto's coin list and fee facts
    from Fidelity's help pages (Nov. 24, 2026). No Fidelity logo used."""
    aave = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/6/6a/Aave_logo_%282024%29.png", CACHE/"aave-logo-2024.png")).convert("RGBA")
    link = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/2/22/Chainlink_logo_-_Blue.svg", CACHE/"chainlink-logo-blue.svg")).convert("RGBA")
    uni = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/e/e7/Uniswap_Logo.svg", CACHE/"uniswap-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(240, 248, 241), bottom=(214, 236, 218))
    d = Draw(base)
    ink, mute, green, deep = (20, 40, 28), (70, 95, 80), (54, 135, 39), (25, 85, 30)
    d.text((28, 22), "Fidelity Crypto", font=font(FONT_B, 24), fill=deep)
    d.text((28, 54), "New on Nov. 24, 2026", font=font(FONT_R, 13), fill=mute)
    tiles = [(aave, "AAVE", "lending"), (link, "LINK", "price data"), (uni, "UNI", "token swaps")]
    for i, (logo, tick, what) in enumerate(tiles):
        x0 = 28 + i * 140; y0 = 88
        d.rounded_rectangle([x0, y0, x0 + 126, y0 + 150], radius=14, fill=(255, 255, 255), outline=(190, 215, 195), width=2)
        d.rounded_rectangle([x0 + 8, y0 - 10, x0 + 52, y0 + 10], radius=9, fill=green)
        d.text((x0 + 17, y0 - 8), "NEW", font=font(FONT_B, 11), fill=WHITE)
        paste_contain(base, logo, (x0 + 10, y0 + 22, 106, 72), pad=4)
        d = Draw(base)
        tw = d.textlength(tick, font=font(FONT_B, 20))
        d.text((x0 + 63 - tw / 2, y0 + 100), tick, font=font(FONT_B, 20), fill=ink)
        ww = d.textlength(what, font=font(FONT_R, 11))
        d.text((x0 + 63 - ww / 2, y0 + 126), what, font=font(FONT_R, 11), fill=mute)
    # full coin list chips
    d.text((28, 262), "Now tradable: 7 coins + FIDD stablecoin", font=font(FONT_B, 13), fill=ink)
    x = 28
    for c in ["BTC", "ETH", "SOL", "LTC", "AAVE", "LINK", "UNI", "FIDD"]:
        f = font(FONT_B, 12); w = d.textlength(c, font=f) + 18
        new = c in ("AAVE", "LINK", "UNI")
        d.rounded_rectangle([x, 286, x + w, 310], radius=11, fill=green if new else (255, 255, 255), outline=green, width=1)
        d.text((x + 9, 291), c, font=f, fill=WHITE if new else deep)
        x += w + 7
    # facts column
    fx = 462
    rows = [("1%", "fee per buy or sell"), ("$1", "smallest trade"), ("$1M", "max order per new token"), ("Not in OR", "Oregon: no new tokens")]
    for i, (big, small) in enumerate(rows):
        y = 40 + i * 70
        d.rounded_rectangle([fx, y, fx + 6, y + 48], radius=3, fill=green)
        d.text((fx + 16, y), big, font=font(FONT_B, 24), fill=deep)
        d.text((fx + 16, y + 30), small, font=font(FONT_R, 11), fill=mute)
    d.text((fx, 322), "Logos: Wikimedia Commons", font=font(FONT_R, 10), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Aave logo (2024).png", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Aave_logo_(2024).png", "credit": "Aave"},
        {"file": "Chainlink logo - Blue.svg", "license": "CC BY 4.0", "url": "https://commons.wikimedia.org/wiki/File:Chainlink_logo_-_Blue.svg", "credit": "Chainlink Foundation"},
        {"file": "Uniswap Logo.svg", "license": "GPLv3", "url": "https://commons.wikimedia.org/wiki/File:Uniswap_Logo.svg", "credit": "Uniswap Labs"},
        {"file": "Fidelity Crypto help pages, Nov. 24, 2026", "license": "Facts cited", "url": "https://www.fidelity.com/crypto/help/trading/trading-basics", "credit": "Fidelity Digital Assets"},
    ], "note": "Editorial composite; logos for identification only; no endorsement by Fidelity, Aave, Chainlink or Uniswap implied."}


def thumb_coldcard_weak_seeds():
    """Dark slate illustration: a generic hardware wallet drawn by PlainBTC (not the real Coldcard design),
    a die for private dice rolls, and entropy bars (40 / 72 / 128 bits) from Coinkite's Nov. 23, 2026 postmortem."""
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(30, 41, 59), bottom=(10, 14, 22))
    d = Draw(base)
    teal, red, amber, green, ink = (45, 212, 191), (248, 113, 113), (251, 146, 60), (52, 211, 153), (226, 232, 240)
    # device body
    d.rounded_rectangle([42, 70, 212, 320], radius=18, fill=(51, 65, 85), outline=(100, 116, 139), width=3)
    d.rounded_rectangle([60, 92, 194, 170], radius=6, fill=(15, 23, 42), outline=(71, 85, 105), width=2)
    words = ["1 ·····", "2 ·····", "3 ·····", "...", "24 ····"]
    for i, w in enumerate(words):
        d.text((70, 98 + i * 14), w, font=font(FONT_R, 10), fill=teal)
    for r in range(4):
        for c in range(3):
            x = 68 + c * 42; y = 186 + r * 31
            d.rounded_rectangle([x, y, x + 34, y + 24], radius=5, fill=(71, 85, 105))
            d.text((x + 13, y + 5), str((r * 3 + c + 1) % 10) if r < 3 else ["X", "0", "OK"][c][:2], font=font(FONT_B, 11), fill=ink)
    # die
    d.rounded_rectangle([170, 270, 230, 330], radius=10, fill=(248, 250, 252), outline=(148, 163, 184), width=2)
    for (px, py) in [(184, 284), (216, 284), (200, 300), (184, 316), (216, 316)]:
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(15, 23, 42))
    # bitcoin badge
    disc = Image.new("RGBA", sz((46, 46)), (0, 0, 0, 0)); ImageDraw.Draw(disc).ellipse([0, 0, disc.width - 1, disc.height - 1], fill=(255, 255, 255, 255))
    base.paste(disc.convert("RGB"), sz((190, 46)), disc)
    paste_contain(base, btc, (190, 46, 46, 46), pad=3)
    d = Draw(base)
    # entropy bars
    x0 = 270
    d.text((x0, 40), "Seed randomness", font=font(FONT_B, 22), fill=WHITE)
    d.text((x0, 70), "Coinkite estimate, bits", font=font(FONT_R, 13), fill=(148, 163, 184))
    bars = [("Mk2 / Mk3 (affected)", 40, red), ("Mk4 / Mk5 / Q (affected)", 72, amber), ("Intended target", 128, green)]
    maxw = 300
    for i, (lab, v, col) in enumerate(bars):
        y = 110 + i * 64
        d.text((x0, y), lab, font=font(FONT_R, 12), fill=ink)
        d.rounded_rectangle([x0, y + 20, x0 + maxw, y + 42], radius=8, fill=(30, 41, 59))
        d.rounded_rectangle([x0, y + 20, x0 + maxw * v / 128, y + 42], radius=8, fill=col)
        d.text((x0 + maxw * v / 128 + 8 if v < 128 else x0 + maxw - 70, y + 22), f"{v} bits", font=font(FONT_B, 14), fill=WHITE if v == 128 else col)
    d.text((x0, 300), "Mar 2021 to Jul 2026 firmware", font=font(FONT_R, 12), fill=(148, 163, 184))
    d.text((270, 330), "Illustration, not the actual device", font=font(FONT_R, 10), fill=(100, 116, 139))
    label_chip(base, "Wallet security", xy=(42, 22))
    return base, {"kind": "composite", "sources": [
        {"file": "Bitcoin.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
        {"file": "Coinkite postmortem, Nov. 23, 2026", "license": "Facts cited", "url": "https://blog.coinkite.com/reports/coldcard-seed-generation-incident-postmortem-2026-11-23.pdf", "credit": "Coinkite"},
    ], "note": "Editorial illustration drawn by PlainBTC; not the real Coldcard design; trademarks belong to their owners."}


def thumb_btc_58k_pce_month():
    """Sand-colored 'scorecard': bitcoin's 2026 month-by-month change from Kraken daily closes (frozen Nov 25, 2026
    08:04 CST in chart-data.json), November (to date) highlighted as the worst month of the year, plus the October PCE figure."""
    data = json.loads((I18N / "bitcoin-58000-pce-inflation-3-8-percent-eighth-weekly-loss-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    months = data["monthly_2026_pct"]
    labels = [m[0] for m in months]; vals = [m[1] for m in months]
    bg, ink = "#f5efe3", "#1f2937"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.06, 0.10, 0.60, 0.58]); ax.set_facecolor(bg)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#9ca3af")
    cols = ["#16a34a" if v > 0 else "#f87171" for v in vals]; cols[-1] = "#b91c1c"
    ax.bar(labels, vals, color=cols, width=0.68)
    ax.axhline(0, color="#6b7280", linewidth=0.8)
    ax.tick_params(colors="#4b5563", labelsize=6.5, length=0)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.grid(True, axis="y", color="#e5dccb", linewidth=0.6); ax.set_axisbelow(True)
    ax.text(len(vals) - 1, vals[-1] - 1.5, f"{vals[-1]:.0f}%", ha="center", va="top", color="#7f1d1d", fontsize=8, fontweight="bold")
    ax.set_ylim(min(vals) - 7, max(vals) + 5)
    fig.text(0.06, 0.88, "Bitcoin, month by month in 2026", color=ink, fontsize=12.5, fontweight="bold", va="center")
    fig.text(0.06, 0.79, "Change in Kraken BTC/USD closes · Nov. through Nov. 25", color="#6b7280", fontsize=7.5, va="center")
    # right column: PCE + price facts
    fig.text(0.72, 0.66, "3.8%", color="#b45309", fontsize=30, fontweight="bold", va="center")
    fig.text(0.72, 0.53, "October PCE inflation", color=ink, fontsize=9, fontweight="bold", va="center")
    fig.text(0.72, 0.465, "core 3.3% (forecast 3.2%)", color="#6b7280", fontsize=7.5, va="center")
    fig.text(0.72, 0.33, "$58,000", color="#7f1d1d", fontsize=19, fontweight="bold", va="center")
    fig.text(0.72, 0.235, "BTC on Kraken, Nov. 25", color="#6b7280", fontsize=7.5, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    im = Image.open(buf).convert("RGB")
    return im, {"kind": "chart", "sources": [
        {"file": "Kraken OHLC XBTUSD interval=1440 (frozen in chart-data.json)", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Month-end BTC/USD closes Dec. 2025 to Oct. 2026 and the Nov. 25, 2026 08:04 CST price, from Kraken"},
        {"file": "October 2026 PCE price index", "license": "Facts cited", "url": "https://www.cnbc.com/2026/11/25/pce-inflation-report-october-2026.html", "credit": "U.S. Commerce Department via CNBC"},
    ]}


def thumb_bullpen_takeover():
    """Plum diagram drawn by PlainBTC: a pasted private key -> an app account -> the imported wallet -> $2.57M moved
    to Arbitrum (Lookonchain via The Block), with Bullpen's own figures (19 beta accounts, 99.8% from one account). No logos."""
    base = gradient_bg(top=(59, 7, 100), bottom=(17, 6, 33))
    d = Draw(base)
    ink, mute, pink, amber, red = (250, 245, 255), (216, 180, 254), (244, 114, 182), (251, 191, 36), (248, 113, 113)
    d.text((30, 26), "Imported key = shared risk", font=font(FONT_B, 24), fill=ink)
    d.text((30, 60), "How 19 old Bullpen beta accounts were drained", font=font(FONT_R, 13), fill=mute)
    # nodes
    boxes = [(30, "Private key", "pasted into app"), (190, "App account", "taken over"), (350, "Wallet", "emptied")]
    for i, (x, t1, t2) in enumerate(boxes):
        d.rounded_rectangle([x, 104, x + 130, 196], radius=14, fill=(46, 16, 72), outline=pink if i == 1 else (126, 87, 194), width=2)
        tw = d.textlength(t1, font=font(FONT_B, 15)); d.text((x + 65 - tw / 2, 160), t1, font=font(FONT_B, 15), fill=ink)
        tw = d.textlength(t2, font=font(FONT_R, 11)); d.text((x + 65 - tw / 2, 180), t2, font=font(FONT_R, 11), fill=mute)
        if i < 2:
            ax0 = x + 134; ax1 = x + 158
            d.line([(ax0, 150), (ax1 - 8, 150)], fill=amber, width=3)
            d.polygon([(ax1 - 10, 143), (ax1, 150), (ax1 - 10, 157)], fill=amber)
    # icons: key
    d.ellipse([70, 116, 92, 138], outline=amber, width=4)
    d.line([(92, 127), (122, 127)], fill=amber, width=4); d.line([(114, 127), (114, 137)], fill=amber, width=3); d.line([(121, 127), (121, 135)], fill=amber, width=3)
    # person with broken lock
    d.ellipse([244, 112, 264, 132], fill=(196, 181, 253)); d.pieslice([236, 132, 272, 168], 180, 360, fill=(196, 181, 253))
    d.rounded_rectangle([270, 128, 290, 146], radius=3, fill=red); d.arc([272, 114, 288, 134], 200, 330, fill=red, width=3)
    # wallet
    d.rounded_rectangle([392, 116, 438, 146], radius=6, fill=(126, 87, 194)); d.rounded_rectangle([420, 124, 442, 138], radius=4, fill=(167, 139, 250)); d.ellipse([426, 128, 432, 134], fill=(46, 16, 72))
    # arrow to amount
    d.line([(486, 150), (512, 150)], fill=red, width=3); d.polygon([(510, 143), (520, 150), (510, 157)], fill=red)
    d.text((526, 118), "$2.57M", font=font(FONT_B, 22), fill=red)
    d.text((526, 148), "to Arbitrum", font=font(FONT_R, 12), fill=mute)
    d.text((526, 166), "in USDC", font=font(FONT_R, 12), fill=mute)
    # stats chips
    px = 30; f = font(FONT_B, 13)
    for t in ("19 beta accounts (2024)", "99.8% from one account", "ANSEM about \u221255%"):
        w = d.textlength(t, font=f) + 24
        d.rounded_rectangle([px, 230, px + w, 260], radius=14, fill=(40, 10, 60), outline=pink, width=2)
        d.text((px + 12, 237), t, font=f, fill=ink); px += w + 10
    d.text((30, 290), "Bullpen: \u201cany wallet imported into those accounts was exposed too\u201d", font=font(FONT_R, 13), fill=(233, 213, 255))
    d.text((30, 330), "Diagram by PlainBTC · figures: Bullpen on X, Lookonchain via The Block", font=font(FONT_R, 10), fill=(167, 139, 250))
    return base, {"kind": "diagram", "sources": [
        {"file": "Bullpen posts on X, Nov. 24-25, 2026", "license": "Facts cited", "url": "https://x.com/BullpenFi/status/2125314569136463949", "credit": "Bullpen"},
        {"file": "The Block, Nov. 24, 2026", "license": "Facts cited", "url": "https://www.theblock.co/news/defi/2026-11-24-ansem-denies-involvement-2-57-million-wallet-drain-black-bull-creator-coin-plummets-55-445705", "credit": "Lookonchain via The Block"},
    ], "note": "Editorial diagram drawn by PlainBTC; no company logos used."}


def thumb_doj_scam_surge():
    """Deep-teal 'case board': DOJ seal (public domain) beside the anti-scam surge figures from the DOJ's Nov. 24, 2026
    release (800+ defendants, 400+ cases, 85 districts, 30 extradited, $1B+ stolen crypto frozen in Southeast Asia),
    plus a drawn phone showing a fake 'trading app' with a withdraw-fee trap. No outlet photos."""
    doj = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/5/54/Seal_of_the_United_States_Department_of_Justice.svg", CACHE/"doj-seal.svg")).convert("RGBA")
    base = gradient_bg(top=(6, 78, 89), bottom=(4, 30, 38))
    d = Draw(base)
    ink, mute, mint, amber, red = (240, 253, 250), (153, 205, 200), (94, 234, 212), (252, 211, 77), (248, 113, 113)
    # seal on a white disc
    disc = Image.new("RGBA", sz((150, 150)), (0, 0, 0, 0)); ImageDraw.Draw(disc).ellipse([0, 0, disc.width - 1, disc.height - 1], fill=(255, 255, 255, 255))
    base.paste(disc.convert("RGB"), sz((30, 46)), disc)
    paste_contain(base, doj, (30, 46, 150, 150), pad=6)
    d = Draw(base)
    # drawn phone with fake trading app
    px, py = 62, 214
    d.rounded_rectangle([px, py, px + 86, py + 132], radius=12, fill=(15, 23, 42), outline=(94, 234, 212), width=2)
    d.rounded_rectangle([px + 7, py + 12, px + 79, py + 118], radius=6, fill=(30, 41, 59))
    chart = [(px + 12, py + 70), (px + 24, py + 62), (px + 36, py + 66), (px + 48, py + 46), (px + 60, py + 40), (px + 72, py + 24)]
    d.line(chart, fill=(52, 211, 153), width=2)
    d.text((px + 12, py + 16), "\"Profits\"", font=font(FONT_B, 11), fill=(52, 211, 153))
    d.rounded_rectangle([px + 12, py + 84, px + 74, py + 108], radius=6, fill=red)
    d.text((px + 17, py + 86), "Withdraw", font=font(FONT_B, 9), fill=WHITE)
    d.text((px + 17, py + 97), "fee: pay first", font=font(FONT_R, 7), fill=WHITE)
    # right column: figures
    x0 = 214
    d.text((x0, 34), "Largest-ever DOJ scam crackdown", font=font(FONT_B, 19), fill=ink)
    d.text((x0, 62), "Since March 6, 2026", font=font(FONT_R, 13), fill=mute)
    d.text((x0, 88), "800+", font=font(FONT_B, 58), fill=mint)
    bw = d.textlength("800+", font=font(FONT_B, 58)) + 14
    d.text((x0 + bw, 110), "defendants", font=font(FONT_B, 20), fill=ink)
    d.text((x0 + bw, 138), "in 400+ cases", font=font(FONT_R, 13), fill=mute)
    rows = [("$1B+", "stolen crypto frozen in Southeast Asia", amber),
            ("85", "federal districts took part", mint),
            ("30", "defendants extradited to the U.S.", mint)]
    for i, (big, small, col) in enumerate(rows):
        y = 184 + i * 46
        d.rounded_rectangle([x0, y, x0 + 5, y + 36], radius=2, fill=col)
        d.text((x0 + 14, y + 2), big, font=font(FONT_B, 22), fill=col)
        d.text((x0 + 92, y + 9), small, font=font(FONT_R, 12), fill=ink)
    d.text((x0, 326), "Source: U.S. Department of Justice, Nov. 24, 2026 · seal: public domain", font=font(FONT_R, 10), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Seal_of_the_United_States_Department_of_Justice.svg", "license": "Public domain (U.S. government insignia)", "url": "https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Department_of_Justice.svg", "credit": "U.S. Department of Justice"},
        {"file": "DOJ release, Nov. 24, 2026", "license": "Facts cited", "url": "https://www.justice.gov/opa/pr/justice-department-announces-largest-ever-crackdown-scammers-targeting-over-800-defendants", "credit": "U.S. Department of Justice"},
        {"file": "phone illustration", "license": "PlainBTC original", "url": "", "credit": "PlainBTC"},
    ], "note": "Editorial composite; seal for identification only; no endorsement by DOJ implied. The phone is a generic illustration of a fake trading app."}


def thumb_nvidia_settlement():
    """Black and green: Nvidia logo (Wikimedia, identification only) on a white plate, a generic graphics card drawn by
    PlainBTC, the $290M settlement figure and a 2018 to 2026 case strip (The Block; Kessler Topaz, Nov. 25, 2026)."""
    nv = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/2/21/Nvidia_logo.svg", CACHE/"nvidia-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(24, 28, 22), bottom=(6, 8, 6))
    d = Draw(base)
    green, ink, mute = (118, 185, 0), (244, 247, 240), (163, 176, 150)
    d.rounded_rectangle([24, 26, 214, 84], radius=12, fill=(255, 255, 255))
    paste_contain(base, nv, (30, 30, 178, 50), pad=4)
    d = Draw(base)
    # generic GPU illustration
    gx, gy = 30, 118
    d.rounded_rectangle([gx, gy, gx + 280, gy + 118], radius=10, fill=(38, 44, 36), outline=(90, 100, 84), width=2)
    for k in range(2):
        cx = gx + 76 + k * 128; cy = gy + 59
        d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], fill=(18, 20, 17), outline=(110, 120, 104), width=2)
        for a in range(0, 360, 45):
            import math
            ex = cx + 38 * math.cos(math.radians(a)); ey = cy + 38 * math.sin(math.radians(a))
            d.line([(cx, cy), (ex, ey)], fill=(70, 78, 66), width=4)
        d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=green)
    d.rectangle([gx + 30, gy + 118, gx + 200, gy + 130], fill=(196, 160, 60))
    for k in range(18):
        d.line([(gx + 36 + k * 9, gy + 120), (gx + 36 + k * 9, gy + 129)], fill=(140, 110, 30), width=2)
    d.text((gx, gy + 142), "Gaming GPUs sold to crypto miners, 2017-18", font=font(FONT_R, 11), fill=mute)
    # right: figure
    x0 = 340
    d.text((x0, 34), "Proposed settlement", font=font(FONT_B, 17), fill=mute)
    d.text((x0, 58), "$290M", font=font(FONT_B, 62), fill=green)
    d.text((x0, 136), "Investor class action over", font=font(FONT_R, 14), fill=ink)
    d.text((x0, 156), "crypto mining sales", font=font(FONT_R, 14), fill=ink)
    d.text((x0, 184), "Needs court approval", font=font(FONT_B, 13), fill=(250, 204, 21))
    # case strip
    steps = [("2018", "stock -28.5%"), ("2021", "dismissed"), ("2023", "revived"), ("2026", "deal filed")]
    sx0, sx1, sy = 352, 604, 252
    d.line([(sx0, sy), (sx1, sy)], fill=(80, 90, 74), width=3)
    for i, (yr, t) in enumerate(steps):
        cx = sx0 + (sx1 - sx0) * i / (len(steps) - 1)
        d.ellipse([cx - 7, sy - 7, cx + 7, sy + 7], fill=green if i == len(steps) - 1 else (163, 176, 150))
        tw = d.textlength(yr, font=font(FONT_B, 13)); d.text((cx - tw / 2, sy - 30), yr, font=font(FONT_B, 13), fill=ink)
        tw = d.textlength(t, font=font(FONT_R, 10)); d.text((cx - tw / 2, sy + 14), t, font=font(FONT_R, 10), fill=mute)
    d.text((30, 326), "Sources: The Block; Kessler Topaz, Nov. 25, 2026 · logo: Wikimedia Commons · GPU: illustration", font=font(FONT_R, 10), fill=(120, 132, 110))
    return base, {"kind": "composite", "sources": [
        {"file": "Nvidia_logo.svg", "license": "Public domain (logo)", "url": "https://commons.wikimedia.org/wiki/File:Nvidia_logo.svg", "credit": "NVIDIA"},
        {"file": "Kessler Topaz, Nov. 25, 2026", "license": "Facts cited", "url": "https://www.ktmc.com/news/kessler-topaz-secures-290-million-settlement-for-nvidia-investors-following-victory-at-u-s-supreme-court", "credit": "Kessler Topaz"},
        {"file": "The Block, Nov. 25, 2026", "license": "Facts cited", "url": "https://www.theblock.co/news/regulation/2026-11-25-nvidia-290-million-settlement-crypto-mining-class-action-446709", "credit": "The Block"},
    ], "note": "Editorial composite; logo for identification only; the graphics card is a generic drawing, not an Nvidia product photo."}


def thumb_cbw_direct_deposit():
    """Deep-blue editorial illustration: a phone drawn by PlainBTC (not a Coinbase screenshot) showing the
    paycheck -> USDC on Base flow, with the official Coinbase icon and Circle USDC logo (Wikimedia Commons,
    identification only) and the limits from Coinbase Wallet's Nov. 25, 2026 launch post and help page."""
    cb = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/5/5c/Coinbase_Icon.png", CACHE/"coinbase-icon.png")).convert("RGBA")
    usdc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/4a/Circle_USDC_Logo.svg", CACHE/"circle-usdc-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(10, 40, 110), bottom=(6, 14, 38))
    d = Draw(base)
    ink, mute, cyan, blue = (235, 242, 255), (160, 180, 215), (34, 211, 238), (0, 82, 255)
    # phone
    px, py, pw, ph = 46, 22, 196, 318
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=28, fill=(14, 20, 34), outline=(70, 90, 130), width=3)
    d.rounded_rectangle([px + 74, py + 10, px + 122, py + 18], radius=4, fill=(40, 50, 70))
    d.text((px + 20, py + 34), "Direct Deposit", font=font(FONT_B, 16), fill=ink)
    # paycheck card
    d.rounded_rectangle([px + 16, py + 66, px + pw - 16, py + 122], radius=12, fill=(30, 41, 59))
    d.ellipse([px + 26, py + 76, px + 62, py + 112], fill=(34, 197, 94))
    tw = d.textlength("$", font=font(FONT_B, 22)); d.text((px + 44 - tw / 2, py + 79), "$", font=font(FONT_B, 22), fill=WHITE)
    d.text((px + 72, py + 78), "Paycheck", font=font(FONT_B, 13), fill=ink)
    d.text((px + 72, py + 98), "U.S. dollars", font=font(FONT_R, 11), fill=mute)
    # arrow
    ax = px + pw / 2
    d.line([(ax, py + 130), (ax, py + 160)], fill=cyan, width=4)
    d.polygon([(ax - 9, py + 156), (ax + 9, py + 156), (ax, py + 170)], fill=cyan)
    d.text((ax + 14, py + 140), "1 to 1", font=font(FONT_B, 11), fill=cyan)
    # usdc card
    d.rounded_rectangle([px + 16, py + 176, px + pw - 16, py + 232], radius=12, fill=(30, 41, 59))
    paste_contain(base, usdc, (px + 22, py + 180, 46, 48), pad=2)
    d = Draw(base)
    d.text((px + 72, py + 188), "USDC", font=font(FONT_B, 13), fill=ink)
    d.text((px + 72, py + 208), "on Base", font=font(FONT_R, 11), fill=mute)
    d.rounded_rectangle([px + 16, py + 252, px + pw - 16, py + 284], radius=16, fill=cyan)
    tw = d.textlength("1 to 3 business days", font=font(FONT_B, 11))
    d.text((px + pw / 2 - tw / 2, py + 261), "1 to 3 business days", font=font(FONT_B, 11), fill=(8, 20, 40))
    # right column
    x0 = 286
    d.rounded_rectangle([x0, 28, x0 + 54, 82], radius=12, fill=WHITE)
    paste_contain(base, cb, (x0 + 4, 32, 46, 46), pad=2)
    d = Draw(base)
    d.text((x0 + 68, 32), "Coinbase Wallet", font=font(FONT_B, 22), fill=ink)
    d.text((x0 + 68, 62), "Direct deposit, Nov. 25, 2026", font=font(FONT_R, 12), fill=mute)
    rows = [("$3,000", "per deposit"), ("$10,000", "daily limit"), ("1", "virtual account per user")]
    for i, (big, small) in enumerate(rows):
        y = 110 + i * 66
        d.rounded_rectangle([x0, y, x0 + 6, y + 48], radius=3, fill=cyan)
        d.text((x0 + 18, y - 2), big, font=font(FONT_B, 30), fill=WHITE)
        bw = d.textlength(big, font=font(FONT_B, 30))
        d.text((x0 + 30 + bw, y + 14), small, font=font(FONT_R, 14), fill=mute)
    d.text((x0, 316), "Logos: Wikimedia Commons · phone: illustration", font=font(FONT_R, 10), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Coinbase_Icon.png", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:Coinbase_Icon.png", "credit": "Coinbase"},
        {"file": "Circle_USDC_Logo.svg", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:Circle_USDC_Logo.svg", "credit": "Circle/USDC"},
        {"file": "Coinbase Wallet on X, Nov. 25, 2026", "license": "Facts cited", "url": "https://x.com/CoinbaseWallet/status/2125605435097198999", "credit": "Coinbase Wallet"},
        {"file": "Coinbase Help: Direct deposit in Coinbase Wallet", "license": "Facts cited", "url": "https://help.coinbase.com/en/wallet/managing-account/receive-usd-wallet", "credit": "Coinbase"},
    ], "note": "Editorial composite; logos for identification only; the phone is a PlainBTC drawing, not a Coinbase app screenshot."}


def thumb_ezpz_hype():
    """Mint Hyperliquid board: official Hyperliquid wordmark (Wikimedia Commons, CC BY-SA 4.0), Kraken HYPEUSD
    daily closes Jan 28 - Nov 25, 2026, and the eight EZPZ coins from Dec. 1, 2026 (SEC prospectus supplement)."""
    hl = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/8/8f/Hyperliquid_Logo.png", CACHE/"hyperliquid-logo.png")).convert("RGBA")
    url = "https://api.kraken.com/0/public/OHLC?pair=HYPEUSD&interval=1440"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = next(v for k, v in json.load(r)["result"].items() if k != "last")
    end = datetime(2026, 11, 26, tzinfo=timezone.utc)
    pts = [(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[4])) for r in rows]
    pts = [p for p in pts if p[0] < end]
    xs, closes = [p[0] for p in pts], [p[1] for p in pts]
    bg, deep, teal = "#dbfbf6", "#0b3b33", "#0f9f86"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.07, 0.10, 0.50, 0.50]); ax.set_facecolor(bg)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#7fbfb2")
    ax.tick_params(colors="#2f6b60", labelsize=6.5, length=0)
    ax.grid(True, axis="y", color="#b8eadf", linewidth=0.6)
    ax.plot(xs, closes, color=teal, linewidth=1.6)
    ax.fill_between(xs, closes, min(closes) * 0.9, color=teal, alpha=0.12)
    ax.set_ylim(min(closes) * 0.9, max(closes) * 1.08)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.0f}"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[3, 6, 9]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.text(0.07, 0.66, "HYPE/USD daily close on Kraken, 2026", color="#2f6b60", fontsize=7.5, va="center")
    fig.text(0.62, 0.84, "Joins Franklin's", color=deep, fontsize=12, fontweight="bold", va="center")
    fig.text(0.62, 0.77, "EZPZ crypto ETF", color=deep, fontsize=12, fontweight="bold", va="center")
    fig.text(0.62, 0.69, "on or about Dec. 1, 2026", color="#2f6b60", fontsize=9, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    base = Image.open(buf).convert("RGB")
    paste_contain(base, hl, (30, 22, 300, 70), pad=2)
    d = Draw(base)
    coins = ["BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "XLM", "HYPE"]
    d.text((398, 152), "8 coins from Dec. 1", font=font(FONT_B, 13), fill=(11, 59, 51))
    for i, c in enumerate(coins):
        cx = 398 + (i % 2) * 104; cy = 178 + (i // 2) * 36
        new = c == "HYPE"
        d.rounded_rectangle([cx, cy, cx + 94, cy + 28], radius=13, fill=(15, 159, 134) if new else (255, 255, 255), outline=(15, 159, 134), width=1)
        t = c + (" new" if new else "")
        tw = d.textlength(t, font=font(FONT_B, 12))
        d.text((cx + 47 - tw / 2, cy + 7), t, font=font(FONT_B, 12), fill=WHITE if new else (11, 59, 51))
    d.text((398, 326), "Logo: Wikimedia Commons · data: Kraken, SEC", font=font(FONT_R, 9), fill=(47, 107, 96))
    return base, {"kind": "composite", "sources": [
        {"file": "Hyperliquid Logo.png", "license": "CC BY-SA 4.0", "url": "https://commons.wikimedia.org/wiki/File:Hyperliquid_Logo.png", "credit": "Hyperliquid"},
        {"file": "Kraken OHLC HYPEUSD interval=1440", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Daily HYPE/USD closes Jan 28 - Nov 25, 2026, from Kraken"},
        {"file": "Franklin Crypto Index ETF prospectus supplement, Nov. 25, 2026", "license": "Facts cited", "url": "https://www.sec.gov/Archives/edgar/data/2033807/000207184426001935/draftezpz424b3nov2026.htm", "credit": "Franklin Templeton / SEC EDGAR"},
    ], "note": "Editorial composite; logo for identification only; no endorsement by Hyperliquid or Franklin Templeton implied."}


def thumb_btc60_thanksgiving():
    """Warm autumn (Thanksgiving) board: Kraken BTC/USD hourly closes Nov 24-26, 2026 (frozen in chart-data.json)
    with the $60,000 line, the Nov. 25 intraday low and the 8 a.m. CT price, plus Farside's seven straight
    daily ETF outflows as mini bars. Bitcoin logo from Wikimedia Commons (public domain)."""
    data = json.loads((I18N / "bitcoin-back-above-60000-thanksgiving-etf-outflows-seventh-day-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    hrs = data["hourly"]
    xs = [datetime.fromtimestamp(r[0], tz=timezone.utc) for r in hrs]
    closes = [r[1] for r in hrs]
    lo = min(hrs, key=lambda r: r[2])
    btc = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg", CACHE/"bitcoin-logo.svg")).convert("RGBA")
    bg, deep, rust, mute = "#fbf1e1", "#4a2511", "#c2410c", "#8a5a3c"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.07, 0.12, 0.56, 0.56]); ax.set_facecolor(bg)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#d6b48c")
    ax.tick_params(colors=mute, labelsize=6.5, length=0)
    ax.grid(True, axis="y", color="#efd9b8", linewidth=0.6)
    ax.plot(xs, closes, color=rust, linewidth=1.8)
    ax.fill_between(xs, closes, 56500, color="#f59e0b", alpha=0.16)
    ax.axhline(60000, color="#92400e", linestyle="--", linewidth=0.9)
    ax.text(xs[-14], 59700, "$60,000", color="#92400e", fontsize=6.5, fontweight="bold")
    lx = datetime.fromtimestamp(lo[0], tz=timezone.utc)
    ax.scatter([lx], [lo[2]], color="#7f1d1d", s=14 * S, zorder=3)
    ax.annotate(f"intraday low ${lo[2]:,.0f}", (lx, lo[2]), xytext=(6, -2), textcoords="offset points", color="#7f1d1d", fontsize=6.5, fontweight="bold", va="center")
    ax.set_ylim(56500, 62000)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}K"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.text(0.07, 0.85, "Back above $60K", color=deep, fontsize=15, fontweight="bold", va="center")
    fig.text(0.07, 0.765, "BTC/USD hourly closes on Kraken, Nov. 24 to 26", color=mute, fontsize=7.5, va="center")
    fig.text(0.70, 0.87, f"${closes[-1]:,.0f}", color=rust, fontsize=19, fontweight="bold", va="center")
    fig.text(0.70, 0.79, "Thanksgiving, 8 a.m. CT", color=mute, fontsize=7.5, va="center")
    # ETF outflow mini bars
    flows = data["etf_flows"][1:]
    bx = fig.add_axes([0.70, 0.17, 0.26, 0.40]); bx.set_facecolor(bg)
    bx.bar(range(len(flows)), [f[1] for f in flows], color=["#ef4444"] * (len(flows) - 1) + ["#991b1b"], width=0.7)
    bx.axhline(0, color=mute, linewidth=0.7)
    for s in ("top", "right", "left", "bottom"): bx.spines[s].set_visible(False)
    bx.set_xticks([]); bx.set_yticks([])
    fig.text(0.70, 0.63, "7 days of ETF outflows", color=deep, fontsize=8, fontweight="bold", va="center")
    fig.text(0.70, 0.12, "Nov. 25: -$453M (Farside)", color=mute, fontsize=7, va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    base = Image.open(buf).convert("RGB")
    paste_contain(base, btc, (566, 14, 58, 58), pad=2)
    return base, {"kind": "composite", "sources": [
        {"file": "Kraken OHLC XBTUSD interval=60 (frozen in chart-data.json)", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Hourly BTC/USD closes Nov. 24 to Nov. 26, 2026, from Kraken"},
        {"file": "Farside Investors bitcoin ETF flows", "license": "Facts cited", "url": "https://farside.co.uk/btc/", "credit": "Daily net flows Nov. 17 to Nov. 25, 2026"},
        {"file": "Bitcoin.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Bitcoin.svg", "credit": "Bitcoin logo"},
    ]}


def thumb_flnk_filing():
    """Chainlink-blue board: official Chainlink logo (Wikimedia Commons, CC BY 4.0) on a white tile, a drawn
    'Form S-1' document with the FLNK ticker chip and key filing facts (SEC EDGAR, Nov. 25, 2026), and LINK/USD
    daily closes in 2026 from Kraken (frozen in chart-data.json). No Fidelity logo used."""
    link = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/2/22/Chainlink_logo_-_Blue.svg", CACHE/"chainlink-logo-blue.svg")).convert("RGBA")
    data = json.loads((I18N / "fidelity-files-spot-chainlink-etf-flnk-nov-2026" / "chart-data.json").read_text(encoding="utf-8"))
    xs = [datetime.fromtimestamp(r[0], tz=timezone.utc) for r in data["daily"]]
    ys = [r[1] for r in data["daily"]]
    bg = "#1a2b6b"
    fig = plt.figure(figsize=(6.4, 3.6), dpi=100 * S); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0.53, 0.19, 0.42, 0.29]); ax.set_facecolor(bg)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#4f66b8")
    ax.tick_params(colors="#b9c6f2", labelsize=6, length=0)
    ax.plot(xs, ys, color="#7fa2ff", linewidth=1.4)
    ax.fill_between(xs, ys, min(ys) * 0.9, color="#7fa2ff", alpha=0.15)
    ax.set_ylim(min(ys) * 0.9, max(ys) * 1.05)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.0f}"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.text(0.53, 0.545, f"LINK ${ys[-1]:.2f} on Kraken, Nov. 26", color="#e6ecff", fontsize=8, fontweight="bold", va="center")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=bg); plt.close(fig); buf.seek(0)
    base = Image.open(buf).convert("RGB")
    d = Draw(base)
    # S-1 document illustration
    d.rounded_rectangle([30, 34, 300, 330], radius=10, fill=(250, 251, 255), outline=(200, 210, 240), width=2)
    d.polygon([(262, 34), (300, 72), (262, 72)], fill=(214, 222, 246))
    d.text((48, 52), "FORM S-1", font=font(FONT_B, 22), fill=(26, 43, 107))
    d.text((48, 82), "Filed with the SEC, Nov. 25, 2026", font=font(FONT_R, 11), fill=(90, 105, 150))
    d.text((48, 108), "Fidelity Chainlink Fund", font=font(FONT_B, 14), fill=(20, 30, 70))
    for i, w_ in enumerate([210, 180, 200, 150]):
        d.rounded_rectangle([48, 136 + i * 14, 48 + w_, 142 + i * 14], radius=3, fill=(222, 228, 245))
    d.rounded_rectangle([48, 200, 158, 236], radius=17, fill=(55, 91, 210))
    tw = d.textlength("FLNK", font=font(FONT_B, 20))
    d.text((103 - tw / 2, 206), "FLNK", font=font(FONT_B, 20), fill=(255, 255, 255))
    d.text((168, 210), "on Nasdaq", font=font(FONT_B, 14), fill=(26, 43, 107))
    facts = ["Holds LINK directly", "No staking", "Fee: not yet set"]
    for i, t in enumerate(facts):
        y = 250 + i * 24
        d.ellipse([50, y + 4, 60, y + 14], fill=(55, 91, 210))
        d.text((68, y), t, font=font(FONT_R, 13), fill=(30, 40, 80))
    # Chainlink logo tile
    d.rounded_rectangle([340, 34, 610, 150], radius=12, fill=(255, 255, 255))
    paste_contain(base, link, (350, 44, 250, 96), pad=6)
    d = Draw(base)
    d.text((340, 322), "Logo: Chainlink (Wikimedia Commons) · data: SEC, Kraken", font=font(FONT_R, 9), fill=(185, 198, 242))
    return base, {"kind": "composite", "sources": [
        {"file": "Chainlink logo - Blue.svg", "license": "CC BY 4.0", "url": "https://commons.wikimedia.org/wiki/File:Chainlink_logo_-_Blue.svg", "credit": "Chainlink Foundation"},
        {"file": "Fidelity Chainlink Fund Form S-1, Nov. 25, 2026", "license": "Facts cited", "url": "https://www.sec.gov/Archives/edgar/data/2166611/000119312526477751/d85304ds1.htm", "credit": "SEC EDGAR"},
        {"file": "Kraken OHLC LINKUSD interval=1440 (frozen in chart-data.json)", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Daily LINK/USD closes Dec. 31, 2025 to Nov. 26, 2026, from Kraken"},
    ], "note": "Editorial composite; logo for identification only; no endorsement by Chainlink or Fidelity implied. S-1 drawing is a PlainBTC illustration, not a copy of the filing."}


def thumb_sbr_bill_house():
    """Capitol-style board: official seal of the U.S. House of Representatives (public domain, Wikimedia Commons)
    on a cream tile, a drawn legislative-path stepper for H.R. 8957 (Congress.gov actions, Nov. 24, 2026) and the
    20-year lock from the bill text. No price data."""
    seal = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/1/1a/Seal_of_the_United_States_House_of_Representatives.svg", CACHE/"us-house-seal.svg")).convert("RGBA")
    base = gradient_bg(top=(18, 32, 74), bottom=(9, 16, 40))
    d = Draw(base)
    # faint stripes (flag-like) on the right
    for i in range(7):
        y = 20 + i * 22
        d.rectangle([380, y, 640, y + 10], fill=(24, 40, 88))
    # seal tile
    d.ellipse([28, 40, 208, 220], fill=(246, 241, 228))
    paste_contain(base, seal, (34, 46, 168, 168), pad=4)
    d = Draw(base)
    d.text((236, 52), "H.R. 8957", font=font(FONT_B, 34), fill=WHITE)
    d.text((238, 98), "Strategic Bitcoin Reserve bill", font=font(FONT_R, 16), fill=(203, 213, 225))
    d.rounded_rectangle([236, 132, 470, 196], radius=12, fill=(178, 34, 52))
    d.text((252, 140), "20-year lock", font=font(FONT_B, 26), fill=WHITE)
    d.text((253, 174), "no sales of reserve bitcoin", font=font(FONT_R, 12), fill=(255, 226, 230))
    # legislative path stepper
    steps = [("Introduced", "done"), ("Committee", "done"), ("House vote", "next"), ("Senate", "todo"), ("President", "todo")]
    x0, x1, y = 60, 580, 268
    d.line([(x0, y), (x1, y)], fill=(71, 85, 105), width=4)
    d.line([(x0, y), (x0 + (x1 - x0) * 0.5, y)], fill=ORANGE, width=4)
    for i, (lab, st) in enumerate(steps):
        cx = x0 + (x1 - x0) * i / (len(steps) - 1)
        if st == "done":
            d.ellipse([cx - 13, y - 13, cx + 13, y + 13], fill=ORANGE)
            d.line([(cx - 6, y), (cx - 1, y + 6), (cx + 7, y - 6)], fill=WHITE, width=3)
        elif st == "next":
            d.ellipse([cx - 14, y - 14, cx + 14, y + 14], fill=(18, 32, 74), outline=ORANGE, width=3)
            d.text((cx - 4, y - 10), "?", font=font(FONT_B, 16), fill=ORANGE)
        else:
            d.ellipse([cx - 11, y - 11, cx + 11, y + 11], fill=(51, 65, 85))
        tw = d.textlength(lab, font=font(FONT_B, 13))
        d.text((cx - tw / 2, y + 20), lab, font=font(FONT_B, 13), fill=WHITE if st != "todo" else (148, 163, 184))
    d.text((236, 210), "On the House calendar Nov. 24 · Congress ends Jan. 3", font=font(FONT_R, 11), fill=(203, 213, 225))
    d.text((28, 328), "Seal: U.S. House of Representatives (public domain) · data: Congress.gov", font=font(FONT_R, 9), fill=(148, 163, 184))
    return base, {"kind": "composite", "sources": [
        {"file": "Seal_of_the_United_States_House_of_Representatives.svg", "license": "Public domain (U.S. government insignia)", "url": "https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_House_of_Representatives.svg", "credit": "U.S. House of Representatives"},
        {"file": "H.R. 8957 all actions, Congress.gov", "license": "Facts cited", "url": "https://www.congress.gov/bill/119th-congress/house-bill/8957/all-actions", "credit": "Congress.gov"},
    ], "note": "Editorial composite; seal for identification only; no endorsement implied. Stepper is a PlainBTC illustration of the bill's status."}


def thumb_braiins_hijack():
    """Braiins-purple board: Braiins wordmark cropped from Braiins' official share image (identification only) and a
    drawn diagram of the attack (miner -> forged route -> impostor pool, real pool cut off), with figures from the
    Braiins security alert of Nov. 25, 2026."""
    src = fetch("https://cdn.prod.website-files.com/5e5ee6f9b325a6509259421f/6a880fa23b9035b28d2b738c_og-image_braiins.jpg", CACHE/"braiins-og.jpg")
    mark = Image.open(src).convert("RGB").crop((300, 200, 900, 305))
    base = gradient_bg(top=(30, 16, 70), bottom=(8, 6, 20))
    d = Draw(base)
    d.rounded_rectangle([20, 22, 232, 70], radius=10, fill=(10, 8, 24))
    paste_contain(base, mark, (24, 24, 204, 44), pad=3)
    d = Draw(base)
    d.text((252, 30), "Up to 1.9 EH/s", font=font(FONT_B, 30), fill=ORANGE)
    d.text((254, 70), "hijacked in one episode, Nov. 20", font=font(FONT_R, 14), fill=(221, 214, 254))
    # diagram
    def box(x, y, w, h, title, sub, fill, outline, tcol=WHITE):
        d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=fill, outline=outline, width=2)
        tw = d.textlength(title, font=font(FONT_B, 15))
        d.text((x + w / 2 - tw / 2, y + 12), title, font=font(FONT_B, 15), fill=tcol)
        sw = d.textlength(sub, font=font(FONT_R, 11))
        d.text((x + w / 2 - sw / 2, y + 34), sub, font=font(FONT_R, 11), fill=(196, 181, 253))
    box(28, 150, 150, 60, "1,000+ sites", "miners on Stratum V1", (40, 28, 90), (139, 92, 246))
    box(452, 112, 160, 60, "Real pool", "connection cut", (24, 24, 40), (100, 116, 139), (148, 163, 184))
    box(452, 222, 160, 60, "Impostor pool", "takes the rewards", (90, 20, 36), (248, 113, 113))
    # cut path to real pool (dashed gray with X)
    for i in range(10):
        xa = 182 + i * 27
        d.line([(xa, 168 - i * 2.4), (xa + 14, 168 - (i + 0.5) * 2.4)], fill=(100, 116, 139), width=3)
    d.line([(300, 128), (322, 150)], fill=(248, 113, 113), width=4); d.line([(322, 128), (300, 150)], fill=(248, 113, 113), width=4)
    # forged route to impostor
    d.line([(182, 194), (446, 250)], fill=(248, 113, 113), width=5)
    d.polygon([(446, 250), (430, 238), (426, 256)], fill=(248, 113, 113))
    d.rounded_rectangle([238, 230, 384, 256], radius=8, fill=(15, 10, 30), outline=(248, 113, 113), width=1)
    d.text((248, 236), "forged BGP route", font=font(FONT_B, 12), fill=(254, 202, 202))
    d.text((28, 300), "Fix: Stratum V2 or TLS that checks the pool's certificate", font=font(FONT_B, 13), fill=(134, 239, 172))
    d.text((28, 328), "Logo: Braiins · data: Braiins security alert, Nov. 25, 2026", font=font(FONT_R, 9), fill=(167, 139, 250))
    return base, {"kind": "composite", "sources": [
        {"file": "og-image_braiins.jpg (wordmark crop)", "license": "Logo", "url": "https://braiins.com/", "credit": "Braiins"},
        {"file": "Braiins security alert, Nov. 25, 2026", "license": "Facts cited", "url": "https://braiins.com/blog/bitcoin-hashrate-hijacking-unencrypted-stratum-v1", "credit": "Braiins"},
    ], "note": "Editorial composite; logo for identification only; no endorsement by Braiins implied. Diagram is a PlainBTC illustration."}


def thumb_novatech_judgment():
    """Courtroom-navy board: Great Seal of the State of New York (public domain, Wikimedia Commons) beside the figures
    from the New York Supreme Court order and judgment filed Nov. 24, 2026 and the Attorney General's Nov. 25 release,
    plus a drawn group-chat bubble illustrating how affinity scams spread. No outlet photos."""
    seal = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/c/ca/Seal_of_New_York.svg", CACHE/"ny-state-seal.svg")).convert("RGBA")
    base = gradient_bg(top=(17, 24, 64), bottom=(6, 9, 26))
    d = Draw(base)
    ink, mute, gold, mint, red = (241, 245, 249), (165, 180, 252), (252, 211, 77), (94, 234, 212), (248, 113, 113)
    paste_contain(base, seal, (24, 30, 160, 160), pad=2)
    d = Draw(base)
    # drawn group-chat bubble
    bx, by = 30, 214
    d.rounded_rectangle([bx, by, bx + 150, by + 92], radius=14, fill=(30, 41, 59), outline=(100, 116, 139), width=2)
    d.polygon([(bx + 20, by + 92), (bx + 36, by + 92), (bx + 18, by + 108)], fill=(30, 41, 59))
    d.text((bx + 12, by + 10), "Group chat", font=font(FONT_B, 11), fill=mute)
    d.text((bx + 12, by + 30), "\"Steady high", font=font(FONT_B, 13), fill=ink)
    d.text((bx + 12, by + 48), "returns, invite", font=font(FONT_B, 13), fill=ink)
    d.text((bx + 12, by + 66), "your family!\"", font=font(FONT_B, 13), fill=ink)
    d.line([(bx + 118, by + 40), (bx + 142, by + 64)], fill=red, width=4); d.line([(bx + 142, by + 40), (bx + 118, by + 64)], fill=red, width=4)
    x0 = 206
    d.text((x0, 32), "NovaTech crypto Ponzi judgment", font=font(FONT_B, 18), fill=ink)
    d.text((x0, 58), "New York Supreme Court, filed Nov. 24, 2026", font=font(FONT_R, 12), fill=mute)
    d.text((x0, 80), "$1.37B", font=font(FONT_B, 60), fill=gold)
    bw = d.textlength("$1.37B", font=font(FONT_B, 60)) + 12
    d.text((x0 + bw, 98), "ordered", font=font(FONT_B, 20), fill=ink)
    d.text((x0 + bw, 126), "from the founders", font=font(FONT_R, 13), fill=mute)
    rows = [("$1.13B", "disgorgement", gold), ("$232M", "interest at 9% a year", gold), ("~$6M", "secured so far from 4 promoters", mint)]
    for i, (big, small, col) in enumerate(rows):
        y = 172 + i * 46
        d.rounded_rectangle([x0, y, x0 + 5, y + 36], radius=2, fill=col)
        d.text((x0 + 14, y + 4), big, font=font(FONT_B, 22), fill=col)
        d.text((x0 + 112, y + 11), small, font=font(FONT_R, 13), fill=ink)
    d.text((x0, 324), "Sources: NY court judgment; NY Attorney General · seal: public domain", font=font(FONT_R, 10), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Seal_of_New_York.svg", "license": "Public domain", "url": "https://commons.wikimedia.org/wiki/File:Seal_of_New_York.svg", "credit": "State of New York"},
        {"file": "Order and judgment, People v. Nova Tech Ltd et al., Nov. 24, 2026", "license": "Facts cited", "url": "https://ag.ny.gov/sites/default/files/decisions/new-york-v-nova-tech-ltd-et-al-order-and-judgement-2026.pdf", "credit": "New York Supreme Court"},
        {"file": "NY Attorney General release, Nov. 25, 2026", "license": "Facts cited", "url": "https://ag.ny.gov/press-release/2026/attorney-general-james-wins-13-billion-judgment-against-crypto-scammers-who", "credit": "Office of the New York Attorney General"},
        {"file": "group chat illustration", "license": "PlainBTC original", "url": "", "credit": "PlainBTC"},
    ], "note": "Editorial composite; seal for identification only; no endorsement by the State of New York implied."}


def thumb_zodia_breach():
    """Zodia-green board: Zodia Custody white logo from zodia-custody.com (identification only) and three drawn
    incident cards (Zodia, Cryptio, Bithumb) with facts from Zodia's statement, crypto.news and CoinDesk, Nov. 25-26, 2026."""
    logo = Image.open(fetch("https://zodia-custody.com/wp-content/themes/zodia/images/logo-white.svg", CACHE/"zodia-logo-white.svg")).convert("RGBA")
    base = gradient_bg(top=(6, 52, 48), bottom=(4, 16, 22))
    d = Draw(base)
    ink, mute, mint, amber, red = (236, 253, 245), (153, 211, 196), (110, 231, 183), (252, 211, 77), (248, 113, 113)
    paste_contain(base, logo, (24, 20, 150, 68), pad=2)
    d = Draw(base)
    d.text((196, 28), "Client contact data accessed", font=font(FONT_B, 19), fill=ink)
    d.text((196, 56), "No unauthorized transactions, Zodia says", font=font(FONT_R, 13), fill=mint)
    cards = [
        ("Zodia Custody", ["Nov. 23: probing,", "B2B API offline", "Names + emails seen"], (96, 165, 250), "No funds moved"),
        ("Cryptio", ["AI-assisted break-in", "Tried to move crypto", "with stored keys"], amber, "Attempts failed"),
        ("Bithumb", ["October leak bigger:", "passport numbers,", "bank details"], red, "No crypto stolen"),
    ]
    for i, (name, lines, col, verdict) in enumerate(cards):
        x = 24 + i * 202
        d.rounded_rectangle([x, 104, x + 188, 262], radius=12, fill=(8, 30, 34), outline=col, width=2)
        d.text((x + 14, 116), name, font=font(FONT_B, 16), fill=col)
        for j, ln in enumerate(lines):
            d.text((x + 14, 146 + j * 22), ln, font=font(FONT_R, 13), fill=ink)
        d.text((x + 14, 230), verdict, font=font(FONT_B, 13), fill=mint)
    d.rounded_rectangle([24, 280, 616, 314], radius=10, fill=(69, 26, 3))
    d.text((38, 288), "Next risk: phishing. Never share passwords, 2FA codes or keys.", font=font(FONT_B, 13), fill=amber)
    d.text((24, 328), "Logo: Zodia Custody · facts: Zodia statement; crypto.news; CoinDesk, Nov. 25-26, 2026", font=font(FONT_R, 9), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "logo-white.svg", "license": "Logo", "url": "https://zodia-custody.com/", "credit": "Zodia Custody"},
        {"file": "Zodia Custody statement, Nov. 26, 2026", "license": "Facts cited", "url": "https://zodia-custody.com/statement-on-recent-security-incident/", "credit": "Zodia Custody"},
        {"file": "crypto.news, Nov. 26, 2026", "license": "Facts cited", "url": "https://crypto.news/cryptio-ai-attack-attempted-crypto-transfers/", "credit": "crypto.news"},
        {"file": "CoinDesk, Nov. 25, 2026", "license": "Facts cited", "url": "https://www.coindesk.com/tech/2026/11/25/south-korean-crypto-exchange-bithumb-warns-of-phishing-after-deeper-october-breach-probe", "credit": "CoinDesk"},
    ], "note": "Editorial composite; logo for identification only; no endorsement by Zodia Custody implied. Cards are PlainBTC illustrations."}


def thumb_monero_kucoin():
    """Monero-orange board: Monero logo (Wikimedia Commons) and KuCoin logo (Wikimedia Commons), identification only,
    with a mini chart of Kraken XMR/USD daily closes Nov 1 to 26, 2026 and the KuCoin delisting date from KuCoin's notice."""
    monero = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/2/2d/Monero-Logo.svg", CACHE/"monero-logo.svg")).convert("RGBA")
    kucoin = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/3/39/KUCOIN.svg", CACHE/"kucoin-logo.svg")).convert("RGBA")
    url = "https://api.kraken.com/0/public/OHLC?pair=XMRUSD&interval=1440&since=1793404800"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
        rows = next(v for k, v in json.load(r)["result"].items() if k != "last")
    start = datetime(2026, 11, 1, tzinfo=timezone.utc); end = datetime(2026, 11, 27, tzinfo=timezone.utc)
    pts = [(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[4])) for r in rows]
    pts = [p for p in pts if start <= p[0] < end]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    base = gradient_bg(top=(58, 24, 6), bottom=(18, 10, 6))
    d = Draw(base)
    xmr_or, ink, mute, kc = (255, 102, 0), (255, 247, 237), (253, 186, 116), (36, 174, 143)
    # logo tiles
    d.rounded_rectangle([22, 22, 222, 78], radius=12, fill=(255, 255, 255))
    paste_contain(base, monero, (22, 22, 200, 56), pad=8)
    d = Draw(base)
    d.rounded_rectangle([22, 90, 222, 140], radius=12, fill=(14, 22, 20), outline=kc, width=2)
    paste_contain(base, kucoin, (22, 90, 200, 50), pad=10)
    d = Draw(base)
    d.text((248, 24), "XMR trading ends on KuCoin", font=font(FONT_B, 21), fill=ink)
    d.text((248, 54), "Nov. 30, 08:00 UTC", font=font(FONT_B, 30), fill=xmr_or)
    d.text((248, 96), "Withdrawals open until Dec. 31, 08:00 UTC", font=font(FONT_R, 13), fill=mute)
    d.text((248, 116), "Deposits already closed", font=font(FONT_R, 13), fill=mute)
    # mini chart
    fig = plt.figure(figsize=(6.0, 1.6), dpi=100 * S); fig.patch.set_facecolor("#1a0e06")
    ax = fig.add_axes([0.08, 0.16, 0.9, 0.7]); ax.set_facecolor("#1a0e06")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color("#7c4a20")
    ax.tick_params(colors="#fdba74", labelsize=6.5, length=0)
    ax.grid(True, axis="y", color="#4a2a12", linewidth=0.6)
    ax.plot(xs, ys, color="#ff6600", linewidth=2.2)
    ax.fill_between(xs, ys, min(ys) * 0.96, color="#ff6600", alpha=0.15)
    ax.scatter([xs[-1]], [ys[-1]], s=28, color="#f87171", zorder=5, edgecolors="white", linewidths=1)
    ax.set_ylim(min(ys) * 0.96, max(ys) * 1.04)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.set_title("XMR daily close on Kraken, Nov. 1 to 26 (UTC)", color="#fed7aa", fontsize=7.5, loc="left", pad=4)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100 * S, facecolor=fig.get_facecolor()); plt.close(fig); buf.seek(0)
    ch = Image.open(buf).convert("RGB")
    base.paste(ch, sz((20, 156)))
    d = Draw(base)
    d.text((24, 324), "Logos: Monero, KuCoin (Wikimedia Commons) · prices: Kraken · date: KuCoin notice, Nov. 26, 2026", font=font(FONT_R, 9), fill=(251, 146, 60))
    return base, {"kind": "composite", "sources": [
        {"file": "Monero-Logo.svg", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:Monero-Logo.svg", "credit": "The Monero Project"},
        {"file": "KUCOIN.svg", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:KUCOIN.svg", "credit": "KuCoin"},
        {"file": "Kraken OHLC XMRUSD interval=1440", "license": "Kraken public API", "url": "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data", "credit": "Daily XMR/USD closes Nov 1 to 26, 2026, from Kraken"},
        {"file": "KuCoin Will Delist Monero (XMR) on 2026-11-30", "license": "Facts cited", "url": "https://www.kucoin.com/announcement/en-kucoin-will-delist-xmr-on-2026-11-30", "credit": "KuCoin"},
    ], "note": "Editorial composite; logos for identification only; no endorsement implied."}


def thumb_binance_restored():
    """Binance-black board: Binance logo (Wikimedia Commons, identification only) over a drawn four-step progress track
    (Oct. 29 hack to Nov. 26 full lift), dates and figures from Binance's Nov. 26 update, CoinDesk and Exchange.news."""
    binance = Image.open(fetch("https://upload.wikimedia.org/wikipedia/commons/e/e8/Binance_Logo.svg", CACHE/"binance-logo.svg")).convert("RGBA")
    base = gradient_bg(top=(30, 32, 38), bottom=(11, 14, 17))
    d = Draw(base)
    yel, ink, mute, green, red = (240, 185, 11), (234, 236, 239), (132, 142, 156), (14, 203, 129), (246, 70, 93)
    paste_contain(base, binance, (22, 20, 64, 56), pad=2)
    d = Draw(base)
    d.text((96, 34), "BINANCE", font=font(FONT_B, 24), fill=yel)
    d.text((26, 92), "Withdrawals fully restored", font=font(FONT_B, 32), fill=ink)
    d.text((28, 136), "Suspension from the October hack lifted, Binance says", font=font(FONT_R, 15), fill=mute)
    steps = [("Oct. 29", "Hack: ~$6.3B", red), ("Nov. 1", "Restart begins", yel), ("Nov. 14", "87 networks", yel), ("Nov. 26", "Fully lifted", green)]
    x0, x1, y = 70, 570, 222
    d.rounded_rectangle([x0, y - 5, x1, y + 5], radius=5, fill=(43, 49, 57))
    d.rounded_rectangle([x0, y - 5, x1, y + 5], radius=5, fill=yel)
    for i, (dt_, lab, col) in enumerate(steps):
        cx = x0 + i * (x1 - x0) / 3
        d.ellipse([cx - 14, y - 14, cx + 14, y + 14], fill=col, outline=(11, 14, 17), width=3)
        if i == 3:
            d.line([(cx - 7, y), (cx - 2, y + 6), (cx + 8, y - 6)], fill=(11, 14, 17), width=3)
        tw = d.textlength(dt_, font=font(FONT_B, 15))
        d.text((cx - tw / 2, y - 44), dt_, font=font(FONT_B, 15), fill=ink)
        lw = d.textlength(lab, font=font(FONT_R, 13))
        d.text((cx - lw / 2, y + 24), lab, font=font(FONT_R, 13), fill=col if i in (0, 3) else mute)
    d.rounded_rectangle([26, 276, 614, 312], radius=10, fill=(24, 26, 32), outline=(71, 77, 87), width=1)
    d.text((40, 286), "A few networks still paused for maintenance, which Binance says is unrelated", font=font(FONT_R, 12), fill=ink)
    d.text((26, 324), "Logo: Binance (Wikimedia Commons) · sources: Binance, CoinDesk, Exchange.news", font=font(FONT_R, 9), fill=mute)
    return base, {"kind": "composite", "sources": [
        {"file": "Binance_Logo.svg", "license": "Logo", "url": "https://commons.wikimedia.org/wiki/File:Binance_Logo.svg", "credit": "Binance"},
        {"file": "Service Recovery Update: Withdrawals Recovery Work Complete (2026-11-26)", "license": "Facts cited", "url": "https://www.binance.com/en/support/announcement/detail/95c463396a034f1ab3994814225e6d69", "credit": "Binance"},
        {"file": "CoinDesk, Nov. 27, 2026", "license": "Facts cited", "url": "https://www.coindesk.com/markets/2026/11/27/binance-says-its-withdrawal-suspension-is-over-four-weeks-after-a-usd6-3-billion-hack", "credit": "CoinDesk"},
        {"file": "progress track illustration", "license": "PlainBTC original", "url": "", "credit": "PlainBTC"},
    ], "note": "Editorial composite; logo for identification only; no endorsement by Binance implied."}



BUILDERS = {
    "monero-falls-11-percent-kucoin-delists-xmr-nov-2026": thumb_monero_kucoin,
    "binance-withdrawals-fully-restored-after-6-3-billion-hack-nov-2026": thumb_binance_restored,
    "novatech-founders-ordered-to-pay-1-37-billion-new-york-crypto-ponzi-nov-2026": thumb_novatech_judgment,
    "zodia-custody-data-breach-cryptio-bithumb-phishing-nov-2026": thumb_zodia_breach,
    "house-strategic-bitcoin-reserve-bill-20-year-lock-floor-vote-nov-2026": thumb_sbr_bill_house,
    "braiins-hashrate-hijacking-stratum-v1-1000-mining-sites-nov-2026": thumb_braiins_hijack,
    "bitcoin-back-above-60000-thanksgiving-etf-outflows-seventh-day-nov-2026": thumb_btc60_thanksgiving,
    "fidelity-files-spot-chainlink-etf-flnk-nov-2026": thumb_flnk_filing,
    "coinbase-wallet-direct-deposit-paycheck-usdc-base-nov-2026": thumb_cbw_direct_deposit,
    "franklin-templeton-ezpz-etf-adds-hyperliquid-hype-nov-2026": thumb_ezpz_hype,
    "doj-scam-crackdown-800-defendants-1-billion-crypto-frozen-nov-2026": thumb_doj_scam_surge,
    "nvidia-290-million-settlement-crypto-mining-lawsuit-nov-2026": thumb_nvidia_settlement,
    "bitcoin-58000-pce-inflation-3-8-percent-eighth-weekly-loss-nov-2026": thumb_btc_58k_pce_month,
    "bullpen-hack-ansem-wallet-2-57-million-imported-keys-nov-2026": thumb_bullpen_takeover,
    "fidelity-crypto-adds-aave-link-uni-nov-2026": thumb_fidelity_defi_tokens,
    "coldcard-postmortem-weak-seeds-bitcoin-thefts-nov-2026": thumb_coldcard_weak_seeds,
    "kraken-krak-credit-cards-4-percent-bitcoin-cashback-usdc-secured-nov-2026": thumb_krak_credit_cards,
    "bitcoin-etfs-record-4-71-billion-november-outflows-nov-2026": thumb_etf_nov_record_471,
    "south-korea-crypto-bill-bank-led-stablecoins-ico-20-percent-exchange-cap-nov-2026": thumb_korea_digital_asset_bill,
    "bitcoin-spikes-to-64500-on-huang-return-then-fades-nov-2026": thumb_huang_btc_fade,
    "cftc-staff-bitcoin-ether-stablecoins-count-toward-exchange-reserves-nov-2026": thumb_cftc_crypto_reserves,
    "binance-hires-mandiant-slowmist-verichains-security-review-nov-2026": thumb_binance_security_review,
    "ark-invest-withdraws-coindesk-20-crypto-etfs-nov-2026": thumb_ark_withdraws_cd20_etfs,
    "bitcoin-etfs-1-79-billion-weekly-outflow-fourth-week-nov-2026": thumb_etf_weekly_179,
    "strategy-buys-457-bitcoin-212-million-strc-buyback-nov-2026": thumb_strategy_457_btc,
    "bitcoin-61500-abraxas-capital-1-billion-btc-off-exchanges-nov-2026": thumb_abraxas_withdrawals,
    "fusionist-ace-bridge-exploit-10-quintillion-tokens-nov-2026": thumb_fusionist_ace,
    "trump-memecoin-second-dinner-token-down-99-percent-nov-2026": thumb_trump_dinner,
    "chainflip-loss-12-million-bitcoin-10-percent-bounty-nov-2026": thumb_chainflip_bounty,
    "bitcoin-core-node-stall-bug-ai-found-fix-nov-2026": thumb_core_node_stall,
    "kraken-bitcoin-cad-flash-crash-24250-trades-stand-nov-2026": thumb_kraken_cad_crash,
    "bitcoin-crashes-to-55100-rebounds-above-60000-nov-2026": thumb_btc_55100_rebound,
    "bitcoin-new-2026-low-57661-strategy-shares-sink-nov-2026": thumb_btc_new_2026_low,
    "bitcoin-below-59000-near-2026-low-liquidations-nov-2026": thumb_btc_below_59k_2026_low,
    "senate-passes-death-bets-act-prediction-markets-nov-2026": thumb_death_bets_act,
    "blackrock-ibit-record-541-million-outflow-nov-2026": thumb_ibit_record_outflow,
    "sec-fake-crypto-platforms-37-million-whatsapp-nov-2026": thumb_sec_fake_platforms,
    "bitcoin-below-62000-lowest-since-july-etf-outflows-nov-2026": thumb_btc_below_62k_july,
    "coinbase-crypto-options-non-us-users-deribit-nov-2026": thumb_coinbase_options_intl,
    "threat-disruption-center-crypto-scams-trm-labs-nov-2026": thumb_threat_disruption_center,
    "sky-stablecoin-psm-north-korea-518-million-inca-nov-2026": thumb_sky_psm_illicit,
    "ledger-tampered-wallets-berlin-dubai-nov-2026": thumb_ledger_berlin_dubai,
    "senators-genius-act-state-stablecoin-safe-harbor-nov-2026": thumb_genius_state_safe_harbor,
    "fed-minutes-more-rate-hikes-bitcoin-below-63000-nov-2026": thumb_fed_minutes_btc_63k,
    "binance-abu-dhabi-court-order-frozen-hack-funds-nov-2026": thumb_binance_adgm_order,
    "russia-retail-investors-bitcoin-ether-usdt-300000-ruble-cap-nov-2026": thumb_russia_retail_crypto,
    "mev-brothers-acquitted-25-million-ethereum-bots-nov-2026": thumb_mev_acquittal,
    "cftc-approves-backpack-blockchain-derivatives-exchange-nov-2026": thumb_cftc_backpack,
    "goldman-wells-fargo-double-bitcoin-etf-holdings-13f-nov-2026": thumb_banks_btc_etf_13f,
    "trezor-skladon-shipping-breach-27000-orders-nov-2026": thumb_trezor_skladon,
    "coinbase-borrow-new-york-all-50-states-nov-2026": thumb_coinbase_borrow_ny,
    "optimizely-hack-crypto-address-swap-178-sites-nov-2026": thumb_optimizely_clipper,
    "solana-foundation-coingecko-majority-stake-nov-2026": thumb_coingecko_solana,
    "supreme-court-rejects-custodia-fed-master-account-nov-2026": thumb_custodia_scotus,
    "solana-drops-mainnet-beta-solana-1-0-nov-2026": thumb_solana_1_0,
    "lighter-dex-10-4-million-leaked-api-key-nov-2026": thumb_lighter_api_key,
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
    "bitcoin-below-67000-sixth-weekly-loss-nov-2026": thumb_btc_below_67k,
    "unocoin-hack-bitgo-backup-keys-nov-2026": thumb_unocoin_keys,
    "ether-solana-xrp-lead-selloff-bitcoin-65000-nov-2026": thumb_alt_selloff,
    "binance-reopens-withdrawals-87-networks-nov-2026": thumb_binance_reopen,
    "bitcoin-falls-below-64000-three-month-low-nov-2026": thumb_btc_below_64k,
    "kava-lend-hack-3-8-million-kava-falls-nov-2026": thumb_kava_hack,
    "chainflip-vault-drained-4-86-million-flip-falls-nov-2026": thumb_chainflip_vault_drain,
    "bitcoin-four-month-low-62000-liquidations-nov-2026": thumb_btc_62k_low,
    "coinone-data-breach-support-contractor-passwords-nov-2026": thumb_coinone_breach,
    "stusdt-wind-down-redeem-by-may-2027-nov-2026": thumb_stusdt_wind_down,
    "luxor-commander-hack-bitcoin-miners-hashrate-ocean-nov-2026": thumb_luxor_hashrate_hijack,
    "germany-customs-crypto-seizure-100000-euros-bundestag-nov-2026": thumb_germany_customs_crypto,
    "strategy-buys-485-bitcoin-strive-251-nov-2026": thumb_strategy_485_btc,
    "crypto-fear-greed-index-10-extreme-fear-nov-2026": thumb_fear_greed_10,
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
    im = open_rgb(src)
    if S == 1 and im.width / im.height > W / H + 0.02:
        # wider than 16:9 (1200x630 figure): letterbox instead of cutting off axis labels
        fit = im.resize((W, round(im.height * W / im.width)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (W, H), im.getpixel((2, 2))); canvas.paste(fit, (0, (H - fit.height) // 2))
        im = canvas
    return cover_fit(im), {"kind":"figure-fallback","sources":[{"file":str(src.relative_to(ROOT)),"license":"See article figures","url":"","credit":"Derived from mid-article figure"}]}

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

def og_figure_source(slug: str) -> Path | None:
    """No builder: prefer the article's fact card / timeline / comparison (readable at
    preview size) over its bar charts."""
    d = IMG / slug
    if d.is_dir():
        for pref in ("fact-", "timeline-", "compare-", "chart-"):
            for p in sorted(d.glob(pref + "*")):
                if p.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"}: return p
    return first_figure_source(slug)

def og_path(slug: str) -> Path:
    return OG_DIR / f"{slug}{OG_SUFFIX}.jpg"

def build_og(slug: str) -> bool:
    """Render the article's card-thumb design natively at 1200x630 (no upscaling).

    Same builder as the 640x360 homepage thumb, drawn at S=1.875 (1200x675), then
    trimmed to 630 px tall (15 px top, 30 px bottom). Articles without a builder use
    their first in-article figure (already 1200 px wide).
    """
    global S, DATA_END
    print(f"· og {slug}")
    cred = IMG / slug / "thumb.credits.json"
    DATA_END = None
    if cred.exists():
        g = json.loads(cred.read_text(encoding="utf-8")).get("generated")
        if g: DATA_END = datetime.strptime(g, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    S = OG_W / W
    try:
        im = None
        if slug in BUILDERS:
            try: im, _ = BUILDERS[slug]()
            except Exception as e: print(f"  builder ERROR {e}; using article figure")
        if im is None:
            src = og_figure_source(slug)
            if not src: print("  skip (no visual)"); return False
            out = cover_fit(open_rgb(src), OG_W, OG_H, cy=0.5)
        elif abs(im.width - OG_W) <= 2 and abs(im.height - round(H * S)) <= 2:
            full = cover_fit(im, OG_W, round(H * S))          # 1200x675 design canvas
            out = full.crop((0, 15, OG_W, 15 + OG_H))
        else:
            # matplotlib chart (free aspect): fit whole chart, never crop its title/axes
            out = Image.new("RGB", (OG_W, OG_H), im.convert("RGB").getpixel((2, im.height - 3)))
            paste_contain(out, im, (0, 0, OG_W / S, OG_H / S), pad=6)
        OG_DIR.mkdir(parents=True, exist_ok=True)
        dest = og_path(slug)
        out.convert("RGB").save(dest, "JPEG", quality=86, optimize=True, progressive=True)
        print(f"  wrote {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")
        return True
    finally:
        S, DATA_END = 1.0, None

def published_slugs():
    idx = (ROOT/"index.html").read_text(encoding="utf-8"); seen=[]
    for m in re.finditer(r'href="(?:/articles/|articles/)([a-z0-9-]+)(?:\.html)?"', idx):
        s=m.group(1)
        if s not in seen: seen.append(s)
    return seen

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--og", action="store_true", help="write 1200x630 link previews assets/og/<slug>-v2.jpg instead of thumbs")
    args = ap.parse_args()
    slugs = published_slugs() if args.all or not args.slugs else args.slugs
    ok = sum(1 for s in slugs if (build_og(s) if args.og else build_one(s)))
    print(f"done: {ok}/{len(slugs)}"); return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
