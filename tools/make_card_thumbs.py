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

BUILDERS = {
    "coinbase-occ-national-trust-charter-nov-2026": thumb_occ,
    "fincen-fed-withdraw-250-travel-rule-nov-2026": thumb_fincen,
    "bitcoin-loses-50-week-moving-average-nov-2026": thumb_btc_50w,
    "bitcoin-volatility-liquidations-nov-2026": thumb_liquidations,
    "pnc-coinbase-usdc-payments-pilot-nov-2026": thumb_pnc_usdc,
    "us-midterms-crypto-regulation-etf-outflows": thumb_midterms,
    "how-to-buy-first-bitcoin-coinbase": thumb_howto,
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
