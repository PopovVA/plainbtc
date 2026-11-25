#!/usr/bin/env python3
"""Generate mid-article charts and fact cards for PlainBTC.

Usage:
  python3 tools/make_article_images.py --all
  python3 tools/make_article_images.py <slug>

Outputs under assets/img/<slug>/ (webp preferred, png fallback), writes
i18n/content/<slug>/figures.json with per-language alt/caption strings.

Charts use public CoinGecko market data or figures cited in the article
sources — never invent numbers. Fact cards use Pillow in the PlainBTC
dark navy / bitcoin-orange brand style (same as tools/make_og.py).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "img"
I18N = ROOT / "i18n" / "content"

BG_TOP = (11, 22, 48)
BG_BOTTOM = (7, 14, 32)
ORANGE = (247, 147, 26)
WHITE = (255, 255, 255)
GRAY = (148, 163, 184)
MUTED = (100, 116, 139)
GREEN = (52, 211, 153)
RED = (248, 113, 113)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

LANGS = ["en", "es", "pt", "fr", "de", "ru", "tr", "id", "ja", "ko"]

# Short formulaic caption translations (source names stay Latin).
CAPTION_CHART = {
    "en": "Chart: PlainBTC, data: {src}",
    "es": "Gráfico: PlainBTC, datos: {src}",
    "pt": "Gráfico: PlainBTC, dados: {src}",
    "fr": "Graphique : PlainBTC, données : {src}",
    "de": "Chart: PlainBTC, Daten: {src}",
    "ru": "График: PlainBTC, данные: {src}",
    "tr": "Grafik: PlainBTC, veri: {src}",
    "id": "Grafik: PlainBTC, data: {src}",
    "ja": "チャート: PlainBTC、データ: {src}",
    "ko": "차트: PlainBTC, 데이터: {src}",
}
CAPTION_SOURCE = {
    "en": "Source: {src}",
    "es": "Fuente: {src}",
    "pt": "Fonte: {src}",
    "fr": "Source : {src}",
    "de": "Quelle: {src}",
    "ru": "Источник: {src}",
    "tr": "Kaynak: {src}",
    "id": "Sumber: {src}",
    "ja": "出典: {src}",
    "ko": "출처: {src}",
}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw, text, font, max_w, max_lines=4):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def gradient_bg(w, h):
    img = Image.new("RGB", (w, h), BG_TOP)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def save_image(img: Image.Image, path: Path, max_kb=190) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer webp
    webp = path.with_suffix(".webp")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=82, method=6)
    data = buf.getvalue()
    if len(data) <= max_kb * 1024:
        webp.write_bytes(data)
        path.with_suffix(".png").unlink(missing_ok=True)
        return webp
    # Fallback png optimized / jpeg
    png = path.with_suffix(".png")
    img.save(png, format="PNG", optimize=True)
    if png.stat().st_size > max_kb * 1024:
        jpg = path.with_suffix(".jpg")
        img.convert("RGB").save(jpg, format="JPEG", quality=82, optimize=True)
        png.unlink(missing_ok=True)
        webp.unlink(missing_ok=True)
        return jpg
    webp.unlink(missing_ok=True)
    return png


def fetch_btc_prices(days: int = 90):
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        f"?vs_currency=usd&days={days}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    prices = data["prices"]
    # downsample to ~daily for 90d (CoinGecko returns hourly-ish)
    xs, ys = [], []
    step = max(1, len(prices) // 120)
    for i in range(0, len(prices), step):
        ts, price = prices[i]
        xs.append(ts / 1000.0)
        ys.append(price)
    # always include last
    if prices:
        xs.append(prices[-1][0] / 1000.0)
        ys.append(prices[-1][1])
    return np.array(xs), np.array(ys)


def style_axes(ax, title: str):
    ax.set_facecolor("#0b1630")
    ax.figure.patch.set_facecolor("#0b1630")
    ax.set_title(title, color=f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}",
                 fontsize=15, fontweight="bold", pad=14, loc="left")
    ax.tick_params(colors="#94a3b8", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    ax.grid(True, color="#1e293b", linewidth=0.8, alpha=0.9)
    ax.yaxis.label.set_color("#94a3b8")
    ax.xaxis.label.set_color("#94a3b8")


def make_line_chart(path: Path, xs, ys, title: str, hline=None, hlabel=None,
                    ylabel="USD", w=1200, h=675, date_fmt="%b %d", yfmt=None) -> Path:
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, title)
    import datetime as dt

    dts = [dt.datetime.fromtimestamp(float(t), dt.UTC) for t in xs]
    color = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    ax.plot(dts, ys, color=color, linewidth=2.2)
    ax.fill_between(dts, ys, min(ys) * 0.98, color=color, alpha=0.12)
    if hline is not None:
        ax.axhline(hline, color="#38bdf8", linestyle="--", linewidth=1.4, alpha=0.95)
        if hlabel:
            ax.text(
                dts[int(len(dts) * 0.02)],
                hline * 1.008,
                hlabel,
                color="#38bdf8",
                fontsize=10,
                fontweight="bold",
            )
    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_fmt))
    ax.yaxis.set_major_formatter(yfmt or (lambda x, _p: f"${x:,.0f}"))
    fig.autofmt_xdate(rotation=0, ha="center")
    plt.tight_layout(pad=1.2)
    # brand footer
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    return save_image(img, path)


def make_bar_chart(path: Path, labels, values, title: str, ylabel="",
                   colors=None, w=1200, h=675, value_fmt=None, axis_fmt=None) -> Path:
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, title)
    cols = colors or [f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"] * len(values)
    ax.set_axisbelow(True)
    bars = ax.bar(labels, values, color=cols, width=0.55, edgecolor="#0b1630")
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            (value_fmt(v) if value_fmt else (f"${v:,.0f}M" if abs(v) >= 1 else f"${v:.1f}M")),
            ha="center",
            va="bottom",
            color="#e2e8f0",
            fontsize=11,
            fontweight="bold",
        )
    ax.yaxis.set_major_formatter(axis_fmt or (lambda x, _p: f"${x:,.0f}M"))
    if ylabel:
        ax.set_ylabel(ylabel, color="#94a3b8")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return save_image(Image.open(buf).convert("RGB"), path)


def make_cashout_timing_chart(path: Path, w=1200, h=630) -> Path:
    """Coinbase cash-out timing as ranges, only figures from the article / Coinbase Help:
    ACH 3–5 business days; instant cashout about 30 minutes, up to 24 hours."""
    orange = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, "How long a Coinbase cash-out takes (U.S.)")
    ax.set_axisbelow(True)
    rows = [("Instant cashout\n(eligible cards / RTP banks)", 30 / 1440, 1.0, "#60a5fa", "about 30 minutes, up to 24 hours"),
            ("ACH bank withdrawal", 3.0, 5.0, orange, "3–5 business days")]
    for i, (_lab, lo, hi, col, txt) in enumerate(rows):
        ax.barh(i, hi - lo, left=lo, height=0.5, color=col, edgecolor="#0b1630")
        ax.text(hi + 0.08, i, txt, va="center", ha="left", color="#e2e8f0", fontsize=13, fontweight="bold")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.tick_params(axis="y", labelsize=12, colors="#e2e8f0")
    ax.set_xlim(0, 7.2)
    ax.set_ylim(-0.7, 1.7)
    ax.set_xticks(range(0, 8))
    ax.xaxis.set_major_formatter(lambda x, _p: f"{x:.0f}")
    ax.set_xlabel("Days (ACH counts business days: Monday to Friday)", color="#94a3b8")
    ax.grid(True, axis="x"); ax.grid(False, axis="y")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return save_image(Image.open(buf).convert("RGB"), path)


def make_fact_card(
    path: Path,
    label: str,
    big: str,
    sub: str,
    footer: str = "PlainBTC",
    w=1200,
    h=630,
) -> Path:
    img = gradient_bg(w, h)
    draw = ImageDraw.Draw(img)
    # left accent
    draw.rectangle([0, 0, 10, h], fill=ORANGE)
    # subtle grid
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, w, 48):
        od.line([(x, 0), (x, h)], fill=(255, 255, 255, 14))
    for y in range(0, h, 48):
        od.line([(0, y), (w, y)], fill=(255, 255, 255, 14))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    lf = load_font(FONT_BOLD, 28)
    bf = load_font(FONT_BOLD, 96)
    sf = load_font(FONT_REG, 32)
    ff = load_font(FONT_REG, 22)
    brand = load_font(FONT_BOLD, 24)

    draw.text((56, 48), label.upper(), font=lf, fill=ORANGE)
    lw = draw.textlength(label.upper(), font=lf)
    draw.rectangle([56, 48 + 38, 56 + max(48, int(lw * 0.4)), 48 + 42], fill=ORANGE)

    # big number — shrink if needed
    size = 96
    while size > 48 and draw.textlength(big, font=load_font(FONT_BOLD, size)) > w - 120:
        size -= 4
    bf = load_font(FONT_BOLD, size)
    draw.text((56, 160), big, font=bf, fill=WHITE)

    for i, line in enumerate(wrap(draw, sub, sf, w - 120, max_lines=3)):
        draw.text((56, 300 + i * 42), line, font=sf, fill=GRAY)

    draw.text((56, h - 56), footer, font=ff, fill=MUTED)
    draw.text((w - 210, h - 56), "Plain", font=brand, fill=WHITE)
    pw = draw.textlength("Plain", font=brand)
    draw.text((w - 210 + pw, h - 56), "BTC", font=brand, fill=ORANGE)
    return save_image(img, path)


def tr_map(template_dict, **kwargs):
    return {lang: template_dict[lang].format(**kwargs) for lang in LANGS}


def alts(en: str, translations: dict[str, str] | None = None) -> dict[str, str]:
    """Return alt dict; missing langs fall back to English (caller fills translations)."""
    out = {lang: en for lang in LANGS}
    if translations:
        out.update(translations)
    return out


# Per-article image plans ----------------------------------------------------

def build_bitcoin_50w(btc_xs, btc_ys):
    slug = "bitcoin-loses-50-week-moving-average-nov-2026"
    d = OUT / slug
    chart = make_line_chart(
        d / "chart-btc-50w",
        btc_xs,
        btc_ys,
        title="Bitcoin price (90 days) vs ~$75,488 50-week MA",
        hline=75488,
        hlabel="50-week MA ≈ $75,488 (Galaxy / The Block)",
    )
    card = make_fact_card(
        d / "fact-liquidations",
        label="Market stress",
        big="$1.15B",
        sub="Crypto liquidations in 24 hours — mostly longs (CoinGlass via The Block)",
        footer="Cited in article · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of bitcoin price over 90 days with a dashed line at the $75,488 50-week moving average",
                {
                    "es": "Gráfico de la cotización de bitcoin en 90 días con una línea de puntos en la media móvil de 50 semanas de 75.488 $",
                    "pt": "Gráfico do preço do bitcoin em 90 dias com linha tracejada na média móvel de 50 semanas de US$ 75.488",
                    "fr": "Graphique du prix du bitcoin sur 90 jours avec une ligne en pointillés à la moyenne mobile 50 semaines à 75 488 $",
                    "de": "Liniendiagramm des Bitcoin-Kurses über 90 Tage mit gestrichelter 50-Wochen-Durchschnittslinie bei 75.488 $",
                    "ru": "График цены биткоина за 90 дней с пунктирной линией 50-недельной средней около $75 488",
                    "tr": "90 günlük bitcoin fiyat grafiği ve 75.488 $ seviyesindeki 50 haftalık ortalamayı gösteren kesik çizgi",
                    "id": "Grafik harga bitcoin 90 hari dengan garis putus-putus di rata-rata bergerak 50 minggu $75.488",
                    "ja": "ビットコインの90日間価格チャートと5万75488ドルの50週移動平均の破線",
                    "ko": "비트코인 90일 가격 차트와 75,488달러 50주 이동평균 점선",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko; 50-week MA level cited by Galaxy via The Block"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting $1.15 billion in crypto liquidations over 24 hours",
                {
                    "es": "Tarjeta con la cifra de 1.150 millones de dólares en liquidaciones cripto en 24 horas",
                    "pt": "Cartão destacando US$ 1,15 bilhão em liquidações cripto em 24 horas",
                    "fr": "Encadré mettant en avant 1,15 milliard de dollars de liquidations crypto en 24 heures",
                    "de": "Faktenkarte zu 1,15 Mrd. $ Krypto-Liquidationen in 24 Stunden",
                    "ru": "Карточка с цифрой $1,15 млрд ликвидаций за 24 часа",
                    "tr": "24 saatte 1,15 milyar dolarlık kripto tasfiyesini vurgulayan kart",
                    "id": "Kart fakta $1,15 miliar likuidasi kripto dalam 24 jam",
                    "ja": "24時間で11.5億ドルの暗号資産清算を示すファクトカード",
                    "ko": "24시간 동안 11억 5천만 달러 청산을 강조한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via The Block"),
        },
    ]


def build_volatility(btc_xs, btc_ys):
    slug = "bitcoin-volatility-liquidations-nov-2026"
    d = OUT / slug
    # last ~14 days of the 90d series
    cut = max(0, len(btc_xs) - 50)
    chart = make_line_chart(
        d / "chart-btc-weekend",
        btc_xs[cut:],
        btc_ys[cut:],
        title="Bitcoin price into the Nov 8–9 weekend swing",
    )
    card = make_fact_card(
        d / "fact-1b-liquidated",
        label="Derivatives",
        big=">$1B",
        sub="Liquidated in 24 hours — about $913M from longs (CoinGlass via CoinDesk)",
        footer="Cited in article · Nov 8–9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of recent bitcoin prices around the Nov 8–9 weekend selloff",
                {
                    "es": "Gráfico de precios recientes de bitcoin alrededor de la caída del fin de semana del 8–9 de noviembre",
                    "pt": "Gráfico dos preços recentes do bitcoin em torno da queda do fim de semana de 8–9 de novembro",
                    "fr": "Graphique des cours récents du bitcoin autour du sell-off du week-end des 8–9 novembre",
                    "de": "Liniendiagramm der jüngsten Bitcoin-Kurse um den Wochenend-Ausverkauf vom 8.–9. November",
                    "ru": "График недавней цены биткоина вокруг выходной просадки 8–9 ноября",
                    "tr": "8–9 Kasım hafta sonu satış dalgası çevresindeki bitcoin fiyat grafiği",
                    "id": "Grafik harga bitcoin terkini sekitar aksi jual akhir pekan 8–9 November",
                    "ja": "11月8–9日の週末急落前後のビットコイン価格チャート",
                    "ko": "11월 8–9일 주말 급락 전후의 비트코인 가격 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card showing more than $1 billion liquidated in 24 hours, mostly longs",
                {
                    "es": "Tarjeta que muestra más de 1.000 millones de dólares liquidados en 24 horas, sobre todo longs",
                    "pt": "Cartão mostrando mais de US$ 1 bilhão liquidado em 24 horas, sobretudo longs",
                    "fr": "Encadré montrant plus d’1 milliard de dollars liquidés en 24 heures, surtout des longs",
                    "de": "Faktenkarte: über 1 Mrd. $ Liquidationen in 24 Stunden, vor allem Longs",
                    "ru": "Карточка: более $1 млрд ликвидаций за 24 часа, в основном лонги",
                    "tr": "24 saatte 1 milyar dolardan fazla tasfiye — çoğunlukla long pozisyonlar",
                    "id": "Kart fakta lebih dari $1 miliar dilikuidasi dalam 24 jam, sebagian besar long",
                    "ja": "24時間で10億ドル超が清算、大半がロングというファクトカード",
                    "ko": "24시간 동안 10억 달러 이상 청산(대부분 롱) 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via CoinDesk"),
        },
    ]


def build_midterms():
    slug = "us-midterms-crypto-regulation-etf-outflows"
    d = OUT / slug
    # Bar chart from article-cited SoSoValue / CoinDesk figures (millions USD)
    chart = make_bar_chart(
        d / "chart-etf-outflows",
        labels=["Weekly BTC\nETF outflow", "YTD BTC\nETF flow", "Friday IBIT\noutflow", "Nov ETH ETF\noutflow MTD"],
        values=[-1282, -914, -403, -365],
        title="Spot crypto ETF flows cited for the midterms week (SoSoValue via CoinDesk)",
        colors=["#f97316", "#fb923c", "#38bdf8", "#a78bfa"],
    )
    card = make_fact_card(
        d / "fact-weekly-outflow",
        label="ETF flows",
        big="$1.282B",
        sub="Largest weekly spot bitcoin ETF net outflow since late June (SoSoValue via CoinDesk)",
        footer="Cited in article · week of Nov 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Bar chart of spot bitcoin and ether ETF outflows cited for the midterms week",
                {
                    "es": "Gráfico de barras de salidas de ETF spot de bitcoin y ether citadas tras las midterms",
                    "pt": "Gráfico de barras das saídas de ETF spot de bitcoin e ether citadas na semana das midterms",
                    "fr": "Histogramme des sorties d’ETF spot bitcoin et ether citées la semaine des midterms",
                    "de": "Balkendiagramm der Spot-Bitcoin- und Ether-ETF-Abflüsse in der Midterms-Woche",
                    "ru": "Столбчатый график оттоков спотовых ETF биткоина и эфира за неделю midterms",
                    "tr": "Ara seçimler haftasında alıntılanan spot bitcoin ve ether ETF çıkışlarını gösteren çubuk grafik",
                    "id": "Grafik batang arus keluar ETF spot bitcoin dan ether yang dikutip pada pekan midterms",
                    "ja": "中間選挙週に引用されたビットコイン／イーサのスポットETF流出の棒グラフ",
                    "ko": "중간선거 주간에 인용된 비트코인·이더 현물 ETF 유출 막대 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="SoSoValue figures as reported by CoinDesk / SquawkNews"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a $1.282 billion weekly spot bitcoin ETF net outflow",
                {
                    "es": "Tarjeta con la cifra de 1.282 millones de dólares de salida semanal neta de ETF spot de bitcoin",
                    "pt": "Cartão destacando saída líquida semanal de US$ 1,282 bilhão em ETF spot de bitcoin",
                    "fr": "Encadré sur une sortie nette hebdomadaire de 1,282 milliard de dollars des ETF spot bitcoin",
                    "de": "Faktenkarte: 1,282 Mrd. $ wöchentlicher Nettoabfluss aus Spot-Bitcoin-ETFs",
                    "ru": "Карточка: недельный чистый отток $1,282 млрд из спотовых ETF биткоина",
                    "tr": "Spot bitcoin ETF’lerinden haftalık 1,282 milyar dolar net çıkışı vurgulayan kart",
                    "id": "Kart fakta arus keluar bersih mingguan $1,282 miliar dari ETF spot bitcoin",
                    "ja": "ビットコインのスポットETFから週次で12.82億ドルの純流出を示すカード",
                    "ko": "비트코인 현물 ETF 주간 순유출 12억 8,200만 달러 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="SoSoValue via CoinDesk"),
        },
    ]


def build_fincen():
    slug = "fincen-fed-withdraw-250-travel-rule-nov-2026"
    d = OUT / slug
    chart = make_bar_chart(
        d / "chart-thresholds",
        labels=["Current Travel Rule\nthreshold", "2020 proposal\n(withdrawn)"],
        values=[3000, 250],
        title="Cross-border funds-transfer threshold: $3,000 stays (FinCEN / Fed)",
        colors=["#38bdf8", "#f97316"],
    )
    # Override bar labels to show dollars not millions — remake with custom formatter
    # Actually make_bar_chart formats as $XM which is wrong for 3000/250.
    # Rebuild manually:
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Cross-border funds-transfer threshold: $3,000 stays")
    vals = [3000, 250]
    labels = ["Current threshold\n(stays)", "2020 proposal\n(withdrawn Nov 9, 2026)"]
    bars = ax.bar(labels, vals, color=["#38bdf8", "#f97316"], width=0.45)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"${v:,}",
                ha="center", va="bottom", color="#e2e8f0", fontsize=14, fontweight="bold")
    ax.set_ylabel("USD threshold", color="#94a3b8")
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-thresholds")

    card = make_fact_card(
        d / "fact-threshold-stays",
        label="Travel Rule",
        big="$3,000",
        sub="Threshold stays — FinCEN and the Fed withdrew the $250 NPRM on Nov 9, 2026",
        footer="Federal Register notice · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Bar chart comparing the current $3,000 Travel Rule threshold with the withdrawn $250 proposal",
                {
                    "es": "Gráfico que compara el umbral vigente de 3.000 $ de la Travel Rule con la propuesta retirada de 250 $",
                    "pt": "Gráfico comparando o limiar atual de US$ 3.000 da Travel Rule com a proposta retirada de US$ 250",
                    "fr": "Histogramme comparant le seuil actuel de 3 000 $ de la Travel Rule et la proposition retirée à 250 $",
                    "de": "Balkendiagramm: geltende 3.000-$ Travel-Rule-Schwelle vs. zurückgezogener 250-$ Vorschlag",
                    "ru": "Сравнение действующего порога Travel Rule $3 000 и отозванного предложения $250",
                    "tr": "Yürürlükteki 3.000 $ Travel Rule eşiği ile geri çekilen 250 $ teklifini karşılaştıran grafik",
                    "id": "Grafik membandingkan ambang Travel Rule $3.000 yang berlaku dengan usulan $250 yang ditarik",
                    "ja": "現行のトラベルルールしきい値3000ドルと撤回された250ドル案の比較棒グラフ",
                    "ko": "현행 트래블룰 3,000달러 기준과 철회된 250달러 제안 비교 막대 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="FinCEN / Federal Reserve Federal Register notice"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card stating the $3,000 Travel Rule threshold remains after the $250 proposal was withdrawn",
                {
                    "es": "Tarjeta que indica que el umbral de 3.000 $ de la Travel Rule se mantiene tras retirar la propuesta de 250 $",
                    "pt": "Cartão afirmando que o limiar de US$ 3.000 da Travel Rule permanece após a retirada da proposta de US$ 250",
                    "fr": "Encadré : le seuil de 3 000 $ de la Travel Rule reste après le retrait de la proposition à 250 $",
                    "de": "Faktenkarte: 3.000-$ Travel-Rule-Schwelle bleibt nach Rücknahme des 250-$ Vorschlags",
                    "ru": "Карточка: порог Travel Rule $3 000 сохраняется после отзыва предложения $250",
                    "tr": "250 $ teklifi geri çekildikten sonra 3.000 $ Travel Rule eşiğinin kaldığını belirten kart",
                    "id": "Kart fakta ambang Travel Rule $3.000 tetap setelah usulan $250 ditarik",
                    "ja": "250ドル案撤回後もトラベルルールしきい値3000ドルが維持されることを示すカード",
                    "ko": "250달러 제안 철회 후에도 트래블룰 3,000달러 기준이 유지됨을 보여주는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="Federal Register / FinCEN & Federal Reserve"),
        },
    ]


def build_pnc():
    slug = "pnc-coinbase-usdc-payments-pilot-nov-2026"
    d = OUT / slug
    card1 = make_fact_card(
        d / "fact-usdc-1to1",
        label="Stablecoin pilot",
        big="1 : 1",
        sub="Incoming USDC on Ethereum converts into a PNC U.S. dollar deposit (PNC press release)",
        footer="PNC Bank × Coinbase · Nov 9, 2026",
    )
    card2 = make_fact_card(
        d / "fact-corporate-pilot",
        label="Who it’s for",
        big="CIB clients",
        sub="Limited pilot for eligible Corporate & Institutional Banking clients — not a retail product",
        footer="PNC media room · Nov 9, 2026",
    )
    return [
        {
            "id": "chart",  # first mid-image slot (fact styled)
            "file": card1.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card showing USDC converts 1-to-1 into a PNC dollar deposit",
                {
                    "es": "Tarjeta que muestra que USDC se convierte 1 a 1 en un depósito en dólares de PNC",
                    "pt": "Cartão mostrando que USDC converte 1 para 1 em depósito em dólares no PNC",
                    "fr": "Encadré : l’USDC est converti 1 pour 1 en dépôt dollar chez PNC",
                    "de": "Faktenkarte: USDC wird 1:1 in eine PNC-Dollar-Einlage umgewandelt",
                    "ru": "Карточка: USDC конвертируется 1 к 1 в долларовый депозит PNC",
                    "tr": "USDC’nin 1’e 1 PNC dolar mevduatına dönüştüğünü gösteren kart",
                    "id": "Kart fakta USDC dikonversi 1:1 menjadi deposito dolar PNC",
                    "ja": "USDCが1対1でPNCのドル預金に換金されることを示すカード",
                    "ko": "USDC가 1:1로 PNC 달러 예금으로 전환됨을 보여주는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="PNC Bank press release"),
        },
        {
            "id": "fact",
            "file": card2.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card noting the USDC payments launch is a limited pilot for CIB clients",
                {
                    "es": "Tarjeta que indica que el lanzamiento de pagos USDC es un piloto limitado para clientes CIB",
                    "pt": "Cartão notando que o lançamento de pagamentos USDC é um piloto limitado para clientes CIB",
                    "fr": "Encadré : le lancement des paiements USDC est un pilote limité pour les clients CIB",
                    "de": "Faktenkarte: USDC-Zahlungsstart ist ein begrenzter Pilot für CIB-Kunden",
                    "ru": "Карточка: запуск платежей USDC — ограниченный пилот для клиентов CIB",
                    "tr": "USDC ödeme lansmanının CIB müşterileri için sınırlı bir pilot olduğunu belirten kart",
                    "id": "Kart fakta peluncuran pembayaran USDC adalah pilot terbatas untuk klien CIB",
                    "ja": "USDC決済の開始がCIB顧客向けの限定パイロットであることを示すカード",
                    "ko": "USDC 결제 출시가 CIB 고객 대상 제한 파일럿임을 알리는 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="PNC Bank press release"),
        },
    ]


def build_occ():
    slug = "coinbase-occ-national-trust-charter-nov-2026"
    d = OUT / slug
    card1 = make_fact_card(
        d / "fact-60m-capital",
        label="OCC charter terms",
        big="$60M",
        sub="Minimum Tier 1 capital required for Coinbase National Trust Company (reports on OCC terms)",
        footer="Cited in article · OCC / Coinbase",
    )
    card2 = make_fact_card(
        d / "fact-180-days",
        label="Liquidity guardrail",
        big="180 days",
        sub="Liquid assets to cover operating expenses required in the trust’s first three years",
        footer="Cited in article · OCC conditional terms",
    )
    return [
        {
            "id": "chart",
            "file": card1.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a $60 million Tier 1 capital requirement for Coinbase National Trust Company",
                {
                    "es": "Tarjeta que destaca el requisito de 60 millones de dólares de capital de Nivel 1 para Coinbase National Trust Company",
                    "pt": "Cartão destacando exigência de US$ 60 milhões de capital Nível 1 para a Coinbase National Trust Company",
                    "fr": "Encadré sur l’exigence de 60 millions de dollars de fonds propres de catégorie 1 pour Coinbase National Trust Company",
                    "de": "Faktenkarte: 60 Mio. $ Tier-1-Kapitalanforderung für Coinbase National Trust Company",
                    "ru": "Карточка: требование капитала Tier 1 на $60 млн для Coinbase National Trust Company",
                    "tr": "Coinbase National Trust Company için 60 milyon $ Tier 1 sermaye şartını vurgulayan kart",
                    "id": "Kart fakta persyaratan modal Tier 1 $60 juta untuk Coinbase National Trust Company",
                    "ja": "Coinbase National Trust Companyのティア1自己資本6000万ドル要件を示すカード",
                    "ko": "Coinbase National Trust Company의 티어1 자본 6천만 달러 요건 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="OCC terms as reported in article sources"),
        },
        {
            "id": "fact",
            "file": card2.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card highlighting a 180-day operating-expense liquidity requirement",
                {
                    "es": "Tarjeta que destaca el requisito de liquidez para 180 días de gastos operativos",
                    "pt": "Cartão destacando exigência de liquidez para 180 dias de despesas operacionais",
                    "fr": "Encadré sur l’exigence de liquidités couvrant 180 jours de frais d’exploitation",
                    "de": "Faktenkarte: Liquiditätsanforderung für 180 Tage Betriebskosten",
                    "ru": "Карточка: требование ликвидности на 180 дней операционных расходов",
                    "tr": "180 günlük işletme gideri likidite şartını vurgulayan kart",
                    "id": "Kart fakta persyaratan likuiditas biaya operasional 180 hari",
                    "ja": "180日分の運営費用をカバーする流動性要件を示すカード",
                    "ko": "180일분 운영비용 유동성 요건을 강조한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="OCC conditional approval terms as reported"),
        },
    ]


def build_howto(btc_xs, btc_ys):
    slug = "how-to-buy-first-bitcoin-coinbase"
    d = OUT / slug
    chart = make_line_chart(
        d / "chart-btc-context",
        btc_xs,
        btc_ys,
        title="Bitcoin price context (90 days) — why first buys stay small",
    )
    card = make_fact_card(
        d / "fact-5-steps",
        label="Beginner path",
        big="6 steps",
        sub="Account → verify ID → add payment → buy BTC → check fees → secure storage",
        footer="U.S. beginner guide · Coinbase help docs",
    )
    return [
        {
            "id": "chart",
            "file": chart.name,
            "w": 1200,
            "h": 675,
            "kind": "chart",
            "alt": alts(
                "Line chart of bitcoin’s 90-day price used as market context for first-time buyers",
                {
                    "es": "Gráfico de 90 días del precio de bitcoin como contexto de mercado para compradores primerizos",
                    "pt": "Gráfico de 90 dias do preço do bitcoin como contexto de mercado para iniciantes",
                    "fr": "Graphique sur 90 jours du prix du bitcoin comme contexte pour les premiers acheteurs",
                    "de": "90-Tage-Bitcoin-Kurschart als Marktkontext für Ersteinsteiger",
                    "ru": "График цены биткоина за 90 дней как рыночный контекст для новичков",
                    "tr": "İlk alıcılar için piyasa bağlamı olarak 90 günlük bitcoin fiyat grafiği",
                    "id": "Grafik harga bitcoin 90 hari sebagai konteks pasar bagi pembeli pemula",
                    "ja": "初めての購入者向けの市場コンテキストとしてのビットコイン90日価格チャート",
                    "ko": "첫 구매자를 위한 시장 맥락용 비트코인 90일 가격 차트",
                },
            ),
            "caption": tr_map(CAPTION_CHART, src="CoinGecko"),
        },
        {
            "id": "fact",
            "file": card.name,
            "w": 1200,
            "h": 630,
            "kind": "fact",
            "alt": alts(
                "Fact card summarizing the six beginner steps to buy bitcoin on Coinbase",
                {
                    "es": "Tarjeta que resume los seis pasos para comprar bitcoin en Coinbase como principiante",
                    "pt": "Cartão resumindo os seis passos para comprar bitcoin na Coinbase como iniciante",
                    "fr": "Encadré résumant les six étapes pour acheter du bitcoin sur Coinbase en débutant",
                    "de": "Faktenkarte: sechs Einsteiger-Schritte zum Bitcoin-Kauf auf Coinbase",
                    "ru": "Карточка: шесть шагов новичка для покупки биткоина на Coinbase",
                    "tr": "Coinbase’de bitcoin almak için altı başlangıç adımını özetleyen kart",
                    "id": "Kart fakta enam langkah pemula membeli bitcoin di Coinbase",
                    "ja": "Coinbaseでビットコインを買う初心者向け6ステップをまとめたカード",
                    "ko": "코인베이스에서 비트코인을 사는 초보 6단계를 요약한 팩트 카드",
                },
            ),
            "caption": tr_map(CAPTION_SOURCE, src="Coinbase help documentation (as cited in guide)"),
        },
    ]


# ---------------------------------------------------------------------------
# Evergreen beginner guides (Coinbase Exchange public candles, Coinbase docs)
# ---------------------------------------------------------------------------

def fetch_coinbase_daily(start="2020-12-01"):
    """Daily BTC-USD candles from Coinbase Exchange public API -> list of (date, close)."""
    import datetime as dt
    import time

    def get(s, e):
        u = ("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"
             f"&start={s.isoformat()}Z&end={e.isoformat()}Z")
        r = urllib.request.Request(u, headers={"User-Agent": "PlainBTC/1.0"})
        return json.loads(urllib.request.urlopen(r, timeout=30).read())

    cur = dt.datetime.fromisoformat(start)
    end = dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(days=1)
    rows = {}
    while cur < end:
        nxt = min(cur + dt.timedelta(days=299), end)
        for c in get(cur, nxt):
            rows[c[0]] = c
        cur = nxt
        time.sleep(0.4)
    return [(dt.datetime.fromtimestamp(r[0], dt.UTC).date(), r[4]) for r in sorted(rows.values())]


def make_compare_card(path: Path, title: str, left: str, right: str, rows, footer="PlainBTC", w=1200, h=630):
    img = gradient_bg(w, h)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 10, h], fill=ORANGE)
    tf, hf = load_font(FONT_BOLD, 34), load_font(FONT_BOLD, 28)
    rl, cf = load_font(FONT_BOLD, 22), load_font(FONT_REG, 25)
    ff, brand = load_font(FONT_REG, 22), load_font(FONT_BOLD, 24)
    draw.text((56, 36), title, font=tf, fill=WHITE)
    x0, x1, x2 = 56, 400, 800
    colw = 360
    draw.rounded_rectangle([x1 - 12, 100, x1 + colw, 150], radius=10, fill=(30, 41, 59))
    draw.rounded_rectangle([x2 - 12, 100, x2 + colw, 150], radius=10, fill=(120, 70, 10))
    draw.text((x1, 109), left, font=hf, fill=WHITE)
    draw.text((x2, 109), right, font=hf, fill=WHITE)
    y = 172
    for label, a, b in rows:
        draw.text((x0, y + 4), label.upper(), font=rl, fill=ORANGE)
        for x, txt in ((x1, a), (x2, b)):
            for i, line in enumerate(wrap(draw, txt, cf, colw - 6, max_lines=3)):
                draw.text((x, y + i * 32), line, font=cf, fill=GRAY if x == x1 else (226, 232, 240))
        y += 128
        draw.line([(x0, y - 22), (w - 56, y - 22)], fill=(30, 41, 59), width=2)
    draw.text((56, h - 46), footer, font=ff, fill=MUTED)
    draw.text((w - 210, h - 46), "Plain", font=brand, fill=WHITE)
    pw = draw.textlength("Plain", font=brand)
    draw.text((w - 210 + pw, h - 46), "BTC", font=brand, fill=ORANGE)
    return save_image(img, path)


def _lang_dict(en, **tr):
    out = {"en": en}
    out.update(tr)
    missing = [l for l in LANGS if l not in out]
    assert not missing, missing
    return out


def _fig(fid, file, kind, w, h, alt, caption):
    return {"id": fid, "file": file, "w": w, "h": h, "kind": kind, "alt": alt, "caption": caption}


def build_safe():
    slug = "is-coinbase-safe-for-beginners"
    d = OUT / slug
    c1 = make_fact_card(
        d / "fact-cold-storage", label="Where your crypto sits", big="Over 99%",
        sub="of customer assets stay in Coinbase’s offline cold wallets, according to Coinbase",
        footer="Source: Coinbase blog · How Coinbase protects customer assets")
    c2 = make_fact_card(
        d / "fact-fdic-250k", label="What is insured", big="$250,000",
        sub="Per-depositor FDIC / NCUSIF pass-through limit on U.S. dollar cash balances, not on crypto",
        footer="Source: Coinbase Help · FDIC")
    cap1 = tr_map(CAPTION_SOURCE, src="Coinbase blog")
    cap2 = tr_map(CAPTION_SOURCE, src="Coinbase Help, FDIC")
    return [
        _fig("cold", c1.name, "fact", 1200, 630, _lang_dict(
            "Fact card: Coinbase says over 99% of customer assets stay in offline cold wallets",
            es="Tarjeta: Coinbase afirma que más del 99 % de los activos de clientes permanece en carteras frías sin conexión",
            pt="Cartão: a Coinbase diz que mais de 99% dos ativos dos clientes ficam em carteiras frias offline",
            fr="Encadré : Coinbase affirme que plus de 99 % des actifs clients restent dans des portefeuilles froids hors ligne",
            de="Faktenkarte: Coinbase gibt an, dass über 99 % der Kundenwerte in Offline-Cold-Wallets liegen",
            ru="Карточка: Coinbase сообщает, что более 99% активов клиентов хранится в офлайн-холодных кошельках",
            tr="Bilgi kartı: Coinbase, müşteri varlıklarının %99’undan fazlasının çevrimdışı soğuk cüzdanlarda durduğunu söylüyor",
            id="Kartu fakta: Coinbase menyatakan lebih dari 99% aset pelanggan disimpan di dompet dingin offline",
            ja="ファクトカード：Coinbaseは顧客資産の99%超をオフラインのコールドウォレットで保管していると説明",
            ko="팩트 카드: 코인베이스는 고객 자산의 99% 이상을 오프라인 콜드 월렛에 보관한다고 밝힘"), cap1),
        _fig("fdic", c2.name, "fact", 1200, 630, _lang_dict(
            "Fact card: the $250,000 per-depositor FDIC pass-through limit applies to U.S. dollar cash balances, not crypto",
            es="Tarjeta: el límite de 250 000 $ por depositante de la FDIC se aplica al efectivo en dólares, no a las criptomonedas",
            pt="Cartão: o limite de US$ 250.000 por depositante da FDIC vale para saldo em dólares, não para cripto",
            fr="Encadré : le plafond FDIC de 250 000 $ par déposant s’applique aux dollars en espèces, pas aux cryptos",
            de="Faktenkarte: Die FDIC-Grenze von 250.000 $ pro Einleger gilt für Dollar-Guthaben, nicht für Krypto",
            ru="Карточка: лимит FDIC в $250 000 на вкладчика относится к долларовым остаткам, а не к криптовалюте",
            tr="Bilgi kartı: mudi başına 250.000 $ FDIC sınırı dolar nakit bakiyeler için geçerlidir, kripto için değil",
            id="Kartu fakta: batas FDIC US$250.000 per penyimpan berlaku untuk saldo dolar tunai, bukan kripto",
            ja="ファクトカード：預金者1人あたり25万ドルのFDIC上限は米ドル現金残高が対象で、暗号資産は対象外",
            ko="팩트 카드: 예금자당 25만 달러 FDIC 한도는 미국 달러 현금 잔액에 적용되며 암호화폐에는 적용되지 않음"), cap2),
    ]


def build_dca():
    import datetime as dt
    slug = "how-much-bitcoin-should-a-beginner-buy-dca"
    d = OUT / slug
    ASOF = dt.date(2026, 11, 8)  # fixed last full-day close so the article numbers stay reproducible
    px = [x for x in fetch_coinbase_daily("2020-12-01") if x[0] <= ASOF]
    last_d, last_p = px[-1]
    # --- chart: 5 years of closes with two peak-to-trough drops
    five = [x for x in px if x[0] >= dt.date(2021, 10, 1)]
    p21 = max((x for x in px if x[0].year == 2021), key=lambda x: x[1])
    t22 = min((x for x in px if p21[0] < x[0] <= dt.date(2022, 12, 31)), key=lambda x: x[1])
    ath = max(px, key=lambda x: x[1])
    low = min((x for x in px if x[0] > ath[0]), key=lambda x: x[1])
    drop1 = (t22[1] / p21[1] - 1) * 100
    drop2 = (low[1] / ath[1] - 1) * 100
    print(f"  peak {p21} -> trough {t22} = {drop1:.1f}%;  ATH {ath} -> low {low} = {drop2:.1f}%")
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Bitcoin daily closing price (USD), Nov 2021 – Nov 2026")
    orange = "#f7931a"
    xs = [x[0] for x in five]
    ys = [x[1] for x in five]
    ax.plot(xs, ys, color=orange, linewidth=1.8)
    ax.fill_between(xs, ys, 0, color=orange, alpha=0.10)
    for (a, b, dd) in ((p21, t22, drop1), (ath, low, drop2)):
        ax.annotate("", xy=(b[0], b[1]), xytext=(a[0], a[1]),
                    arrowprops=dict(arrowstyle="->", color="#f87171", lw=1.6, linestyle="--"))
        ax.scatter([a[0], b[0]], [a[1], b[1]], color="#f87171", zorder=5, s=28)
        mid_x = a[0] + (b[0] - a[0]) / 2 + dt.timedelta(days=45)
        ax.text(mid_x, (a[1] + b[1]) / 2 * 1.3, f"{dd:.0f}%", color="#f87171",
                fontsize=16, fontweight="bold", ha="center")
        ax.text(a[0], a[1] * 1.04, f"${a[1]:,.0f}\n{a[0]:%b %-d, %Y}", color="#e2e8f0", fontsize=9, ha="center")
        ax.text(b[0], b[1] * 0.55, f"${b[1]:,.0f}\n{b[0]:%b %-d, %Y}", color="#e2e8f0", fontsize=9, ha="center")
    ax.set_ylim(0, ath[1] * 1.22)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.yaxis.set_major_formatter(lambda v, _p: f"${v/1000:,.0f}k")
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-btc-5y-drawdowns")
    # --- DCA vs lump sum bars (weekly $50)
    def sim(days, amt=50):
        start = last_d - dt.timedelta(days=days)
        w = [x for x in px if x[0] >= start and (x[0] - start).days % 7 == 0]
        inv = amt * len(w)
        coins = sum(amt / p for _, p in w)
        return len(w), inv, coins * last_p, inv / w[0][1] * last_p
    res = [sim(364), sim(730), sim(1092)]
    for r in res:
        print(f"  weeks={r[0]} invested=${r[1]:,} dca=${r[2]:,.0f} lump=${r[3]:,.0f}")
    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=100)
    style_axes(ax, f"$50 weekly buys vs. one lump sum, valued {last_d:%b %-d, %Y}")
    labels = ["Last 12 months", "Last 24 months", "Last 36 months"]
    import numpy as _np
    xi = _np.arange(3)
    bw = 0.26
    series = [([r[1] for r in res], "Total invested", "#64748b"),
              ([r[2] for r in res], "Weekly $50 buys", orange),
              ([r[3] for r in res], "Lump sum on day one", "#38bdf8")]
    for k, (vals, name, col) in enumerate(series):
        bars = ax.bar(xi + (k - 1) * bw, vals, bw, label=name, color=col, edgecolor="#0b1630")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"${v:,.0f}", ha="center", va="bottom",
                    color="#e2e8f0", fontsize=10, fontweight="bold")
    ax.set_xticks(xi)
    ax.set_xticklabels([f"{l}\n({r[0]} buys)" for l, r in zip(labels, res)], color="#cbd5e1", fontsize=11)
    ax.yaxis.set_major_formatter(lambda v, _p: f"${v:,.0f}")
    ax.set_ylim(0, max(r[3] for r in res) * 1.15)
    leg = ax.legend(facecolor="#0b1630", edgecolor="#1e293b", labelcolor="#e2e8f0", loc="upper left")
    fig.text(0.01, 0.01, "Illustration only: daily closes, no fees or taxes. Past performance is not a guide to the future.",
             color="#64748b", fontsize=8.5)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    plt.tight_layout(pad=1.2, rect=(0, 0.03, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    bars_img = save_image(Image.open(buf).convert("RGB"), d / "chart-dca-vs-lump-sum")
    cap = tr_map(CAPTION_CHART, src="Coinbase Exchange (BTC-USD daily candles)")
    return [
        _fig("chart", chart.name, "chart", 1200, 675, _lang_dict(
            "Line chart of bitcoin’s daily closing price from November 2021 to November 2026, marking a 77% fall and a 53% fall from two peaks",
            es="Gráfico del precio de cierre diario de bitcoin de noviembre de 2021 a noviembre de 2026, con una caída del 77 % y otra del 53 % desde dos máximos",
            pt="Gráfico do preço de fechamento diário do bitcoin de novembro de 2021 a novembro de 2026, com quedas de 77% e 53% a partir de dois picos",
            fr="Graphique du cours de clôture quotidien du bitcoin de novembre 2021 à novembre 2026, avec une baisse de 77 % et une de 53 % depuis deux sommets",
            de="Liniendiagramm des täglichen Bitcoin-Schlusskurses von November 2021 bis November 2026 mit Rückgängen um 77 % und 53 % von zwei Höchstständen",
            ru="График ежедневной цены закрытия биткоина с ноября 2021 по ноябрь 2026 с падениями на 77% и 53% от двух пиков",
            tr="Kasım 2021’den Kasım 2026’ya bitcoin günlük kapanış fiyatı grafiği; iki zirveden %77 ve %53 düşüş işaretli",
            id="Grafik harga penutupan harian bitcoin November 2021 hingga November 2026 dengan penurunan 77% dan 53% dari dua puncak",
            ja="2021年11月から2026年11月までのビットコイン日次終値チャート。2つの高値からの77%と53%の下落を表示",
            ko="2021년 11월부터 2026년 11월까지 비트코인 일간 종가 차트, 두 번의 고점에서 각각 77%와 53% 하락 표시"), cap),
        _fig("fact", bars_img.name, "chart", 1200, 630, _lang_dict(
            "Bar chart comparing $50 weekly bitcoin buys with a single lump sum over the last 12, 24 and 36 months",
            es="Gráfico de barras que compara compras semanales de 50 $ en bitcoin con una inversión única en los últimos 12, 24 y 36 meses",
            pt="Gráfico de barras comparando compras semanais de US$ 50 em bitcoin com um aporte único nos últimos 12, 24 e 36 meses",
            fr="Histogramme comparant des achats hebdomadaires de 50 $ en bitcoin à un investissement unique sur 12, 24 et 36 mois",
            de="Balkendiagramm: wöchentliche Bitcoin-Käufe von 50 $ im Vergleich zu einer Einmalanlage über 12, 24 und 36 Monate",
            ru="Столбчатая диаграмма: еженедельные покупки биткоина на $50 и разовая покупка за последние 12, 24 и 36 месяцев",
            tr="Son 12, 24 ve 36 ayda haftalık 50 $’lık bitcoin alımlarını tek seferlik alımla karşılaştıran sütun grafiği",
            id="Grafik batang membandingkan pembelian bitcoin US$50 per minggu dengan pembelian sekaligus selama 12, 24, dan 36 bulan terakhir",
            ja="過去12・24・36か月について、毎週50ドルの積立購入と一括購入を比べた棒グラフ",
            ko="최근 12·24·36개월 동안 매주 50달러 분할 매수와 일시 매수를 비교한 막대 차트"), cap),
    ]


def build_wallet():
    slug = "what-is-a-crypto-wallet-custodial-vs-self-custody"
    d = OUT / slug
    cmp_ = make_compare_card(
        d / "compare-custodial-vs-self",
        "Custodial vs. self-custody wallets", "Custodial", "Self-custody",
        [("Who holds the keys", "The company (e.g. a Coinbase account)", "You (e.g. the Coinbase Wallet app)"),
         ("Lose your login", "The provider can help you recover access", "Only your recovery phrase can restore it"),
         ("Main risks", "Company failure, hacks, account takeover", "Lost phrase, phishing scams, malware")],
        footer="Source: Coinbase Help · Bitcoin.org · FINRA")
    words = make_fact_card(
        d / "fact-12-words", label="Self-custody backup", big="12 words",
        sub="A Coinbase Wallet recovery phrase is 12 words. Lose it and Coinbase can’t restore your funds",
        footer="Source: Coinbase Help · BIP-39 allows 12–24 words")
    return [
        _fig("compare", cmp_.name, "fact", 1200, 630, _lang_dict(
            "Comparison card: custodial wallets, where a company holds the keys, versus self-custody wallets, where you do",
            es="Tarjeta comparativa: carteras custodiadas, donde una empresa guarda las claves, frente a carteras de autocustodia, donde las guardas tú",
            pt="Cartão comparativo: carteiras custodiais, em que uma empresa guarda as chaves, e carteiras de autocustódia, em que você as guarda",
            fr="Encadré comparatif : portefeuilles custodiaux, où une entreprise détient les clés, et portefeuilles en auto-conservation, où c’est vous",
            de="Vergleichskarte: Custodial-Wallets, bei denen ein Unternehmen die Schlüssel hält, und Self-Custody-Wallets, bei denen Sie sie halten",
            ru="Сравнительная карточка: кастодиальные кошельки, где ключи у компании, и некастодиальные, где ключи у вас",
            tr="Karşılaştırma kartı: anahtarları bir şirketin tuttuğu emanetçi cüzdanlar ile anahtarları sizin tuttuğunuz kendi saklama cüzdanları",
            id="Kartu perbandingan: dompet kustodian, di mana perusahaan memegang kunci, dan dompet self-custody, di mana Anda memegangnya",
            ja="比較カード：企業が鍵を保管するカストディアルウォレットと、自分で鍵を管理するセルフカストディウォレット",
            ko="비교 카드: 회사가 키를 보관하는 수탁형 지갑과 본인이 키를 보관하는 셀프 커스터디 지갑"),
            tr_map(CAPTION_SOURCE, src="Coinbase Help, Bitcoin.org, FINRA")),
        _fig("words", words.name, "fact", 1200, 630, _lang_dict(
            "Fact card: a Coinbase Wallet recovery phrase is 12 words, and Coinbase cannot restore it if you lose it",
            es="Tarjeta: la frase de recuperación de Coinbase Wallet tiene 12 palabras y Coinbase no puede restaurarla si la pierdes",
            pt="Cartão: a frase de recuperação da Coinbase Wallet tem 12 palavras, e a Coinbase não consegue restaurá-la se você a perder",
            fr="Encadré : la phrase de récupération de Coinbase Wallet compte 12 mots, et Coinbase ne peut pas la restaurer si vous la perdez",
            de="Faktenkarte: Die Wiederherstellungsphrase von Coinbase Wallet hat 12 Wörter; Coinbase kann sie bei Verlust nicht wiederherstellen",
            ru="Карточка: фраза восстановления Coinbase Wallet состоит из 12 слов, и Coinbase не сможет восстановить её при потере",
            tr="Bilgi kartı: Coinbase Wallet kurtarma ifadesi 12 kelimedir ve kaybederseniz Coinbase onu geri getiremez",
            id="Kartu fakta: frasa pemulihan Coinbase Wallet terdiri dari 12 kata, dan Coinbase tidak dapat memulihkannya jika hilang",
            ja="ファクトカード：Coinbase Walletのリカバリーフレーズは12語で、紛失してもCoinbaseは復元できない",
            ko="팩트 카드: 코인베이스 월렛 복구 문구는 12단어이며 분실하면 코인베이스도 복구할 수 없음"),
            tr_map(CAPTION_SOURCE, src="Coinbase Help, BIP-39")),
    ]



def build_fees():
    slug = "coinbase-fees-explained"
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    # Bar chart of published Advanced Intro maker/taker (public VIP table)
    chart = make_bar_chart(
        d / "chart-advanced-intro-v2",   # -v2: y axis was mislabeled in $M (fixed Nov 19, 2026)
        ["Maker\n(Intro)", "Taker\n(Intro)"],
        [0.50, 0.90],
        title="Coinbase Advanced spot — Intro tier (U.S.)",
        ylabel="Fee (% of order)",
        value_fmt=lambda v: f"{v:.2f}%",
        axis_fmt=lambda x, _p: f"{x:.1f}%",
        h=630,
    )
    card = make_fact_card(
        d / "fact-spread-preview",
        label="Simple trades",
        big="Preview",
        sub="Spread sits inside the quoted price — Coinbase does not publish one fixed %; check the tooltip before you buy",
        footer="Source: Coinbase Help · Pricing and fees",
    )
    return [
        _fig("advanced", chart.name, "chart", 1200, 630, _lang_dict(
            "Bar chart of Coinbase Advanced Intro spot maker 0.50% and taker 0.90% fees",
            es="Gráfico de barras: comisiones Intro de Coinbase Advanced al contado, maker 0,50 % y taker 0,90 %",
            pt="Gráfico de barras: taxas Intro da Coinbase Advanced à vista, maker 0,50% e taker 0,90%",
            fr="Graphique en barres : frais Intro Coinbase Advanced au comptant, maker 0,50 % et taker 0,90 %",
            de="Balkendiagramm: Coinbase-Advanced-Intro-Spotgebühren Maker 0,50 % und Taker 0,90 %",
            ru="Столбчатый график: комиссии Intro Coinbase Advanced на споте — maker 0,50% и taker 0,90%",
            tr="Çubuk grafik: Coinbase Advanced Intro spot maker %0,50 ve taker %0,90 ücretleri",
            id="Grafik batang: biaya Intro Coinbase Advanced spot maker 0,50% dan taker 0,90%",
            ja="棒グラフ：Coinbase AdvancedのIntroスポット手数料（メイカー0.50%、テイカー0.90%）",
            ko="막대 차트: 코인베이스 어드밴스드 Intro 현물 메이커 0.50%·테이커 0.90% 수수료"),
            tr_map(CAPTION_CHART, src="Coinbase Advanced VIP table")),
        _fig("spread", card.name, "fact", 1200, 630, _lang_dict(
            "Fact card: on simple Coinbase trades the spread is inside the quoted price — check the preview tooltip",
            es="Tarjeta: en operaciones simples de Coinbase el diferencial va en el precio cotizado; mira el tooltip de la vista previa",
            pt="Cartão: nas operações simples da Coinbase o spread está no preço cotado; veja o tooltip da prévia",
            fr="Encadré : sur les ordres simples Coinbase, le spread est dans le prix affiché — regardez l’infobulle de l’aperçu",
            de="Faktenkarte: Bei einfachen Coinbase-Trades steckt der Spread im Kurs — Tooltip in der Vorschau prüfen",
            ru="Карточка: в простых сделках Coinbase спред уже в котировке — смотрите подсказку на экране предпросмотра",
            tr="Bilgi kartı: basit Coinbase işlemlerinde spread fiyatın içindedir — önizleme ipucunu kontrol edin",
            id="Kartu fakta: pada perdagangan sederhana Coinbase, spread ada di harga yang dikutip — cek tooltip pratinjau",
            ja="ファクトカード：Coinbaseのシンプル取引ではスプレッドが提示価格に含まれる。プレビューのツールチップを確認",
            ko="팩트 카드: 코인베이스 단순 거래에서는 스프레드가 호가에 포함됨 — 미리보기 툴팁을 확인하세요"),
            tr_map(CAPTION_SOURCE, src="Coinbase Help")),
    ]


def build_cashout():
    slug = "how-to-cash-out-bitcoin-coinbase-to-bank"
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    chart = make_cashout_timing_chart(d / "chart-ach-days-v2")   # -v2: old bars were in $M with made-up ~4d/~0.5d
    tax = make_fact_card(
        d / "fact-irs-property",
        label="U.S. taxes",
        big="Property",
        sub="The IRS treats digital assets as property — selling bitcoin for USD is generally a taxable disposal",
        footer="Source: IRS · Digital assets",
    )
    return [
        _fig("timing", chart.name, "chart", 1200, 630, _lang_dict(
            "Chart comparing Coinbase ACH cash-out timing of 3–5 business days with instant cashouts of about 30 minutes, up to 24 hours",
            es="Gráfico que compara el plazo típico ACH de varios días hábiles con los cashouts instantáneos más rápidos",
            pt="Gráfico que compara o prazo típico ACH de vários dias úteis com cashouts instantâneos mais rápidos",
            fr="Graphique comparant le délai ACH typique de plusieurs jours ouvrés aux cashouts instantanés plus rapides",
            de="Diagramm: typische ACH-Auszahlung über mehrere Werktage vs. schnellere Instant-Cashouts",
            ru="График: типичные сроки ACH в несколько рабочих дней против более быстрых мгновенных выводов",
            tr="Çubuk grafik: birkaç iş günü süren tipik ACH çıkışı ile daha hızlı anlık cashout karşılaştırması",
            id="Grafik batang membandingkan waktu cash-out ACH tipikal beberapa hari kerja vs cashout instan yang lebih cepat",
            ja="棒グラフ：数営業日かかる一般的なACH出金と、より速いインスタントキャッシュアウトの比較",
            ko="막대 차트: 영업일 수일이 걸리는 일반 ACH 출금과 더 빠른 즉시 캐시아웃 비교"),
            tr_map(CAPTION_CHART, src="Coinbase Help (ACH 3–5 business days)")),
        _fig("tax", tax.name, "fact", 1200, 630, _lang_dict(
            "Fact card: the IRS treats digital assets as property, so selling bitcoin for USD is generally taxable",
            es="Tarjeta: el IRS trata los activos digitales como propiedad; vender bitcoin por USD suele ser un hecho imponible",
            pt="Cartão: a IRS trata ativos digitais como propriedade; vender bitcoin por USD geralmente é tributável",
            fr="Encadré : l’IRS traite les actifs numériques comme des biens — vendre du bitcoin contre des USD est en général imposable",
            de="Faktenkarte: Der IRS behandelt Digital Assets als Eigentum — BTC-Verkauf gegen USD ist in der Regel steuerpflichtig",
            ru="Карточка: IRS считает цифровые активы имуществом — продажа биткоина за USD обычно налогооблагаема",
            tr="Bilgi kartı: IRS dijital varlıkları mülk sayar — bitcoin’i USD’ye satmak genellikle vergilendirilir",
            id="Kartu fakta: IRS memperlakukan aset digital sebagai properti — menjual bitcoin ke USD umumnya kena pajak",
            ja="ファクトカード：IRSはデジタル資産を財産として扱うため、ビットコインのUSD売却は一般に課税対象",
            ko="팩트 카드: IRS는 디지털 자산을 재산으로 취급 — 비트코인을 USD로 파는 것은 일반적으로 과세 대상"),
            tr_map(CAPTION_SOURCE, src="IRS Digital assets")),
    ]


def build_etf():
    slug = "bitcoin-etf-vs-buying-bitcoin"
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    cmp_ = make_fact_card(
        d / "fact-etf-shares",
        label="Spot bitcoin ETF",
        big="Shares",
        sub="You own fund shares that hold bitcoin — not on-chain coins you can send to a wallet",
        footer="Source: SEC (Jan 10, 2024) · Fidelity Learning Center",
    )
    keys = make_fact_card(
        d / "fact-direct-keys",
        label="Buying bitcoin",
        big="BTC",
        sub="You hold bitcoin on an exchange or in self-custody — keys and withdrawals are part of the product",
        footer="Source: Coinbase Help · FINRA crypto risks",
    )
    return [
        _fig("compare", cmp_.name, "fact", 1200, 630, _lang_dict(
            "Fact card: a spot bitcoin ETF means you own fund shares that hold bitcoin, not coins in your wallet",
            es="Tarjeta: un ETF spot de bitcoin significa que posees participaciones del fondo, no monedas en tu cartera",
            pt="Cartão: um ETF spot de bitcoin significa que você possui cotas do fundo, não moedas na sua carteira",
            fr="Encadré : un ETF bitcoin spot signifie que vous détenez des parts de fonds, pas des pièces dans un portefeuille",
            de="Faktenkarte: Ein Spot-Bitcoin-ETF bedeutet Fondsanteile — keine Coins in Ihrer Wallet",
            ru="Карточка: спотовый bitcoin-ETF — это доли фонда, а не монеты в вашем кошельке",
            tr="Bilgi kartı: spot bitcoin ETF, cüzdanınızdaki coinler değil fon payları demektir",
            id="Kartu fakta: ETF bitcoin spot berarti Anda memiliki unit dana, bukan koin di dompet",
            ja="ファクトカード：スポットビットコインETFはウォレット内のコインではなく、ファンドの受益証券を保有する",
            ko="팩트 카드: 현물 비트코인 ETF는 지갑의 코인이 아니라 펀드 주식을 보유하는 것"),
            tr_map(CAPTION_SOURCE, src="SEC, Fidelity")),
        _fig("custody", keys.name, "fact", 1200, 630, _lang_dict(
            "Fact card: buying bitcoin means holding BTC on an exchange or in self-custody with keys you control",
            es="Tarjeta: comprar bitcoin implica tener BTC en un exchange o en autocustodia con claves que controlas",
            pt="Cartão: comprar bitcoin significa ter BTC em uma exchange ou em autocustódia com chaves sob seu controle",
            fr="Encadré : acheter du bitcoin, c’est détenir du BTC sur une plateforme ou en auto-conservation avec vos clés",
            de="Faktenkarte: Bitcoin kaufen heißt BTC an einer Börse oder in Self-Custody mit eigenen Schlüsseln halten",
            ru="Карточка: покупка биткоина — это BTC на бирже или в самокастоди с ключами под вашим контролем",
            tr="Bilgi kartı: bitcoin almak, borsada veya kendi saklamanızda kontrol ettiğiniz anahtarlarla BTC tutmak demektir",
            id="Kartu fakta: membeli bitcoin berarti memegang BTC di bursa atau self-custody dengan kunci yang Anda kendalikan",
            ja="ファクトカード：ビットコイン購入とは、取引所または自分で管理する鍵によるセルフカストディでBTCを保有すること",
            ko="팩트 카드: 비트코인 구매는 거래소 또는 본인이 키를 통제하는 셀프 커스터디로 BTC를 보유하는 것"),
            tr_map(CAPTION_SOURCE, src="Coinbase Help, FINRA")),
    ]


def build_binance_hack():
    slug = "binance-hack-north-korea-memecoin-laundering-nov-2026"
    d = OUT / slug
    chart = make_bar_chart(
        d / "chart-binance-hack-funds",
        ["Total stolen", "Frozen or intercepted", "Still in linked addresses"],
        [6430, 2850, 3110],
        "Binance hack: where the money stood on Nov. 6 (Elliptic, $ millions)",
        colors=["#f87171", "#34d399", "#f7931a"],
        value_fmt=lambda v: f"${v/1000:.2f}B",
    )
    card = make_fact_card(
        d / "fact-near-memecoins",
        label="Laundering trick",
        big="~$430,000",
        sub="Stolen NEAR moved through six home-made meme tokens, Nov 5-7; each cost about $90 to create (Elliptic)",
        footer="Elliptic research · Nov 9, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart: $6.43B stolen from Binance, $2.85B frozen or intercepted, $3.11B still in linked addresses", {
            "es": "Gráfico de barras: 6.430 M$ robados a Binance, 2.850 M$ congelados o interceptados, 3.110 M$ aún en direcciones vinculadas",
            "pt": "Gráfico de barras: US$ 6,43 bi roubados da Binance, US$ 2,85 bi congelados ou interceptados, US$ 3,11 bi ainda em endereços ligados",
            "fr": "Graphique : 6,43 Md$ volés à Binance, 2,85 Md$ gelés ou interceptés, 3,11 Md$ encore sur des adresses liées",
            "de": "Balkendiagramm: 6,43 Mrd. $ bei Binance gestohlen, 2,85 Mrd. $ eingefroren oder abgefangen, 3,11 Mrd. $ noch auf verknüpften Adressen",
            "ru": "Диаграмма: у Binance украдено $6,43 млрд, заморожено или перехвачено $2,85 млрд, $3,11 млрд всё ещё на связанных адресах",
            "tr": "Grafik: Binance'ten 6,43 milyar $ çalındı, 2,85 milyar $ donduruldu veya durduruldu, 3,11 milyar $ hâlâ bağlantılı adreslerde",
            "id": "Grafik batang: US$6,43 miliar dicuri dari Binance, US$2,85 miliar dibekukan atau dicegat, US$3,11 miliar masih di alamat terkait",
            "ja": "棒グラフ：Binanceから64.3億ドルが盗まれ、28.5億ドルが凍結・差し止め、31.1億ドルが関連アドレスに残存",
            "ko": "막대 차트: 바이낸스에서 64.3억 달러 도난, 28.5억 달러 동결·차단, 31.1억 달러는 연관 주소에 잔존",
         }),
         "caption": tr_map(CAPTION_CHART, src="Elliptic via The Block, Nov 6, 2026")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $430,000 of stolen NEAR moved through six home-made meme tokens", {
            "es": "Tarjeta: unos 430.000 $ en NEAR robados pasaron por seis memecoins creadas a medida",
            "pt": "Cartão: cerca de US$ 430 mil em NEAR roubados passaram por seis memecoins caseiras",
            "fr": "Encadré : environ 430 000 $ de NEAR volés ont transité par six memecoins maison",
            "de": "Faktenkarte: rund 430.000 $ gestohlene NEAR liefen über sechs selbst erstellte Memecoins",
            "ru": "Карточка: около $430 000 украденных NEAR прошли через шесть самодельных мемкоинов",
            "tr": "Kart: çalınan yaklaşık 430.000 $ değerinde NEAR, kendi üretilmiş altı memecoin üzerinden aktarıldı",
            "id": "Kart fakta: sekitar US$430.000 NEAR curian dialirkan lewat enam memecoin buatan sendiri",
            "ja": "カード：盗まれた約43万ドル相当のNEARが自作のミームコイン6種を経由",
            "ko": "카드: 도난당한 약 43만 달러어치 NEAR가 자체 제작 밈코인 6개를 거쳐 이동",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Elliptic")},
    ]


def build_hot_cpi():
    slug = "bitcoin-hot-cpi-etf-outflows-nov-2026"
    d = OUT / slug
    # Farside Investors, U.S. spot bitcoin ETF daily net flows (US$ millions), Nov 2-9, 2026
    days = ["Nov 2", "Nov 3", "Nov 4", "Nov 5", "Nov 6", "Nov 9"]
    flows = [-398.6, -115.6, 74.6, -430.2, -411.9, -201.0]
    chart = make_bar_chart(
        d / "chart-btc-etf-flows-nov-2-9",
        days, flows,
        "U.S. spot bitcoin ETF daily net flows, Nov 2-9, 2026 ($ millions)",
        colors=["#34d399" if v > 0 else "#f87171" for v in flows],
        value_fmt=lambda v: f"{'+' if v > 0 else '-'}${abs(v):,.1f}M",
    )
    card = make_fact_card(
        d / "fact-mara-13597-btc",
        label="Miner selling",
        big="13,597 BTC",
        sub="Sold by MARA Holdings after Q3 ended, at about $81,039 each, for roughly $1.1 billion",
        footer="MARA Q3 2026 shareholder letter · Nov 9, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of U.S. spot bitcoin ETF daily net flows: -$398.6M Nov 2, -$115.6M Nov 3, +$74.6M Nov 4, -$430.2M Nov 5, -$411.9M Nov 6, -$201.0M Nov 9", {
            "es": "Gráfico de barras de los flujos netos diarios de los ETF de bitcoin al contado en EE. UU.: -398,6 M$ el 2 de nov., -115,6 M$ el 3, +74,6 M$ el 4, -430,2 M$ el 5, -411,9 M$ el 6 y -201,0 M$ el 9",
            "pt": "Gráfico de barras dos fluxos líquidos diários dos ETFs de bitcoin à vista nos EUA: -US$ 398,6 mi em 2/11, -US$ 115,6 mi em 3/11, +US$ 74,6 mi em 4/11, -US$ 430,2 mi em 5/11, -US$ 411,9 mi em 6/11 e -US$ 201,0 mi em 9/11",
            "fr": "Graphique des flux nets quotidiens des ETF bitcoin au comptant américains : -398,6 M$ le 2 nov., -115,6 M$ le 3, +74,6 M$ le 4, -430,2 M$ le 5, -411,9 M$ le 6 et -201,0 M$ le 9",
            "de": "Balkendiagramm der täglichen Nettozuflüsse von US-Spot-Bitcoin-ETFs: -398,6 Mio. $ am 2. Nov., -115,6 Mio. $ am 3., +74,6 Mio. $ am 4., -430,2 Mio. $ am 5., -411,9 Mio. $ am 6. und -201,0 Mio. $ am 9. Nov.",
            "ru": "Диаграмма ежедневных чистых потоков спотовых биткоин-ETF в США: -$398,6 млн 2 ноября, -$115,6 млн 3-го, +$74,6 млн 4-го, -$430,2 млн 5-го, -$411,9 млн 6-го и -$201,0 млн 9 ноября",
            "tr": "ABD spot bitcoin ETF'lerinin günlük net akışları: 2 Kasım -398,6 milyon $, 3 Kasım -115,6 milyon $, 4 Kasım +74,6 milyon $, 5 Kasım -430,2 milyon $, 6 Kasım -411,9 milyon $, 9 Kasım -201,0 milyon $",
            "id": "Grafik batang arus bersih harian ETF bitcoin spot AS: -US$398,6 juta 2 Nov, -US$115,6 juta 3 Nov, +US$74,6 juta 4 Nov, -US$430,2 juta 5 Nov, -US$411,9 juta 6 Nov, -US$201,0 juta 9 Nov",
            "ja": "米国の現物ビットコインETFの日次純流出入を示す棒グラフ：11月2日-3億9860万ドル、3日-1億1560万ドル、4日+7460万ドル、5日-4億3020万ドル、6日-4億1190万ドル、9日-2億100万ドル",
            "ko": "미국 현물 비트코인 ETF 일별 순유출입 막대 차트: 11월 2일 -3억 9,860만 달러, 3일 -1억 1,560만 달러, 4일 +7,460만 달러, 5일 -4억 3,020만 달러, 6일 -4억 1,190만 달러, 9일 -2억 100만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: MARA Holdings sold 13,597 BTC after the third quarter at about $81,039 each, for roughly $1.1 billion", {
            "es": "Tarjeta: MARA Holdings vendió 13.597 BTC tras el tercer trimestre, a unos 81.039 $ cada uno, por cerca de 1.100 M$",
            "pt": "Cartão: a MARA Holdings vendeu 13.597 BTC após o terceiro trimestre, a cerca de US$ 81.039 cada, por cerca de US$ 1,1 bilhão",
            "fr": "Encadré : MARA Holdings a vendu 13 597 BTC après le troisième trimestre, à environ 81 039 $ l'unité, pour près de 1,1 Md$",
            "de": "Faktenkarte: MARA Holdings verkaufte nach dem dritten Quartal 13.597 BTC zu je rund 81.039 $, für etwa 1,1 Mrd. $",
            "ru": "Карточка: MARA Holdings продала 13 597 BTC после третьего квартала примерно по $81 039 за монету, выручив около $1,1 млрд",
            "tr": "Kart: MARA Holdings üçüncü çeyrekten sonra tanesi yaklaşık 81.039 $'dan 13.597 BTC sattı ve yaklaşık 1,1 milyar $ elde etti",
            "id": "Kart fakta: MARA Holdings menjual 13.597 BTC setelah kuartal ketiga di harga sekitar US$81.039 per koin, senilai sekitar US$1,1 miliar",
            "ja": "カード：MARA Holdingsは第3四半期後に13,597 BTCを1枚あたり約81,039ドルで売却し、約11億ドルを得た",
            "ko": "카드: MARA 홀딩스는 3분기 이후 13,597 BTC를 개당 약 81,039달러에 팔아 약 11억 달러를 확보했다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="MARA Holdings Q3 2026 shareholder letter")},
    ]


def build_mexc():
    slug = "binance-blocks-mexc-fincen-order-nov-2026"
    d = OUT / slug
    # FinCEN order on MEXC Global (91 FR 72420, Nov 10, 2026), selected findings, May 2021-May 2026, US$ billions.
    labels = ["Exchanges without\nID checks", "Cybercrime\nactors", "Iran-linked\nexposure", "Russian sanctions\nevasion"]
    vals = [2.9, 1.99, 1.87, 1.5]
    chart = make_bar_chart(
        d / "chart-fincen-mexc-findings",
        labels, vals,
        "MEXC Global: selected FinCEN findings, May 2021 - May 2026 ($ billions)",
        colors=["#f7931a", "#f87171", "#fbbf24", "#60a5fa"],
        value_fmt=lambda v: f"${v:.2f}B" if v not in (2.9, 1.5) else f"~${v:.1f}B",
        axis_fmt=lambda x, _p: f"${x:,.1f}B",
    )
    card = make_fact_card(
        d / "fact-mexc-dec-10",
        label="FinCEN order takes effect",
        big="Dec. 10, 2026",
        sub="From that date, U.S. financial institutions may not send funds to or receive funds from MEXC Global",
        footer="FinCEN order · Federal Register, Nov 10, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of selected FinCEN findings on MEXC Global, May 2021 to May 2026: about $2.9B with exchanges that skip ID checks, $1.99B tied to cybercrime actors, $1.87B with exposure to Iran and nearly $1.5B linked to Russian sanctions evasion", {
            "es": "Gráfico de barras con hallazgos de FinCEN sobre MEXC Global, de mayo de 2021 a mayo de 2026: unos 2.900 M$ con exchanges sin verificación de identidad, 1.990 M$ ligados a ciberdelincuentes, 1.870 M$ con exposición a Irán y casi 1.500 M$ vinculados a la evasión de sanciones rusas",
            "pt": "Gráfico de barras com conclusões da FinCEN sobre a MEXC Global, de maio de 2021 a maio de 2026: cerca de US$ 2,9 bi com corretoras sem verificação de identidade, US$ 1,99 bi ligados a cibercriminosos, US$ 1,87 bi com exposição ao Irã e quase US$ 1,5 bi ligados à evasão de sanções russas",
            "fr": "Graphique des conclusions de FinCEN sur MEXC Global, de mai 2021 à mai 2026 : environ 2,9 Md$ avec des plateformes sans vérification d'identité, 1,99 Md$ liés à des cybercriminels, 1,87 Md$ exposés à l'Iran et près de 1,5 Md$ liés au contournement des sanctions russes",
            "de": "Balkendiagramm mit ausgewählten FinCEN-Erkenntnissen zu MEXC Global, Mai 2021 bis Mai 2026: rund 2,9 Mrd. $ mit Börsen ohne Identitätsprüfung, 1,99 Mrd. $ mit Bezug zu Cyberkriminellen, 1,87 Mrd. $ mit Iran-Bezug und fast 1,5 Mrd. $ im Zusammenhang mit der Umgehung von Russland-Sanktionen",
            "ru": "Диаграмма выводов FinCEN о MEXC Global за май 2021 — май 2026: около $2,9 млрд с биржами без проверки личности, $1,99 млрд, связанных с киберпреступниками, $1,87 млрд с привязкой к Ирану и почти $1,5 млрд, связанных с обходом российских санкций",
            "tr": "FinCEN'in MEXC Global hakkındaki bazı bulgularını gösteren grafik, Mayıs 2021 - Mayıs 2026: kimlik doğrulaması yapmayan borsalarla yaklaşık 2,9 milyar $, siber suçlularla bağlantılı 1,99 milyar $, İran bağlantılı 1,87 milyar $ ve Rusya yaptırımlarından kaçınmayla bağlantılı yaklaşık 1,5 milyar $",
            "id": "Grafik batang temuan FinCEN tentang MEXC Global, Mei 2021 hingga Mei 2026: sekitar US$2,9 miliar dengan bursa tanpa verifikasi identitas, US$1,99 miliar terkait pelaku kejahatan siber, US$1,87 miliar terkait Iran, dan hampir US$1,5 miliar terkait penghindaran sanksi Rusia",
            "ja": "FinCENによるMEXC Globalの主な認定額（2021年5月〜2026年5月）を示す棒グラフ：本人確認をしない取引所との取引約29億ドル、サイバー犯罪関連19.9億ドル、イラン関連18.7億ドル、ロシア制裁回避関連約15億ドル",
            "ko": "FinCEN이 밝힌 MEXC Global 관련 주요 수치(2021년 5월~2026년 5월) 막대 차트: 신원 확인 없는 거래소와의 거래 약 29억 달러, 사이버 범죄 관련 19.9억 달러, 이란 관련 18.7억 달러, 러시아 제재 회피 관련 약 15억 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="FinCEN order on MEXC Global (categories can overlap)")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the FinCEN order takes effect Dec. 10, 2026; from then U.S. financial institutions may not send funds to or receive funds from MEXC Global", {
            "es": "Tarjeta: la orden de FinCEN entra en vigor el 10 de diciembre de 2026; desde entonces las instituciones financieras de EE. UU. no podrán enviar ni recibir fondos de MEXC Global",
            "pt": "Cartão: a ordem da FinCEN entra em vigor em 10 de dezembro de 2026; a partir daí instituições financeiras dos EUA não poderão enviar nem receber fundos da MEXC Global",
            "fr": "Encadré : l'ordonnance de FinCEN entre en vigueur le 10 décembre 2026 ; dès lors, les institutions financières américaines ne pourront plus envoyer ni recevoir de fonds de MEXC Global",
            "de": "Faktenkarte: Die FinCEN-Anordnung gilt ab dem 10. Dezember 2026; danach dürfen US-Finanzinstitute keine Gelder mehr an MEXC Global senden oder von dort empfangen",
            "ru": "Карточка: приказ FinCEN вступает в силу 10 декабря 2026 года; с этой даты финансовые учреждения США не могут отправлять средства в MEXC Global или получать их оттуда",
            "tr": "Kart: FinCEN kararı 10 Aralık 2026'da yürürlüğe giriyor; o tarihten itibaren ABD finans kuruluşları MEXC Global'e para gönderemeyecek ve oradan para alamayacak",
            "id": "Kart fakta: perintah FinCEN berlaku 10 Desember 2026; sejak itu lembaga keuangan AS tidak boleh mengirim dana ke atau menerima dana dari MEXC Global",
            "ja": "カード：FinCENの命令は2026年12月10日に発効し、以後米国の金融機関はMEXC Globalとの資金の送受信を禁じられる",
            "ko": "카드: FinCEN 명령은 2026년 12월 10일 발효되며, 이후 미국 금융기관은 MEXC Global과 자금을 주고받을 수 없다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="FinCEN order, Federal Register (91 FR 72420)")},
    ]


def build_faro():
    slug = "banks-270-million-stablecoin-project-faro-nov-2026"
    d = OUT / slug
    # DefiLlama stablecoins API snapshot, Nov 10, 2026: circulating USD-pegged supply, US$ billions.
    labels = ["USDT\n(Tether)", "USDC\n(Circle)", "USDS", "USDe", "DAI", "All other\nUSD coins"]
    vals = [176.3, 70.1, 5.3, 4.9, 4.7, 32.1]
    chart = make_bar_chart(
        d / "chart-usd-stablecoin-supply",
        labels, vals,
        r"Dollar stablecoins in circulation, Nov. 10, 2026 (\$ billions; total ~\$293.4B)",
        colors=["#34d399", "#60a5fa", "#f7931a", "#f7931a", "#f7931a", "#94a3b8"],
        value_fmt=lambda v: f"${v:,.1f}B",
        axis_fmt=lambda x, _p: f"${x:,.0f}B",
    )
    card = make_fact_card(
        d / "fact-faro-270m",
        label="Bank stablecoin venture",
        big="$270 million",
        sub="Committed by Goldman Sachs, Citi, Santander, Deutsche Bank and other firms to fund five years of operations",
        footer="Bloomberg, as reported by CoinDesk · Nov 10, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of dollar stablecoins in circulation on Nov. 10, 2026: USDT $176.3B, USDC $70.1B, USDS $5.3B, USDe $4.9B, DAI $4.7B, all others $32.1B, total about $293.4B", {
            "es": "Gráfico de barras de las stablecoins en dólares en circulación el 10 de noviembre de 2026: USDT 176.300 M$, USDC 70.100 M$, USDS 5.300 M$, USDe 4.900 M$, DAI 4.700 M$ y el resto 32.100 M$; total de unos 293.400 M$",
            "pt": "Gráfico de barras das stablecoins em dólar em circulação em 10 de novembro de 2026: USDT US$ 176,3 bi, USDC US$ 70,1 bi, USDS US$ 5,3 bi, USDe US$ 4,9 bi, DAI US$ 4,7 bi e as demais US$ 32,1 bi; total de cerca de US$ 293,4 bi",
            "fr": "Graphique des stablecoins en dollars en circulation au 10 novembre 2026 : USDT 176,3 Md$, USDC 70,1 Md$, USDS 5,3 Md$, USDe 4,9 Md$, DAI 4,7 Md$, autres 32,1 Md$, soit environ 293,4 Md$ au total",
            "de": "Balkendiagramm der umlaufenden Dollar-Stablecoins am 10. November 2026: USDT 176,3 Mrd. $, USDC 70,1 Mrd. $, USDS 5,3 Mrd. $, USDe 4,9 Mrd. $, DAI 4,7 Mrd. $, übrige 32,1 Mrd. $, insgesamt rund 293,4 Mrd. $",
            "ru": "Диаграмма долларовых стейблкоинов в обращении на 10 ноября 2026 года: USDT $176,3 млрд, USDC $70,1 млрд, USDS $5,3 млрд, USDe $4,9 млрд, DAI $4,7 млрд, остальные $32,1 млрд, всего около $293,4 млрд",
            "tr": "10 Kasım 2026 itibarıyla dolaşımdaki dolar stablecoin'leri: USDT 176,3 milyar $, USDC 70,1 milyar $, USDS 5,3 milyar $, USDe 4,9 milyar $, DAI 4,7 milyar $, diğerleri 32,1 milyar $; toplam yaklaşık 293,4 milyar $",
            "id": "Grafik batang stablecoin dolar yang beredar pada 10 November 2026: USDT US$176,3 miliar, USDC US$70,1 miliar, USDS US$5,3 miliar, USDe US$4,9 miliar, DAI US$4,7 miliar, lainnya US$32,1 miliar, total sekitar US$293,4 miliar",
            "ja": "2026年11月10日時点で流通するドル建てステーブルコインの棒グラフ：USDT 1763億ドル、USDC 701億ドル、USDS 53億ドル、USDe 49億ドル、DAI 47億ドル、その他321億ドル、合計約2934億ドル",
            "ko": "2026년 11월 10일 기준 유통 중인 달러 스테이블코인 막대 차트: USDT 1,763억 달러, USDC 701억 달러, USDS 53억 달러, USDe 49억 달러, DAI 47억 달러, 기타 321억 달러, 합계 약 2,934억 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="DefiLlama")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $270 million committed by Goldman Sachs, Citi, Santander, Deutsche Bank and other firms to fund five years of the stablecoin venture's operations", {
            "es": "Tarjeta: unos 270 M$ comprometidos por Goldman Sachs, Citi, Santander, Deutsche Bank y otras firmas para financiar cinco años de operaciones de la empresa de stablecoin",
            "pt": "Cartão: cerca de US$ 270 milhões comprometidos por Goldman Sachs, Citi, Santander, Deutsche Bank e outras empresas para financiar cinco anos de operação da empresa de stablecoin",
            "fr": "Encadré : environ 270 M$ engagés par Goldman Sachs, Citi, Santander, Deutsche Bank et d'autres pour financer cinq ans d'activité de la coentreprise de stablecoin",
            "de": "Faktenkarte: rund 270 Mio. $ von Goldman Sachs, Citi, Santander, Deutsche Bank und weiteren Häusern zugesagt, um fünf Jahre Betrieb des Stablecoin-Gemeinschaftsunternehmens zu finanzieren",
            "ru": "Карточка: около $270 млн выделили Goldman Sachs, Citi, Santander, Deutsche Bank и другие компании, чтобы профинансировать пять лет работы совместного стейблкоин-проекта",
            "tr": "Kart: Goldman Sachs, Citi, Santander, Deutsche Bank ve diğer kurumlar stablecoin girişiminin beş yıllık faaliyetini finanse etmek için yaklaşık 270 milyon $ taahhüt etti",
            "id": "Kart fakta: sekitar US$270 juta dijanjikan Goldman Sachs, Citi, Santander, Deutsche Bank, dan perusahaan lain untuk mendanai lima tahun operasi usaha stablecoin itu",
            "ja": "カード：Goldman Sachs、Citi、Santander、Deutsche Bankなどが、ステーブルコイン合弁会社の5年分の運営資金として約2億7000万ドルを拠出",
            "ko": "카드: 골드만삭스, 씨티, 산탄데르, 도이체방크 등이 스테이블코인 합작사의 5년 운영비로 약 2억 7,000만 달러를 약정",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bloomberg via CoinDesk")},
    ]


def fetch_kraken_hourly(start_ts: int, end_ts: int, pair="XBTUSD"):
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=60"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = next(v for k, v in data["result"].items() if k != "last")
    xs, ys = [], []
    for r in rows:
        if start_ts <= int(r[0]) < end_ts:
            xs.append(float(r[0]))
            ys.append(float(r[4]))
    return np.array(xs), np.array(ys)


def build_btc_below_73k():
    slug = "bitcoin-below-73000-lowest-since-august-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 9 00:00 UTC - Nov 11 00:00 UTC; 200-day SMA of Kraken daily closes to Nov 10 = $73,137.
    xs, ys = fetch_kraken_hourly(1794182400, 1794355200)
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-9-10",
        xs, ys,
        title="Bitcoin hourly price, Nov. 9-10, 2026 (Kraken, UTC)",
        hline=73137,
        hlabel="200-day average ≈ $73,137 (Kraken daily closes)",
        date_fmt="%b %d %H:%M",
    )
    card = make_fact_card(
        d / "fact-liquidations-716m",
        label="Forced selling",
        big="$716 million",
        sub="Crypto futures liquidated in 24 hours on Nov. 10, including $589 million of long bets",
        footer="CoinGlass data via FXStreet · Nov 10, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken on Nov. 9 and 10, 2026, falling from about $75,250 to below $73,000 before ending near $73,700, with a dashed line at the 200-day average of about $73,137", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken el 9 y 10 de noviembre de 2026: cae de unos 75.250 $ por debajo de 73.000 $ y termina cerca de 73.700 $, con una línea discontinua en la media de 200 días de unos 73.137 $",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken em 9 e 10 de novembro de 2026: cai de cerca de US$ 75.250 para menos de US$ 73.000 e termina perto de US$ 73.700, com linha tracejada na média de 200 dias de cerca de US$ 73.137",
            "fr": "Courbe du prix horaire du bitcoin sur Kraken les 9 et 10 novembre 2026 : baisse d'environ 75 250 $ sous 73 000 $, puis clôture vers 73 700 $, avec une ligne pointillée sur la moyenne à 200 jours d'environ 73 137 $",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken am 9. und 10. November 2026: Rückgang von rund 75.250 $ auf unter 73.000 $, Schluss bei etwa 73.700 $, gestrichelte Linie beim 200-Tage-Durchschnitt von rund 73.137 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken 9 и 10 ноября 2026 года: падение примерно с $75 250 ниже $73 000 и закрытие около $73 700; пунктир — 200-дневная средняя около $73 137",
            "tr": "Kraken'de 9-10 Kasım 2026 saatlik bitcoin fiyatı: yaklaşık 75.250 $'dan 73.000 $'ın altına düşüş ve 73.700 $ civarında kapanış; kesikli çizgi yaklaşık 73.137 $'lık 200 günlük ortalama",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 9 dan 10 November 2026: turun dari sekitar US$75.250 ke bawah US$73.000 lalu ditutup dekat US$73.700, dengan garis putus-putus di rata-rata 200 hari sekitar US$73.137",
            "ja": "2026年11月9〜10日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約75,250ドルから73,000ドルを割り込み約73,700ドルで終了。破線は約73,137ドルの200日平均",
            "ko": "2026년 11월 9~10일 크라켄 비트코인 시간별 가격 선 차트: 약 75,250달러에서 73,000달러 아래로 하락한 뒤 약 73,700달러로 마감, 점선은 약 73,137달러인 200일 평균",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes; 200-day average calculated by PlainBTC")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $716 million in crypto futures liquidated in 24 hours on Nov. 10, including $589 million of long bets", {
            "es": "Tarjeta: unos 716 M$ en futuros cripto liquidados en 24 horas el 10 de noviembre, de ellos 589 M$ en apuestas alcistas",
            "pt": "Cartão: cerca de US$ 716 milhões em futuros cripto liquidados em 24 horas em 10 de novembro, sendo US$ 589 milhões em apostas de alta",
            "fr": "Encadré : environ 716 M$ de contrats à terme crypto liquidés en 24 heures le 10 novembre, dont 589 M$ de paris à la hausse",
            "de": "Faktenkarte: rund 716 Mio. $ an Krypto-Futures innerhalb von 24 Stunden am 10. November liquidiert, davon 589 Mio. $ Long-Wetten",
            "ru": "Карточка: около $716 млн ликвидаций криптофьючерсов за 24 часа 10 ноября, из них $589 млн — длинные позиции",
            "tr": "Kart: 10 Kasım'da 24 saatte yaklaşık 716 milyon $ kripto vadeli pozisyon tasfiye edildi; bunun 589 milyon $'ı yükseliş pozisyonuydu",
            "id": "Kart fakta: sekitar US$716 juta kontrak berjangka kripto dilikuidasi dalam 24 jam pada 10 November, termasuk US$589 juta posisi long",
            "ja": "カード：11月10日の24時間で約7億1600万ドルの暗号資産先物が清算され、うち5億8900万ドルが買いポジション",
            "ko": "카드: 11월 10일 24시간 동안 약 7억 1,600만 달러 규모 암호화폐 선물이 청산됐고, 그중 5억 8,900만 달러가 롱 포지션",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via FXStreet")},
    ]


def make_timeline_card(path: Path, label: str, steps, footer: str, w=1200, h=630, margin=220, wrap_w=300) -> Path:
    img = gradient_bg(w, h)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 10, h], fill=ORANGE)
    lf = load_font(FONT_BOLD, 28)
    df = load_font(FONT_BOLD, 34)
    tf = load_font(FONT_REG, 25)
    ff = load_font(FONT_REG, 22)
    brand = load_font(FONT_BOLD, 24)
    draw.text((56, 48), label.upper(), font=lf, fill=ORANGE)
    lw = draw.textlength(label.upper(), font=lf)
    draw.rectangle([56, 86, 56 + max(48, int(lw * 0.4)), 90], fill=ORANGE)
    n = len(steps)
    x0, x1, ly = margin, w - margin, 210
    draw.line([(x0, ly), (x1, ly)], fill=(51, 65, 85), width=6)
    colw = (x1 - x0) / max(n - 1, 1)
    for i, (date, text, col) in enumerate(steps):
        cx = int(x0 + i * colw)
        draw.ellipse([cx - 18, ly - 18, cx + 18, ly + 18], fill=col, outline=WHITE, width=3)
        dw = draw.textlength(date, font=df)
        draw.text((cx - dw / 2, ly - 80), date, font=df, fill=WHITE)
        lines = wrap(draw, text, tf, wrap_w, max_lines=6)
        for j, line in enumerate(lines):
            tw = draw.textlength(line, font=tf)
            draw.text((cx - tw / 2, ly + 46 + j * 34), line, font=tf, fill=GRAY)
    draw.text((56, h - 56), footer, font=ff, fill=MUTED)
    draw.text((w - 210, h - 56), "Plain", font=brand, fill=WHITE)
    pw = draw.textlength("Plain", font=brand)
    draw.text((w - 210 + pw, h - 56), "BTC", font=brand, fill=ORANGE)
    return save_image(img, path)


def build_ios_flaw():
    slug = "binance-warns-iphone-ios-flaw-wallet-keys-nov-2026"
    d = OUT / slug
    tl = make_timeline_card(
        d / "timeline-worse-query",
        "How the warning unfolded",
        [
            ("Nov. 8", "Researcher publishes the worse_query sandbox escape on GitHub", (248, 113, 113)),
            ("Nov. 9", "Apple ships iOS 27.2.1 and 26.7.3; notes do not mention worse_query", (96, 165, 250)),
            ("Nov. 10", "Binance warns that seed phrases and keys could be exposed", ORANGE),
        ],
        footer="The Hacker News · Apple security releases · Binance on X",
    )
    card = make_fact_card(
        d / "fact-ios-versions",
        label="Versions Binance named",
        big="iOS 26.7.1 · 27.0.1 · 27.2",
        sub="Binance: \u201cThis is an iOS-level issue, not unique to Binance.\u201d No thefts have been reported.",
        footer="Binance on X, via Bitcoin Magazine · Nov 10, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Nov. 8, a researcher publishes the worse_query sandbox escape; Nov. 9, Apple ships iOS 27.2.1 and 26.7.3 without mentioning it; Nov. 10, Binance warns that seed phrases and keys could be exposed", {
            "es": "Cronología: 8 de nov., un investigador publica el escape de sandbox worse_query; 9 de nov., Apple lanza iOS 27.2.1 y 26.7.3 sin mencionarlo; 10 de nov., Binance advierte que frases semilla y claves podrían quedar expuestas",
            "pt": "Linha do tempo: 8 de nov., um pesquisador publica a fuga de sandbox worse_query; 9 de nov., a Apple lança o iOS 27.2.1 e o 26.7.3 sem mencioná-la; 10 de nov., a Binance alerta que frases-semente e chaves podem ficar expostas",
            "fr": "Chronologie : 8 nov., un chercheur publie l'évasion de sandbox worse_query ; 9 nov., Apple publie iOS 27.2.1 et 26.7.3 sans la mentionner ; 10 nov., Binance avertit que des phrases de récupération et des clés pourraient être exposées",
            "de": "Zeitleiste: 8. Nov., ein Forscher veröffentlicht den Sandbox-Ausbruch worse_query; 9. Nov., Apple veröffentlicht iOS 27.2.1 und 26.7.3 ohne Erwähnung; 10. Nov., Binance warnt, dass Seed-Phrasen und Schlüssel offengelegt werden könnten",
            "ru": "Хронология: 8 ноября исследователь публикует обход песочницы worse_query; 9 ноября Apple выпускает iOS 27.2.1 и 26.7.3, не упоминая его; 10 ноября Binance предупреждает, что сид-фразы и ключи могут оказаться под угрозой",
            "tr": "Zaman çizelgesi: 8 Kasım'da bir araştırmacı worse_query korumalı alan kaçışını yayımlıyor; 9 Kasım'da Apple, ondan söz etmeden iOS 27.2.1 ve 26.7.3'ü çıkarıyor; 10 Kasım'da Binance kurtarma ifadelerinin ve anahtarların açığa çıkabileceği uyarısını yapıyor",
            "id": "Linimasa: 8 Nov, peneliti merilis celah sandbox worse_query; 9 Nov, Apple merilis iOS 27.2.1 dan 26.7.3 tanpa menyebutnya; 10 Nov, Binance memperingatkan bahwa frasa pemulihan dan kunci bisa terekspos",
            "ja": "時系列：11月8日、研究者がサンドボックス回避「worse_query」を公開。11月9日、AppleがiOS 27.2.1と26.7.3を配信（言及なし）。11月10日、Binanceがシードフレーズや鍵が漏れるおそれを警告",
            "ko": "타임라인: 11월 8일 연구자가 샌드박스 탈출 기법 worse_query 공개, 11월 9일 애플이 이를 언급하지 않은 채 iOS 27.2.1·26.7.3 배포, 11월 10일 바이낸스가 시드 문구와 키 노출 가능성 경고",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="The Hacker News; Apple security releases; Binance")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Binance named iOS 26.7.1, 27.0.1 and 27.2 as affected and said it is an iOS-level issue, not unique to Binance; no thefts have been reported", {
            "es": "Tarjeta: Binance señaló iOS 26.7.1, 27.0.1 y 27.2 como afectados y dijo que es un problema de iOS, no exclusivo de Binance; no se han reportado robos",
            "pt": "Cartão: a Binance apontou o iOS 26.7.1, 27.0.1 e 27.2 como afetados e disse que o problema é do iOS, não exclusivo da Binance; nenhum roubo foi relatado",
            "fr": "Encadré : Binance cite iOS 26.7.1, 27.0.1 et 27.2 comme concernés et parle d'un problème propre à iOS, pas à Binance ; aucun vol n'a été signalé",
            "de": "Faktenkarte: Binance nennt iOS 26.7.1, 27.0.1 und 27.2 als betroffen und spricht von einem iOS-Problem, das nicht nur Binance betrifft; Diebstähle wurden nicht gemeldet",
            "ru": "Карточка: Binance назвала затронутыми iOS 26.7.1, 27.0.1 и 27.2 и подчеркнула, что это проблема iOS, а не только Binance; краж пока не зафиксировано",
            "tr": "Kart: Binance etkilenen sürümler olarak iOS 26.7.1, 27.0.1 ve 27.2'yi gösterdi ve sorunun yalnızca Binance'e değil iOS'a ait olduğunu söyledi; bildirilen bir hırsızlık yok",
            "id": "Kart fakta: Binance menyebut iOS 26.7.1, 27.0.1, dan 27.2 terdampak dan mengatakan ini masalah iOS, bukan khusus Binance; belum ada laporan pencurian",
            "ja": "カード：BinanceはiOS 26.7.1、27.0.1、27.2が影響を受けるとし、Binance固有ではなくiOSの問題だと説明。盗難の報告はない",
            "ko": "카드: 바이낸스는 iOS 26.7.1, 27.0.1, 27.2가 영향을 받는다며 바이낸스만의 문제가 아닌 iOS 차원의 문제라고 밝혔다. 도난 보고는 없다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Binance on X, via Bitcoin Magazine")},
    ]


def build_across():
    slug = "across-protocol-domain-hijack-phishing-nov-2026"
    d = OUT / slug
    tl = make_timeline_card(
        d / "timeline-across-hijack",
        "How the hijack unfolded",
        [
            ("18:45 UTC", "Attacker takes over across.to via social engineering at registrar Namecheap", (248, 113, 113)),
            ("+15 min", "Across alerted; SEAL911 and Cloudflare get the fake site flagged and blocked", (96, 165, 250)),
            ("Nov. 11", "Domain back under Across's control; affected users to be made whole", ORANGE),
        ],
        footer="Across on X, via The Block and Cointelegraph · Nov 10-11, 2026",
    )
    card = make_fact_card(
        d / "fact-across-350k",
        label="Estimated user losses",
        big="~$350,000",
        sub="Drained through fake token approvals and permits on Ethereum, Arbitrum, Base, BNB Chain, Ink and Plasma",
        footer="GoPlus estimate, via The Block · Nov 11, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: at 18:45 UTC on Nov. 10 an attacker takes over across.to through social engineering at registrar Namecheap; within 15 minutes Across is alerted and SEAL911 and Cloudflare get the fake site flagged and blocked; on Nov. 11 the domain is back under Across's control and affected users are promised repayment", {
            "es": "Cronología: a las 18:45 UTC del 10 de noviembre un atacante toma across.to mediante ingeniería social en el registrador Namecheap; en 15 minutos Across recibe la alerta y SEAL911 y Cloudflare marcan y bloquean el sitio falso; el 11 de noviembre el dominio vuelve a manos de Across, que promete compensar a los afectados",
            "pt": "Linha do tempo: às 18:45 UTC de 10 de novembro um invasor assume o across.to por engenharia social na registradora Namecheap; em 15 minutos a Across é alertada e SEAL911 e Cloudflare sinalizam e bloqueiam o site falso; em 11 de novembro o domínio volta ao controle da Across, que promete ressarcir os afetados",
            "fr": "Chronologie : à 18 h 45 UTC le 10 novembre, un attaquant prend le contrôle d'across.to par ingénierie sociale chez le registraire Namecheap ; en 15 minutes, Across est alerté et SEAL911 et Cloudflare signalent et bloquent le faux site ; le 11 novembre, Across récupère le domaine et promet d'indemniser les victimes",
            "de": "Zeitleiste: Um 18:45 UTC am 10. November übernimmt ein Angreifer across.to per Social Engineering beim Registrar Namecheap; innerhalb von 15 Minuten wird Across alarmiert, SEAL911 und Cloudflare lassen die gefälschte Seite markieren und sperren; am 11. November ist die Domain wieder unter Kontrolle von Across, Betroffene sollen entschädigt werden",
            "ru": "Хронология: в 18:45 UTC 10 ноября злоумышленник захватывает across.to с помощью социальной инженерии у регистратора Namecheap; в течение 15 минут Across получает сигнал, а SEAL911 и Cloudflare помечают и блокируют фальшивый сайт; 11 ноября домен снова под контролем Across, пострадавшим обещана компенсация",
            "tr": "Zaman çizelgesi: 10 Kasım 18:45 UTC'de bir saldırgan, alan adı kayıt şirketi Namecheap'e yönelik sosyal mühendislikle across.to'yu ele geçiriyor; 15 dakika içinde Across uyarı alıyor, SEAL911 ve Cloudflare sahte siteyi işaretleyip engelliyor; 11 Kasım'da alan adı yeniden Across'un kontrolünde ve etkilenenlere tazminat sözü veriliyor",
            "id": "Linimasa: pukul 18.45 UTC pada 10 November penyerang mengambil alih across.to lewat rekayasa sosial di registrar Namecheap; dalam 15 menit Across menerima peringatan, SEAL911 dan Cloudflare menandai dan memblokir situs palsu; pada 11 November domain kembali dikuasai Across, yang berjanji mengganti kerugian pengguna",
            "ja": "時系列：11月10日18:45（UTC）、攻撃者がレジストラNamecheapへのソーシャルエンジニアリングでacross.toを乗っ取る。15分以内にAcrossが検知し、SEAL911とCloudflareが偽サイトを警告・遮断。11月11日、ドメインはAcrossの管理下に戻り、被害者への全額補償を表明",
            "ko": "타임라인: 11월 10일 18:45(UTC) 공격자가 도메인 등록업체 Namecheap을 노린 사회공학 공격으로 across.to를 장악, 15분 안에 Across가 경보를 받고 SEAL911과 Cloudflare가 가짜 사이트를 경고·차단, 11월 11일 도메인이 Across 관리로 돌아오고 피해자 전액 보상 약속",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Across on X, via The Block and Cointelegraph")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: an estimated $350,000 drained through fake token approvals and permits on Ethereum, Arbitrum, Base, BNB Chain, Ink and Plasma, according to GoPlus", {
            "es": "Tarjeta: unos 350.000 $ robados mediante aprobaciones de tokens y permisos falsos en Ethereum, Arbitrum, Base, BNB Chain, Ink y Plasma, según GoPlus",
            "pt": "Cartão: cerca de US$ 350.000 drenados por aprovações de tokens e permissões falsas em Ethereum, Arbitrum, Base, BNB Chain, Ink e Plasma, segundo a GoPlus",
            "fr": "Encadré : environ 350 000 $ siphonnés via de fausses approbations de jetons et signatures « permit » sur Ethereum, Arbitrum, Base, BNB Chain, Ink et Plasma, selon GoPlus",
            "de": "Faktenkarte: geschätzt rund 350.000 $ über gefälschte Token-Freigaben und Permits auf Ethereum, Arbitrum, Base, BNB Chain, Ink und Plasma abgezogen, laut GoPlus",
            "ru": "Карточка: по оценке GoPlus, около $350 000 украдено через поддельные разрешения на токены и подписи permit в сетях Ethereum, Arbitrum, Base, BNB Chain, Ink и Plasma",
            "tr": "Kart: GoPlus'a göre Ethereum, Arbitrum, Base, BNB Chain, Ink ve Plasma ağlarında sahte token onayları ve izinlerle tahminen yaklaşık 350.000 $ çalındı",
            "id": "Kart fakta: sekitar US$350.000 dikuras lewat persetujuan token dan izin palsu di Ethereum, Arbitrum, Base, BNB Chain, Ink, dan Plasma, menurut GoPlus",
            "ja": "カード：GoPlusの推計では、Ethereum、Arbitrum、Base、BNB Chain、Ink、Plasma上で偽のトークン承認や署名を通じて約35万ドルが流出",
            "ko": "카드: GoPlus 추정에 따르면 이더리움, 아비트럼, 베이스, BNB 체인, 잉크, 플라즈마에서 가짜 토큰 승인과 퍼밋 서명으로 약 35만 달러가 탈취됐다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="GoPlus estimate, via The Block")},
    ]


def build_okxice():
    slug = "okxice-tokenized-stocks-launch-nov-23-2026"
    d = OUT / slug
    # CoinDesk tally / OKXICE Nov 5 public notice / OKXICE announcement Nov 11, 2026.
    labels = ["Companies on\noriginal list", "Of those,\nobjected", "Total issuer\nobjections", "Assets confirmed\nfor launch", "Direxion\nETFs"]
    vals = [62, 56, 67, 70, 59]
    chart = make_bar_chart(
        d / "chart-okxice-numbers",
        labels, vals,
        "OKXICE tokenized stock venue: the numbers before launch",
        colors=["#94a3b8", "#f87171", "#f87171", "#f7931a", "#60a5fa"],
        value_fmt=lambda v: "70+" if v == 70 else f"{v:.0f}",
        axis_fmt=lambda x, _p: f"{x:.0f}",
    )
    card = make_fact_card(
        d / "fact-okxice-nov-23",
        label="Launch date",
        big="Nov. 23, 9 a.m. ET",
        sub="OKXICE opens 24/7 tokenized stock trading to eligible U.S. OKX customers, with more than 70 assets confirmed",
        footer="OKXICE announcement, via Unchained and CoinDesk · Nov 11, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of OKXICE figures before launch: 62 companies on the original list, 56 of them objected, 67 total issuer objections, more than 70 assets confirmed for launch and 59 Direxion ETFs", {
            "es": "Gráfico de barras con las cifras de OKXICE antes del lanzamiento: 62 empresas en la lista original, 56 de ellas se opusieron, 67 objeciones de emisores en total, más de 70 activos confirmados y 59 ETF de Direxion",
            "pt": "Gráfico de barras com os números da OKXICE antes do lançamento: 62 empresas na lista original, 56 delas se opuseram, 67 objeções de emissores no total, mais de 70 ativos confirmados e 59 ETFs da Direxion",
            "fr": "Graphique des chiffres d'OKXICE avant le lancement : 62 entreprises sur la liste initiale, dont 56 se sont opposées, 67 objections d'émetteurs au total, plus de 70 actifs confirmés et 59 ETF de Direxion",
            "de": "Balkendiagramm mit OKXICE-Zahlen vor dem Start: 62 Unternehmen auf der ursprünglichen Liste, 56 davon widersprachen, insgesamt 67 Einsprüche von Emittenten, mehr als 70 bestätigte Werte und 59 Direxion-ETFs",
            "ru": "Диаграмма с цифрами OKXICE перед запуском: 62 компании в исходном списке, 56 из них возразили, всего 67 возражений эмитентов, более 70 подтверждённых активов и 59 ETF Direxion",
            "tr": "OKXICE'ın lansman öncesi rakamlarını gösteren grafik: ilk listede 62 şirket, bunlardan 56'sı itiraz etti, toplam 67 ihraççı itirazı, 70'ten fazla onaylı varlık ve 59 Direxion ETF'i",
            "id": "Grafik batang angka OKXICE sebelum peluncuran: 62 perusahaan di daftar awal, 56 di antaranya keberatan, total 67 keberatan emiten, lebih dari 70 aset dikonfirmasi, dan 59 ETF Direxion",
            "ja": "OKXICEのローンチ前の数字を示す棒グラフ：当初リストの企業62社、うち56社が異議、発行体の異議は計67件、確定した銘柄は70超、DirexionのETFは59本",
            "ko": "OKXICE 출시 전 수치 막대 차트: 최초 목록 기업 62곳, 그중 56곳 반대, 발행사 반대 총 67건, 확정 자산 70개 이상, 디렉시온 ETF 59개",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinDesk tally; OKXICE public notice (Nov. 5) and announcement (Nov. 11)")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: OKXICE opens 24/7 tokenized stock trading at 9 a.m. ET on Nov. 23 to eligible U.S. OKX customers, with more than 70 assets confirmed", {
            "es": "Tarjeta: OKXICE abre el trading 24/7 de acciones tokenizadas el 23 de noviembre a las 9 a. m. (hora del Este) para clientes elegibles de OKX en EE. UU., con más de 70 activos confirmados",
            "pt": "Cartão: a OKXICE abre a negociação 24/7 de ações tokenizadas em 23 de novembro, às 9h (horário do Leste dos EUA), para clientes elegíveis da OKX nos EUA, com mais de 70 ativos confirmados",
            "fr": "Encadré : OKXICE ouvre le 23 novembre à 9 h (heure de l'Est) le trading 24 h/24 d'actions tokenisées aux clients américains éligibles d'OKX, avec plus de 70 actifs confirmés",
            "de": "Faktenkarte: OKXICE startet am 23. November um 9 Uhr (US-Ostküstenzeit) den Rund-um-die-Uhr-Handel mit tokenisierten Aktien für berechtigte US-Kunden von OKX; mehr als 70 Werte sind bestätigt",
            "ru": "Карточка: OKXICE откроет круглосуточную торговлю токенизированными акциями 23 ноября в 9:00 по восточному времени для подходящих клиентов OKX в США; подтверждено более 70 активов",
            "tr": "Kart: OKXICE, 23 Kasım'da ABD Doğu saatiyle 09.00'da uygun ABD'li OKX müşterilerine 7/24 tokenize hisse işlemlerini açıyor; 70'ten fazla varlık onaylandı",
            "id": "Kart fakta: OKXICE membuka perdagangan saham tokenisasi 24/7 pada 23 November pukul 09.00 waktu Timur AS untuk nasabah OKX AS yang memenuhi syarat, dengan lebih dari 70 aset dikonfirmasi",
            "ja": "カード：OKXICEは11月23日午前9時（米東部時間）、対象となる米国のOKX顧客向けにトークン化株式の24時間取引を開始。確定銘柄は70超",
            "ko": "카드: OKXICE는 11월 23일 오전 9시(미 동부시간) 자격을 갖춘 미국 OKX 고객에게 토큰화 주식 24시간 거래를 개시하며, 확정 자산은 70개 이상",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="OKXICE announcement, via Unchained and CoinDesk")},
    ]


def fetch_usdt_supply(days: int = 90):
    """Daily USDT circulating supply (USD billions) from DefiLlama's public stablecoins API."""
    url = "https://stablecoins.llama.fi/stablecoin/1"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = data["tokens"][-(days + 1):]
    xs = np.array([float(r["date"]) for r in rows])
    ys = np.array([r["circulating"]["peggedUSD"] / 1e9 for r in rows])
    return xs, ys


def build_stablecoin_shrink():
    slug = "stablecoin-supply-shrinks-usdt-tether-nov-2026"
    d = OUT / slug
    # DefiLlama USDT circulating supply, daily, Aug 13 - Nov 11, 2026: peak $184.4B (Oct 9), $175.9B on Nov 11.
    xs, ys = fetch_usdt_supply(90)
    chart = make_line_chart(
        d / "chart-usdt-supply-90d",
        xs, ys,
        title="Tether (USDT) supply in circulation, last 90 days (DefiLlama)",
        yfmt=lambda x, _p: f"${x:,.0f}B",
    )
    card = make_fact_card(
        d / "fact-usdt-6-6b",
        label="USDT shrinking",
        big="-$6.6 billion",
        sub="Drop in Tether's USDT market cap over 60 days to Nov. 7, more than double the $3.2 billion fall after FTX collapsed in 2022",
        footer="CryptoQuant, via The Block · Nov 10-11, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of Tether's USDT supply over the last 90 days: it climbs to a peak of about $184.4 billion on Oct. 9, 2026, then falls to about $175.9 billion by Nov. 11", {
            "es": "Gráfico de líneas del suministro de USDT de Tether en los últimos 90 días: sube hasta un máximo de unos 184.400 millones de dólares el 9 de octubre de 2026 y cae a unos 175.900 millones el 11 de noviembre",
            "pt": "Gráfico de linha da oferta de USDT da Tether nos últimos 90 dias: sobe até um pico de cerca de US$ 184,4 bilhões em 9 de outubro de 2026 e cai para cerca de US$ 175,9 bilhões em 11 de novembro",
            "fr": "Courbe de l'offre d'USDT de Tether sur 90 jours : elle grimpe jusqu'à un pic d'environ 184,4 milliards de dollars le 9 octobre 2026, puis recule à environ 175,9 milliards le 11 novembre",
            "de": "Liniendiagramm des USDT-Umlaufs von Tether in den letzten 90 Tagen: Anstieg auf einen Höchststand von rund 184,4 Mrd. $ am 9. Oktober 2026, danach Rückgang auf rund 175,9 Mrd. $ bis zum 11. November",
            "ru": "Линейный график предложения USDT от Tether за последние 90 дней: рост до пика около $184,4 млрд 9 октября 2026 года, затем снижение примерно до $175,9 млрд к 11 ноября",
            "tr": "Tether'in USDT arzının son 90 günlük çizgi grafiği: 9 Ekim 2026'da yaklaşık 184,4 milyar $ ile zirveye çıkıyor, ardından 11 Kasım'a kadar yaklaşık 175,9 milyar $'a geriliyor",
            "id": "Grafik garis pasokan USDT Tether dalam 90 hari terakhir: naik ke puncak sekitar US$184,4 miliar pada 9 Oktober 2026, lalu turun ke sekitar US$175,9 miliar pada 11 November",
            "ja": "過去90日間のテザー（USDT）流通量の折れ線グラフ：2026年10月9日に約1844億ドルでピークを付けた後、11月11日には約1759億ドルに減少",
            "ko": "최근 90일간 테더(USDT) 유통량 선 차트: 2026년 10월 9일 약 1,844억 달러로 정점을 찍은 뒤 11월 11일 약 1,759억 달러로 감소",
         }),
         "caption": tr_map(CAPTION_CHART, src="DefiLlama stablecoins data (USDT circulating supply)")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Tether's USDT market cap fell $6.6 billion over 60 days to Nov. 7, more than double the $3.2 billion drop after FTX collapsed in 2022, according to CryptoQuant", {
            "es": "Tarjeta: la capitalización de USDT de Tether cayó 6.600 millones de dólares en 60 días hasta el 7 de noviembre, más del doble que la caída de 3.200 millones tras el colapso de FTX en 2022, según CryptoQuant",
            "pt": "Cartão: o valor de mercado do USDT da Tether caiu US$ 6,6 bilhões em 60 dias até 7 de novembro, mais que o dobro da queda de US$ 3,2 bilhões após o colapso da FTX em 2022, segundo a CryptoQuant",
            "fr": "Encadré : la capitalisation de l'USDT de Tether a reculé de 6,6 milliards de dollars en 60 jours jusqu'au 7 novembre, plus du double de la baisse de 3,2 milliards après la faillite de FTX en 2022, selon CryptoQuant",
            "de": "Faktenkarte: Die Marktkapitalisierung von Tethers USDT sank in 60 Tagen bis zum 7. November um 6,6 Mrd. $, mehr als doppelt so stark wie der Rückgang um 3,2 Mrd. $ nach dem FTX-Zusammenbruch 2022, so CryptoQuant",
            "ru": "Карточка: по данным CryptoQuant, капитализация USDT от Tether за 60 дней до 7 ноября снизилась на $6,6 млрд — более чем вдвое сильнее, чем падение на $3,2 млрд после краха FTX в 2022 году",
            "tr": "Kart: CryptoQuant'a göre Tether'in USDT piyasa değeri 7 Kasım'a kadarki 60 günde 6,6 milyar $ düştü; bu, 2022'de FTX'in çöküşünün ardından görülen 3,2 milyar $'lık düşüşün iki katından fazla",
            "id": "Kart fakta: kapitalisasi pasar USDT Tether turun US$6,6 miliar dalam 60 hari hingga 7 November, lebih dari dua kali lipat penurunan US$3,2 miliar setelah FTX runtuh pada 2022, menurut CryptoQuant",
            "ja": "カード：CryptoQuantによると、テザーのUSDT時価総額は11月7日までの60日間で66億ドル減少。2022年のFTX破綻後の32億ドル減の2倍を超える",
            "ko": "카드: 크립토퀀트에 따르면 테더 USDT 시가총액은 11월 7일까지 60일간 66억 달러 감소해, 2022년 FTX 붕괴 이후 32억 달러 감소의 두 배를 넘었다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CryptoQuant, via The Block")},
    ]


TL_ALTS = {
    "es": "Cronología: 2 de nov., la CFTC da por aprobados los futuros perpetuos sobre acciones de Coinbase, Kalshi y Bitnomial; 3 de nov., un grupo respaldado por Cboe y Citadel demanda y se rechaza una suspensión de emergencia; 10 de nov., el tribunal acepta un escrito de la SEC que respalda a la CFTC; 31 de dic., plazo de la SEC para decidir sobre las reglas de las bolsas",
    "pt": "Linha do tempo: 2 de nov., futuros perpétuos de ações da Coinbase, Kalshi e Bitnomial são considerados aprovados pela CFTC; 3 de nov., um grupo apoiado por Cboe e Citadel processa e uma suspensão de emergência é negada; 10 de nov., o tribunal aceita um parecer da SEC a favor da CFTC; 31 de dez., prazo da SEC para decidir sobre as regras das bolsas",
    "fr": "Chronologie : 2 nov., les contrats perpétuels sur actions de Coinbase, Kalshi et Bitnomial sont réputés approuvés par la CFTC ; 3 nov., un groupe soutenu par Cboe et Citadel porte plainte et une suspension d'urgence est refusée ; 10 nov., le tribunal accepte un mémoire de la SEC favorable à la CFTC ; 31 déc., date limite de la SEC pour se prononcer sur les règles des plateformes",
    "de": "Zeitleiste: 2. Nov., Aktien-Perpetuals von Coinbase, Kalshi und Bitnomial gelten bei der CFTC als genehmigt; 3. Nov., eine von Cboe und Citadel unterstützte Gruppe klagt, ein Eilstopp wird abgelehnt; 10. Nov., das Gericht nimmt einen SEC-Schriftsatz zugunsten der CFTC an; 31. Dez., Frist der SEC für ihre Entscheidung über die Börsenregeln",
    "ru": "Хронология: 2 ноября бессрочные фьючерсы на акции от Coinbase, Kalshi и Bitnomial считаются одобренными CFTC; 3 ноября группа при поддержке Cboe и Citadel подаёт иск, экстренную остановку суд отклоняет; 10 ноября суд принимает записку SEC в поддержку CFTC; 31 декабря — срок, до которого SEC должна решить судьбу правил бирж",
    "tr": "Zaman çizelgesi: 2 Kasım'da Coinbase, Kalshi ve Bitnomial'ın hisse perpetual vadeli işlemleri CFTC tarafından onaylanmış sayılıyor; 3 Kasım'da Cboe ve Citadel destekli bir grup dava açıyor, acil durdurma talebi reddediliyor; 10 Kasım'da mahkeme CFTC'yi destekleyen SEC görüşünü kabul ediyor; 31 Aralık, SEC'in borsa kuralları hakkında karar vermesi için son tarih",
    "id": "Linimasa: 2 Nov, kontrak berjangka perpetual saham dari Coinbase, Kalshi, dan Bitnomial dianggap disetujui CFTC; 3 Nov, kelompok yang didukung Cboe dan Citadel menggugat dan permintaan penghentian darurat ditolak; 10 Nov, pengadilan menerima amicus brief SEC yang mendukung CFTC; 31 Des, batas waktu SEC untuk memutuskan aturan bursa",
    "ja": "時系列：11月2日、Coinbase、Kalshi、Bitnomialの個別株無期限先物がCFTCにより承認とみなされる。11月3日、CboeとCitadelが支援する団体が提訴し、緊急差し止めは却下。11月10日、裁判所がCFTCを支持するSECの意見書を受理。12月31日、取引所規則に関するSECの判断期限",
    "ko": "타임라인: 11월 2일 코인베이스·칼시·비트노미얼의 개별 주식 무기한 선물이 CFTC 승인으로 간주됨, 11월 3일 Cboe·시타델 지원 단체가 소송을 제기했으나 긴급 중단 요청은 기각, 11월 10일 법원이 CFTC를 지지하는 SEC 의견서 수리, 12월 31일 거래소 규칙에 대한 SEC 결정 시한",
}

FACT_ALTS = {
    "es": "Tarjeta: cada materia prima digital de un fondo debe promediar al menos 700 millones de dólares de valor de mercado diario durante 12 meses antes de que Nasdaq ISE pueda listar opciones sobre ese fondo",
    "pt": "Cartão: cada commodity digital de um fundo precisa ter valor de mercado diário médio de pelo menos US$ 700 milhões em 12 meses antes que a Nasdaq ISE possa listar opções sobre esse fundo",
    "fr": "Encadré : chaque matière première numérique d'un fonds doit afficher une valeur de marché quotidienne moyenne d'au moins 700 millions de dollars sur 12 mois avant que Nasdaq ISE puisse coter des options sur ce fonds",
    "de": "Faktenkarte: Jeder digitale Rohstoff in einem Fonds muss über 12 Monate im Schnitt mindestens 700 Mio. $ täglichen Marktwert haben, bevor Nasdaq ISE Optionen auf den Fonds listen darf",
    "ru": "Карточка: каждый цифровой товар в фонде должен иметь среднюю дневную рыночную стоимость не менее $700 млн за 12 месяцев, прежде чем Nasdaq ISE сможет листинговать опционы на этот фонд",
    "tr": "Kart: Nasdaq ISE'ın bir fon üzerinde opsiyon listeleyebilmesi için fondaki her dijital emtianın 12 ay boyunca ortalama günlük piyasa değeri en az 700 milyon $ olmalı",
    "id": "Kart fakta: setiap komoditas digital dalam sebuah dana harus memiliki rata-rata nilai pasar harian minimal US$700 juta selama 12 bulan sebelum Nasdaq ISE dapat mencatatkan opsi atas dana tersebut",
    "ja": "カード：Nasdaq ISEがファンドのオプションを上場するには、組み入れる各デジタル・コモディティの過去12カ月の1日平均時価が7億ドル以上である必要がある",
    "ko": "카드: 나스닥 ISE가 펀드 옵션을 상장하려면 펀드에 담긴 각 디지털 상품의 최근 12개월 일평균 시장가치가 7억 달러 이상이어야 한다",
}


def build_sec_perps_options():
    slug = "sec-backs-cftc-stock-perps-crypto-etf-options-nov-2026"
    d = OUT / slug
    tl = make_timeline_card(
        d / "timeline-stock-perps",
        "The stock perps fight",
        [
            ("Nov. 2", "Stock perps from Coinbase, Kalshi and Bitnomial deemed approved by the CFTC", (96, 165, 250)),
            ("Nov. 3", "Cboe- and Citadel-backed group sues; emergency halt denied", (248, 113, 113)),
            ("Nov. 10", "Court accepts SEC brief backing the CFTC", ORANGE),
            ("Dec. 31", "SEC deadline to decide on the exchanges' rules", (52, 211, 153)),
        ],
        footer="The Block · Ledger Insights · court docket · Nov 11, 2026",
        margin=160, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-ise-700m",
        label="New crypto ETF options test",
        big="$700 million",
        sub="Minimum 12-month average daily market value for each digital commodity in a trust before Nasdaq ISE can list its options",
        footer="SEC Release No. 34-106863 · Nov 10, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Nov. 2, stock perpetual futures from Coinbase, Kalshi and Bitnomial are deemed approved by the CFTC; Nov. 3, a Cboe- and Citadel-backed group sues and an emergency halt is denied; Nov. 10, the court accepts an SEC brief backing the CFTC; Dec. 31, the SEC's deadline to decide on the exchanges' rules", TL_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="The Block; Ledger Insights")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: each digital commodity in a trust must average at least $700 million in daily market value over 12 months before Nasdaq ISE can list options on the trust", FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="SEC Release No. 34-106863")},
    ]


def build_msci_strategy():
    slug = "msci-drops-strategy-bitcoin-falls-nvidia-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD daily closes, Aug 14 - Nov 11, 2026 (90 days): peak close $86,594 (Sep 21), $73,928 on Nov 11.
    # Nov 12 intraday low on Kraken: $72,178.1 (lowest since Aug 20).
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since=1786579200"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = next(v for k, v in data["result"].items() if k != "last")
    rows = [r for r in rows if 1786665600 <= int(r[0]) < 1794441600]
    xs = np.array([float(r[0]) for r in rows]); ys = np.array([float(r[4]) for r in rows])
    chart = make_line_chart(
        d / "chart-btc-daily-90d",
        xs, ys,
        title="Bitcoin daily closing price, Aug. 14 - Nov. 11, 2026 (Kraken)",
        hline=72178,
        hlabel="Nov. 12 intraday low ≈ $72,178 (Kraken)",
    )
    card = make_fact_card(
        d / "fact-msci-2-8b",
        label="Index exit",
        big="~$2.8 billion",
        sub="Selling of Strategy stock JPMorgan estimated MSCI's removal could trigger; up to $8.8 billion if other index providers follow",
        footer="JPMorgan estimate, via Reuters and Cointelegraph · Nov 11-12, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's daily closing price on Kraken from Aug. 14 to Nov. 11, 2026: it rises to a peak close of about $86,600 on Sep. 21, then falls to about $73,900 on Nov. 11, with a dashed line at the Nov. 12 intraday low of about $72,178", MSCI_CHART_ALTS),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD daily closes and Nov. 12 intraday low")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: JPMorgan estimated MSCI's removal of Strategy could trigger about $2.8 billion of selling of its stock, and up to $8.8 billion if other index providers follow", MSCI_FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="JPMorgan estimate, via Reuters and Cointelegraph")},
    ]


MSCI_CHART_ALTS = {
    "es": "Gráfico de líneas del precio de cierre diario de bitcoin en Kraken del 14 de agosto al 11 de noviembre de 2026: sube hasta un cierre máximo de unos 86.600 dólares el 21 de septiembre y cae a unos 73.900 dólares el 11 de noviembre, con una línea discontinua en el mínimo intradía del 12 de noviembre, de unos 72.178 dólares",
    "pt": "Gráfico de linha do preço de fechamento diário do bitcoin na Kraken de 14 de agosto a 11 de novembro de 2026: sobe até um fechamento máximo de cerca de US$ 86.600 em 21 de setembro e cai para cerca de US$ 73.900 em 11 de novembro, com uma linha tracejada na mínima intradiária de 12 de novembro, de cerca de US$ 72.178",
    "fr": "Courbe du cours de clôture quotidien du bitcoin sur Kraken du 14 août au 11 novembre 2026 : il grimpe jusqu'à une clôture record d'environ 86 600 dollars le 21 septembre, puis recule à environ 73 900 dollars le 11 novembre, avec une ligne pointillée au plus bas intrajournalier du 12 novembre, environ 72 178 dollars",
    "de": "Liniendiagramm des täglichen Bitcoin-Schlusskurses bei Kraken vom 14. August bis 11. November 2026: Anstieg auf einen Höchstschlusskurs von rund 86.600 $ am 21. September, danach Rückgang auf rund 73.900 $ am 11. November; gestrichelte Linie beim Tagestief vom 12. November von rund 72.178 $",
    "ru": "Линейный график дневных цен закрытия биткоина на Kraken с 14 августа по 11 ноября 2026 года: рост до максимального закрытия около $86 600 21 сентября, затем снижение примерно до $73 900 11 ноября; пунктирная линия — внутридневной минимум 12 ноября, около $72 178",
    "tr": "Bitcoin'in 14 Ağustos - 11 Kasım 2026 arasında Kraken'deki günlük kapanış fiyatının çizgi grafiği: 21 Eylül'de yaklaşık 86.600 $ ile en yüksek kapanışa çıkıyor, 11 Kasım'da yaklaşık 73.900 $'a geriliyor; kesikli çizgi 12 Kasım'daki yaklaşık 72.178 $'lık gün içi dibi gösteriyor",
    "id": "Grafik garis harga penutupan harian bitcoin di Kraken dari 14 Agustus hingga 11 November 2026: naik ke penutupan tertinggi sekitar US$86.600 pada 21 September, lalu turun ke sekitar US$73.900 pada 11 November, dengan garis putus-putus di level terendah intrahari 12 November sekitar US$72.178",
    "ja": "2026年8月14日〜11月11日のKrakenにおけるビットコイン日次終値の折れ線グラフ：9月21日に約8万6600ドルの最高終値を付けた後、11月11日には約7万3900ドルに下落。破線は11月12日の日中安値（約7万2178ドル）",
    "ko": "2026년 8월 14일~11월 11일 크라켄 비트코인 일일 종가 선 차트: 9월 21일 약 86,600달러로 최고 종가를 기록한 뒤 11월 11일 약 73,900달러로 하락, 점선은 11월 12일 장중 저점 약 72,178달러",
}
MSCI_FACT_ALTS = {
    "es": "Tarjeta: JPMorgan estimó que la salida de Strategy de los índices MSCI podría provocar ventas de sus acciones por unos 2.800 millones de dólares, y hasta 8.800 millones si otros proveedores de índices hacen lo mismo",
    "pt": "Cartão: o JPMorgan estimou que a saída da Strategy dos índices MSCI pode gerar vendas de cerca de US$ 2,8 bilhões em suas ações, e até US$ 8,8 bilhões se outros provedores de índices fizerem o mesmo",
    "fr": "Encadré : JPMorgan estimait que la sortie de Strategy des indices MSCI pourrait entraîner environ 2,8 milliards de dollars de ventes de ses actions, et jusqu'à 8,8 milliards si d'autres fournisseurs d'indices suivent",
    "de": "Faktenkarte: JPMorgan schätzte, dass die Streichung von Strategy aus den MSCI-Indizes Verkäufe der Aktie von rund 2,8 Mrd. $ auslösen könnte, bis zu 8,8 Mrd. $, falls andere Indexanbieter folgen",
    "ru": "Карточка: по оценке JPMorgan, исключение Strategy из индексов MSCI может вызвать продажи её акций примерно на $2,8 млрд, а если последуют другие провайдеры индексов — до $8,8 млрд",
    "tr": "Kart: JPMorgan, Strategy'nin MSCI endekslerinden çıkarılmasının hisselerinde yaklaşık 2,8 milyar $'lık satışa yol açabileceğini, diğer endeks sağlayıcıları da aynı adımı atarsa bunun 8,8 milyar $'a çıkabileceğini tahmin etmişti",
    "id": "Kart fakta: JPMorgan memperkirakan penghapusan Strategy dari indeks MSCI dapat memicu penjualan sahamnya sekitar US$2,8 miliar, dan hingga US$8,8 miliar jika penyedia indeks lain ikut melakukannya",
    "ja": "カード：JPMorganは、MSCI指数からのストラテジー除外で同社株に約28億ドルの売りが出る可能性があり、他の指数会社も追随すれば最大88億ドルになると試算していた",
    "ko": "카드: JP모건은 MSCI 지수 제외로 스트래티지 주식에 약 28억 달러의 매도가 나올 수 있으며, 다른 지수 회사들도 따를 경우 최대 88억 달러에 이를 수 있다고 추정했다",
}


def build_doj_binance_seizure():
    slug = "doj-seizes-1-2-billion-binance-hack-north-korea-nov-2026"
    d = OUT / slug
    # U.S. DOJ press release, Nov 12, 2026: "more than $6 billion" stolen from Binance on or about Oct 29;
    # "freeze of more than $2.7 billion"; court authorization to seize or restrain "in excess of $1.2 billion".
    chart = make_bar_chart(
        d / "chart-binance-hack-doj-seizure",
        ["Stolen from Binance", "Frozen so far", "Court-approved seizure\nor restraint"],
        [6.0, 2.7, 1.2],
        "Binance hack funds, per the U.S. Justice Department (Nov. 12, 2026)",
        colors=["#f87171", "#34d399", "#f7931a"],
        value_fmt=lambda v: f"more than ${v:g}B",
        axis_fmt=lambda x, _p: f"${x:g}B",
    )
    card = make_fact_card(
        d / "fact-facestealer-400m",
        label="FaceStealer",
        big="$400 million+",
        sub="Stolen by North Korean hackers in 18 months using fake Zoom and Teams calls, the FBI says. Agents seized 900+ recorded victim videos.",
        footer="FBI FLASH and U.S. DOJ · Nov. 12, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of Binance hack funds according to the U.S. Justice Department: more than $6 billion stolen, more than $2.7 billion frozen so far, and more than $1.2 billion covered by court approval to seize or restrain", DOJ_CHART_ALTS),
         "caption": {l: CAPTION_CHART[l].format(src=DOJ_CHART_SRC[l]) for l in LANGS}},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the FBI says North Korean hackers stole more than $400 million in 18 months with the FaceStealer fake video call scheme, and agents seized more than 900 recorded victim videos", DOJ_FACT_ALTS),
         "caption": {l: CAPTION_SOURCE[l].format(src=DOJ_FACT_SRC[l]) for l in LANGS}},
    ]


DOJ_CHART_ALTS = {
    "es": "Gráfico de barras de los fondos del hackeo de Binance según el Departamento de Justicia de EE. UU.: más de 6.000 millones de dólares robados, más de 2.700 millones congelados hasta ahora y más de 1.200 millones cubiertos por la autorización judicial de incautación o inmovilización",
    "pt": "Gráfico de barras dos fundos do hack da Binance segundo o Departamento de Justiça dos EUA: mais de US$ 6 bilhões roubados, mais de US$ 2,7 bilhões congelados até agora e mais de US$ 1,2 bilhão cobertos pela autorização judicial de apreensão ou bloqueio",
    "fr": "Graphique en barres des fonds du piratage de Binance selon le ministère américain de la Justice : plus de 6 milliards de dollars volés, plus de 2,7 milliards gelés à ce jour et plus de 1,2 milliard couverts par l'autorisation judiciaire de saisie ou de blocage",
    "de": "Balkendiagramm der Gelder aus dem Binance-Hack laut US-Justizministerium: mehr als 6 Mrd. $ gestohlen, mehr als 2,7 Mrd. $ bisher eingefroren und mehr als 1,2 Mrd. $ von der gerichtlichen Genehmigung zur Beschlagnahme oder Sperrung erfasst",
    "ru": "Столбчатая диаграмма средств со взлома Binance по данным Минюста США: украдено более $6 млрд, заморожено более $2,7 млрд, разрешение суда на изъятие или блокировку получено для более чем $1,2 млрд",
    "tr": "ABD Adalet Bakanlığı'na göre Binance saldırısındaki fonların çubuk grafiği: 6 milyar dolardan fazlası çalındı, şimdiye kadar 2,7 milyar dolardan fazlası donduruldu, 1,2 milyar dolardan fazlası için el koyma veya dondurma yönünde mahkeme izni alındı",
    "id": "Grafik batang dana peretasan Binance menurut Departemen Kehakiman AS: lebih dari US$6 miliar dicuri, lebih dari US$2,7 miliar dibekukan sejauh ini, dan lebih dari US$1,2 miliar tercakup izin pengadilan untuk disita atau dibekukan",
    "ja": "米司法省によるBinanceハッキング資金の棒グラフ：盗まれた額は60億ドル超、これまでに凍結されたのは27億ドル超、裁判所が押収・保全を認めたのは12億ドル超",
    "ko": "미국 법무부 기준 바이낸스 해킹 자금 막대 차트: 도난 60억 달러 이상, 지금까지 동결 27억 달러 이상, 법원이 압수 또는 동결을 승인한 금액 12억 달러 이상"
}
DOJ_CHART_SRC = {
    "en": "U.S. Department of Justice, Nov. 12, 2026",
    "es": "Departamento de Justicia de EE. UU., 12 de noviembre de 2026",
    "pt": "Departamento de Justiça dos EUA, 12 de novembro de 2026",
    "fr": "ministère américain de la Justice, 12 novembre 2026",
    "de": "US-Justizministerium, 12. November 2026",
    "ru": "Министерство юстиции США, 12 ноября 2026 г.",
    "tr": "ABD Adalet Bakanlığı, 12 Kasım 2026",
    "id": "Departemen Kehakiman AS, 12 November 2026",
    "ja": "米司法省（2026年11月12日）",
    "ko": "미국 법무부, 2026년 11월 12일"
}
DOJ_FACT_SRC = {
    "en": "FBI FLASH and U.S. Department of Justice",
    "es": "alerta FLASH del FBI y Departamento de Justicia de EE. UU.",
    "pt": "alerta FLASH do FBI e Departamento de Justiça dos EUA",
    "fr": "alerte FLASH du FBI et ministère américain de la Justice",
    "de": "FBI-FLASH-Warnung und US-Justizministerium",
    "ru": "предупреждение FBI FLASH и Министерство юстиции США",
    "tr": "FBI FLASH uyarısı ve ABD Adalet Bakanlığı",
    "id": "peringatan FLASH FBI dan Departemen Kehakiman AS",
    "ja": "FBIのFLASH警告、米司法省",
    "ko": "FBI FLASH 경보, 미국 법무부"
}
DOJ_FACT_ALTS = {
    "es": "Tarjeta: según el FBI, hackers norcoreanos robaron más de 400 millones de dólares en 18 meses con el esquema FaceStealer de videollamadas falsas, y los agentes se incautaron de más de 900 videos grabados de víctimas",
    "pt": "Cartão: segundo o FBI, hackers norte-coreanos roubaram mais de US$ 400 milhões em 18 meses com o esquema FaceStealer de videochamadas falsas, e os agentes apreenderam mais de 900 vídeos gravados de vítimas",
    "fr": "Encadré : selon le FBI, des pirates nord-coréens ont volé plus de 400 millions de dollars en 18 mois avec le stratagème FaceStealer de fausses visioconférences, et les agents ont saisi plus de 900 vidéos enregistrées de victimes",
    "de": "Faktenkarte: Laut FBI erbeuteten nordkoreanische Hacker mit der FaceStealer-Masche gefälschter Videocalls in 18 Monaten mehr als 400 Mio. $; die Ermittler beschlagnahmten mehr als 900 aufgezeichnete Opfervideos",
    "ru": "Карточка: по данным ФБР, северокорейские хакеры за 18 месяцев украли более $400 млн с помощью схемы FaceStealer с фальшивыми видеозвонками, а агенты изъяли более 900 записанных видео жертв",
    "tr": "Kart: FBI'a göre Kuzey Koreli hackerlar sahte görüntülü aramalara dayanan FaceStealer düzeniyle 18 ayda 400 milyon dolardan fazla çaldı; ekipler kurbanlara ait 900'den fazla kayıtlı videoya el koydu",
    "id": "Kartu fakta: menurut FBI, peretas Korea Utara mencuri lebih dari US$400 juta dalam 18 bulan lewat modus panggilan video palsu FaceStealer, dan petugas menyita lebih dari 900 video rekaman korban",
    "ja": "カード：FBIによると、北朝鮮のハッカーは偽ビデオ通話の手口FaceStealerで18か月間に4億ドル超を盗んだ。捜査当局は被害者を録画した動画900本超を押収した",
    "ko": "카드: FBI에 따르면 북한 해커들은 가짜 화상통화 수법 FaceStealer로 18개월 동안 4억 달러 이상을 훔쳤고, 수사 당국은 녹화된 피해자 영상 900개 이상을 압수했다"
}


def build_btc_below_70k():
    slug = "bitcoin-below-70000-200-week-average-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD daily closes, Aug 15 - Nov 12, 2026 (90 days): $63,024 on Aug 15, peak close $86,594 (Sep 21),
    # $71,371 on Nov 12. Nov 13 intraday low on Kraken: $67,500.0 (05:00 UTC hour), lowest since Aug 19.
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since=1786579200"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = next(v for k, v in data["result"].items() if k != "last")
    rows = [r for r in rows if 1786752000 <= int(r[0]) < 1794528000]
    xs = np.array([float(r[0]) for r in rows]); ys = np.array([float(r[4]) for r in rows])
    chart = make_line_chart(
        d / "chart-btc-daily-aug-nov",
        xs, ys,
        title="Bitcoin daily closing price, Aug. 15 - Nov. 12, 2026 (Kraken)",
        hline=67500,
        hlabel="Nov. 13 intraday low ≈ $67,500 (Kraken)",
    )
    card = make_fact_card(
        d / "fact-liquidations-1-64b",
        label="Liquidations",
        big="$1.64 billion",
        sub="Crypto futures liquidated in 24 hours to Nov. 13. Long bets made up 88.7%; bitcoin futures accounted for $916 million.",
        footer="CoinGlass data via CoinDesk · Nov. 13, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's daily closing price on Kraken from Aug. 15 to Nov. 12, 2026: it rises from about $63,000 to a peak close of about $86,600 on Sep. 21, then falls to about $71,400 on Nov. 12, with a dashed line at the Nov. 13 intraday low of about $67,500", BTC70_CHART_ALTS),
         "caption": {l: CAPTION_CHART[l].format(src=BTC70_CHART_SRC[l]) for l in LANGS}},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $1.64 billion in crypto futures were liquidated in the 24 hours to Nov. 13; long bets made up 88.7%, and bitcoin futures accounted for $916 million", BTC70_FACT_ALTS),
         "caption": {l: CAPTION_SOURCE[l].format(src=BTC70_FACT_SRC[l]) for l in LANGS}},
    ]


BTC70_CHART_SRC = {
    "en": "Kraken BTC/USD daily closes and Nov. 13 intraday low",
    "es": "cierres diarios BTC/USD de Kraken y mínimo intradía del 13 de noviembre",
    "pt": "fechamentos diários BTC/USD da Kraken e mínima intradiária de 13 de novembro",
    "fr": "clôtures quotidiennes BTC/USD de Kraken et plus bas intrajournalier du 13 novembre",
    "de": "BTC/USD-Tagesschlusskurse bei Kraken und Tagestief vom 13. November",
    "ru": "дневные закрытия BTC/USD на Kraken и внутридневной минимум 13 ноября",
    "tr": "Kraken BTC/USD günlük kapanışları ve 13 Kasım gün içi dibi",
    "id": "harga penutupan harian BTC/USD Kraken dan level terendah intrahari 13 November",
    "ja": "KrakenのBTC/USD日次終値と11月13日の日中安値",
    "ko": "크라켄 BTC/USD 일일 종가 및 11월 13일 장중 저점",
}
BTC70_FACT_SRC = {
    "en": "CoinGlass via CoinDesk",
    "es": "CoinGlass, citado por CoinDesk",
    "pt": "CoinGlass, citado pelo CoinDesk",
    "fr": "CoinGlass, cité par CoinDesk",
    "de": "CoinGlass, zitiert von CoinDesk",
    "ru": "CoinGlass, по данным CoinDesk",
    "tr": "CoinDesk'in aktardığı CoinGlass verileri",
    "id": "CoinGlass, dikutip CoinDesk",
    "ja": "CoinGlass（CoinDesk経由）",
    "ko": "CoinGlass(CoinDesk 인용)",
}
BTC70_CHART_ALTS = {
    "es": "Gráfico de líneas del precio de cierre diario de bitcoin en Kraken del 15 de agosto al 12 de noviembre de 2026: sube de unos 63.000 dólares a un cierre máximo de unos 86.600 dólares el 21 de septiembre y cae a unos 71.400 dólares el 12 de noviembre, con una línea discontinua en el mínimo intradía del 13 de noviembre, de unos 67.500 dólares",
    "pt": "Gráfico de linha do preço de fechamento diário do bitcoin na Kraken de 15 de agosto a 12 de novembro de 2026: sobe de cerca de US$ 63.000 para um fechamento máximo de cerca de US$ 86.600 em 21 de setembro e cai para cerca de US$ 71.400 em 12 de novembro, com uma linha tracejada na mínima intradiária de 13 de novembro, de cerca de US$ 67.500",
    "fr": "Courbe du cours de clôture quotidien du bitcoin sur Kraken du 15 août au 12 novembre 2026 : il passe d'environ 63 000 dollars à une clôture record d'environ 86 600 dollars le 21 septembre, puis recule à environ 71 400 dollars le 12 novembre, avec une ligne pointillée au plus bas intrajournalier du 13 novembre, environ 67 500 dollars",
    "de": "Liniendiagramm des täglichen Bitcoin-Schlusskurses bei Kraken vom 15. August bis 12. November 2026: Anstieg von rund 63.000 $ auf einen Höchstschlusskurs von rund 86.600 $ am 21. September, danach Rückgang auf rund 71.400 $ am 12. November; gestrichelte Linie beim Tagestief vom 13. November von rund 67.500 $",
    "ru": "Линейный график дневных цен закрытия биткоина на Kraken с 15 августа по 12 ноября 2026 года: рост примерно с $63 000 до максимального закрытия около $86 600 21 сентября, затем снижение примерно до $71 400 12 ноября; пунктирная линия показывает внутридневной минимум 13 ноября, около $67 500",
    "tr": "Bitcoin'in 15 Ağustos - 12 Kasım 2026 arasında Kraken'deki günlük kapanış fiyatının çizgi grafiği: yaklaşık 63.000 $'dan 21 Eylül'de yaklaşık 86.600 $ ile en yüksek kapanışa çıkıyor, 12 Kasım'da yaklaşık 71.400 $'a geriliyor; kesikli çizgi 13 Kasım'daki yaklaşık 67.500 $'lık gün içi dibi gösteriyor",
    "id": "Grafik garis harga penutupan harian bitcoin di Kraken dari 15 Agustus hingga 12 November 2026: naik dari sekitar US$63.000 ke penutupan tertinggi sekitar US$86.600 pada 21 September, lalu turun ke sekitar US$71.400 pada 12 November, dengan garis putus-putus di level terendah intrahari 13 November sekitar US$67.500",
    "ja": "2026年8月15日〜11月12日のKrakenにおけるビットコイン日次終値の折れ線グラフ：約6万3000ドルから9月21日の最高終値約8万6600ドルまで上昇し、11月12日には約7万1400ドルに下落。破線は11月13日の日中安値（約6万7500ドル）",
    "ko": "2026년 8월 15일~11월 12일 크라켄 비트코인 일일 종가 선 차트: 약 63,000달러에서 9월 21일 약 86,600달러로 최고 종가를 기록한 뒤 11월 12일 약 71,400달러로 하락, 점선은 11월 13일 장중 저점 약 67,500달러",
}
BTC70_FACT_ALTS = {
    "es": "Tarjeta: en las 24 horas hasta el 13 de noviembre se liquidaron unos 1.640 millones de dólares en futuros cripto; el 88,7% eran apuestas alcistas y los futuros de bitcoin sumaron 916 millones",
    "pt": "Cartão: nas 24 horas até 13 de novembro, cerca de US$ 1,64 bilhão em futuros cripto foram liquidados; 88,7% eram apostas de alta, e os futuros de bitcoin somaram US$ 916 milhões",
    "fr": "Encadré : environ 1,64 milliard de dollars de contrats à terme crypto ont été liquidés dans les 24 heures précédant le 13 novembre ; 88,7 % étaient des paris à la hausse, et les contrats sur le bitcoin représentaient 916 millions de dollars",
    "de": "Faktenkarte: In den 24 Stunden bis zum 13. November wurden rund 1,64 Mrd. $ an Krypto-Futures liquidiert; 88,7 % davon waren Long-Wetten, auf Bitcoin-Futures entfielen 916 Mio. $",
    "ru": "Карточка: за 24 часа до 13 ноября ликвидировано около $1,64 млрд в криптофьючерсах; 88,7% пришлось на длинные позиции, на фьючерсы на биткоин пришлось $916 млн",
    "tr": "Kart: 13 Kasım'a kadar 24 saatte yaklaşık 1,64 milyar $'lık kripto vadeli pozisyon tasfiye edildi; bunun %88,7'si yükseliş pozisyonuydu, bitcoin vadelileri 916 milyon $'ı oluşturdu",
    "id": "Kartu fakta: sekitar US$1,64 miliar kontrak berjangka kripto dilikuidasi dalam 24 jam hingga 13 November; 88,7% di antaranya posisi long, dan kontrak bitcoin mencapai US$916 juta",
    "ja": "カード：11月13日までの24時間で約16億4000万ドルの暗号資産先物が清算され、88.7%が買いポジション。ビットコイン先物は9億1600万ドル",
    "ko": "카드: 11월 13일까지 24시간 동안 약 16억 4,000만 달러 규모 암호화폐 선물이 청산됐고, 88.7%가 롱 포지션이었고 비트코인 선물이 9억 1,600만 달러를 차지",
}


def build_sec_cftc_nominees():
    slug = "trump-nominates-sec-cftc-commissioners-peirce-nov-2026"
    d = OUT / slug
    # Seats: SEC has 2 of 5 filled (Atkins, Uyeda), CFTC 1 of 5 (Selig), per CoinDesk / Cointelegraph, Nov 12-13, 2026.
    # White House nominations sent to the Senate, Nov 12, 2026: 2 SEC (Levine, Johnson), 2 CFTC (Anonick, Rowland).
    chart = make_bar_chart(
        d / "chart-sec-cftc-seats",
        ["SEC today", "SEC if all\nconfirmed", "CFTC today", "CFTC if all\nconfirmed"],
        [2, 4, 1, 3],
        "Commissioner seats filled (of 5) at the SEC and CFTC",
        colors=["#60a5fa", "#f7931a", "#60a5fa", "#f7931a"],
        value_fmt=lambda v: f"{v:g} of 5",
        axis_fmt=lambda x, _p: f"{x:g}",
    )
    card = make_fact_card(
        d / "fact-four-nominees",
        label="Nominees",
        big="4 nominees",
        sub="SEC: Steven Levine (R), Kristin Johnson (D). CFTC: Nathan Anonick (R), Matthew Rowland (D). All need Senate confirmation.",
        footer="The White House; Reuters · Nov. 12, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of commissioner seats filled out of five: the SEC has 2 today and would have 4 if both nominees are confirmed; the CFTC has 1 today and would have 3", SECNOM_CHART_ALTS),
         "caption": {l: CAPTION_CHART[l].format(src=SECNOM_CHART_SRC[l]) for l in LANGS}},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: four nominees. SEC: Steven Levine, Republican, and Kristin Johnson, Democrat. CFTC: Nathan Anonick, Republican, and Matthew Rowland, Democrat. All need Senate confirmation", SECNOM_FACT_ALTS),
         "caption": {l: CAPTION_SOURCE[l].format(src=SECNOM_FACT_SRC[l]) for l in LANGS}},
    ]


SECNOM_CHART_SRC = {
    "en": "The White House, CoinDesk, Cointelegraph",
    "es": "Casa Blanca, CoinDesk, Cointelegraph",
    "pt": "Casa Branca, CoinDesk, Cointelegraph",
    "fr": "Maison Blanche, CoinDesk, Cointelegraph",
    "de": "Weißes Haus, CoinDesk, Cointelegraph",
    "ru": "Белый дом, CoinDesk, Cointelegraph",
    "tr": "Beyaz Saray, CoinDesk, Cointelegraph",
    "id": "Gedung Putih, CoinDesk, Cointelegraph",
    "ja": "ホワイトハウス、CoinDesk、Cointelegraph",
    "ko": "백악관, CoinDesk, Cointelegraph",
}
SECNOM_FACT_SRC = {
    "en": "The White House; Reuters",
    "es": "Casa Blanca; Reuters",
    "pt": "Casa Branca; Reuters",
    "fr": "Maison Blanche ; Reuters",
    "de": "Weißes Haus; Reuters",
    "ru": "Белый дом; Reuters",
    "tr": "Beyaz Saray; Reuters",
    "id": "Gedung Putih; Reuters",
    "ja": "ホワイトハウス、ロイター",
    "ko": "백악관, 로이터",
}
SECNOM_CHART_ALTS = {
    "es": "Gráfico de barras de los puestos de comisionado ocupados de un total de cinco: la SEC tiene 2 hoy y tendría 4 si se confirman sus dos candidatos; la CFTC tiene 1 hoy y tendría 3",
    "pt": "Gráfico de barras dos assentos de comissário ocupados de um total de cinco: a SEC tem 2 hoje e teria 4 se os dois indicados forem confirmados; a CFTC tem 1 hoje e teria 3",
    "fr": "Graphique en barres des sièges de commissaire pourvus sur cinq : la SEC en compte 2 aujourd'hui et en aurait 4 si ses deux candidats sont confirmés ; la CFTC en compte 1 et en aurait 3",
    "de": "Balkendiagramm der besetzten Kommissarsposten von fünf: Die SEC hat heute 2 und hätte 4, wenn beide Kandidaten bestätigt werden; die CFTC hat heute 1 und hätte 3",
    "ru": "Столбчатая диаграмма занятых мест комиссаров из пяти: в SEC сейчас 2, а после утверждения обоих кандидатов будет 4; в CFTC сейчас 1, будет 3",
    "tr": "Beş komisyon üyeliğinden dolu olanların çubuk grafiği: SEC'te bugün 2 üye var, iki aday da onaylanırsa 4 olacak; CFTC'de bugün 1 üye var, 3 olacak",
    "id": "Grafik batang kursi komisioner yang terisi dari lima: SEC kini punya 2 dan akan menjadi 4 jika kedua calon dikonfirmasi; CFTC kini punya 1 dan akan menjadi 3",
    "ja": "定員5人のうち埋まっている委員ポストの棒グラフ：SECは現在2人で、2人の候補が承認されれば4人に。CFTCは現在1人で、承認されれば3人に",
    "ko": "정원 5명 중 채워진 위원 자리 막대 차트: SEC는 현재 2명이며 두 후보가 인준되면 4명, CFTC는 현재 1명이며 인준되면 3명",
}
SECNOM_FACT_ALTS = {
    "es": "Tarjeta: cuatro candidatos. SEC: Steven Levine, republicano, y Kristin Johnson, demócrata. CFTC: Nathan Anonick, republicano, y Matthew Rowland, demócrata. Todos necesitan la confirmación del Senado",
    "pt": "Cartão: quatro indicados. SEC: Steven Levine, republicano, e Kristin Johnson, democrata. CFTC: Nathan Anonick, republicano, e Matthew Rowland, democrata. Todos precisam de confirmação do Senado",
    "fr": "Encadré : quatre candidats. SEC : Steven Levine, républicain, et Kristin Johnson, démocrate. CFTC : Nathan Anonick, républicain, et Matthew Rowland, démocrate. Tous doivent être confirmés par le Sénat",
    "de": "Faktenkarte: vier Kandidaten. SEC: Steven Levine, Republikaner, und Kristin Johnson, Demokratin. CFTC: Nathan Anonick, Republikaner, und Matthew Rowland, Demokrat. Alle brauchen die Bestätigung des Senats",
    "ru": "Карточка: четыре кандидата. SEC: республиканец Стивен Левин и демократ Кристин Джонсон. CFTC: республиканец Натан Аноник и демократ Мэтью Роуленд. Всех должен утвердить Сенат",
    "tr": "Kart: dört aday. SEC: Cumhuriyetçi Steven Levine ve Demokrat Kristin Johnson. CFTC: Cumhuriyetçi Nathan Anonick ve Demokrat Matthew Rowland. Hepsinin Senato onayı alması gerekiyor",
    "id": "Kartu fakta: empat calon. SEC: Steven Levine (Republik) dan Kristin Johnson (Demokrat). CFTC: Nathan Anonick (Republik) dan Matthew Rowland (Demokrat). Semuanya perlu konfirmasi Senat",
    "ja": "カード：候補は4人。SECは共和党のスティーブン・レバイン氏と民主党のクリスティン・ジョンソン氏、CFTCは共和党のネイサン・アノニック氏と民主党のマシュー・ローランド氏。全員に上院の承認が必要",
    "ko": "카드: 후보 4명. SEC는 공화당 스티븐 레바인과 민주당 크리스틴 존슨, CFTC는 공화당 네이선 아노닉과 민주당 매슈 롤런드. 모두 상원 인준이 필요하다",
}


def build_illinois_tax():
    slug = "illinois-crypto-tax-doj-defi-challenge-nov-2026"
    d = OUT / slug
    # Cointelegraph (Nov 12, 2026), Decrypt (Nov 12, 2026), Blockchain Association release (Nov 4, 2026).
    tl = make_timeline_card(
        d / "timeline-illinois-tax-challenge",
        "The fight over Illinois' crypto tax",
        [
            ("July", "Digital Chamber sues Illinois officials", (96, 165, 250)),
            ("Aug.", "Blockchain Association and CCI file a second challenge", (96, 165, 250)),
            ("Oct.", "Illinois agrees to pause the tax until July 1, 2027", (52, 211, 153)),
            ("Nov. 6", "DOJ, U.S. Chamber and SIFMA back the challenge", ORANGE),
            ("Nov. 11", "DeFi coalition led by a16z, Paradigm, Uniswap files a brief", ORANGE),
        ],
        footer="Cointelegraph; Decrypt; Blockchain Association · Nov. 2026",
        margin=130, wrap_w=200,
    )
    card = make_fact_card(
        d / "fact-illinois-holders",
        label="Who it could reach",
        big="2.64 million",
        sub="Illinois residents estimated to hold digital assets, the fifth-highest total of any state, per the DeFi coalition's brief. The tax: 0.2% of an asset's full value.",
        footer="DeFi coalition brief, via Decrypt · Nov. 11, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: in July the Digital Chamber sued Illinois officials; in August the Blockchain Association and Crypto Council for Innovation filed a second challenge; in October Illinois agreed to pause the tax until July 1, 2027; on Nov. 6 the DOJ, U.S. Chamber of Commerce and SIFMA backed the challenge; on Nov. 11 a DeFi coalition led by a16z, Paradigm and Uniswap filed a brief", {
            "es": "Cronología: en julio la Digital Chamber demandó a funcionarios de Illinois; en agosto la Blockchain Association y el Crypto Council for Innovation presentaron una segunda impugnación; en octubre Illinois aceptó suspender el impuesto hasta el 1 de julio de 2027; el 6 de noviembre el DOJ, la Cámara de Comercio de EE. UU. y SIFMA respaldaron la demanda; el 11 de noviembre una coalición DeFi liderada por a16z, Paradigm y Uniswap presentó un escrito",
            "pt": "Linha do tempo: em julho a Digital Chamber processou autoridades de Illinois; em agosto a Blockchain Association e o Crypto Council for Innovation abriram uma segunda ação; em outubro Illinois aceitou suspender o imposto até 1º de julho de 2027; em 6 de novembro o DOJ, a Câmara de Comércio dos EUA e a SIFMA apoiaram a ação; em 11 de novembro uma coalizão DeFi liderada por a16z, Paradigm e Uniswap apresentou um parecer",
            "fr": "Chronologie : en juillet, la Digital Chamber attaque des responsables de l'Illinois ; en août, la Blockchain Association et le Crypto Council for Innovation déposent un second recours ; en octobre, l'Illinois accepte de suspendre la taxe jusqu'au 1er juillet 2027 ; le 6 novembre, le DOJ, la Chambre de commerce américaine et la SIFMA soutiennent le recours ; le 11 novembre, une coalition DeFi menée par a16z, Paradigm et Uniswap dépose un mémoire",
            "de": "Zeitleiste: Im Juli verklagt die Digital Chamber Beamte in Illinois; im August reichen Blockchain Association und Crypto Council for Innovation eine zweite Klage ein; im Oktober setzt Illinois die Steuer bis zum 1. Juli 2027 aus; am 6. November unterstützen DOJ, US-Handelskammer und SIFMA die Klage; am 11. November reicht eine DeFi-Koalition unter Führung von a16z, Paradigm und Uniswap einen Schriftsatz ein",
            "ru": "Хронология: в июле Digital Chamber подала иск против чиновников Иллинойса; в августе Blockchain Association и Crypto Council for Innovation подали второй иск; в октябре Иллинойс согласился приостановить налог до 1 июля 2027 года; 6 ноября Минюст США, Торговая палата США и SIFMA поддержали иск; 11 ноября DeFi-коалиция во главе с a16z, Paradigm и Uniswap подала свою записку",
            "tr": "Zaman çizelgesi: Temmuz'da Digital Chamber Illinois yetkililerine dava açtı; Ağustos'ta Blockchain Association ve Crypto Council for Innovation ikinci bir dava açtı; Ekim'de Illinois vergiyi 1 Temmuz 2027'ye kadar askıya almayı kabul etti; 6 Kasım'da ABD Adalet Bakanlığı, ABD Ticaret Odası ve SIFMA davayı destekledi; 11 Kasım'da a16z, Paradigm ve Uniswap liderliğindeki bir DeFi koalisyonu görüş sundu",
            "id": "Linimasa: Juli, Digital Chamber menggugat pejabat Illinois; Agustus, Blockchain Association dan Crypto Council for Innovation mengajukan gugatan kedua; Oktober, Illinois setuju menunda pajak hingga 1 Juli 2027; 6 November, DOJ, Kamar Dagang AS, dan SIFMA mendukung gugatan; 11 November, koalisi DeFi yang dipimpin a16z, Paradigm, dan Uniswap mengajukan berkas",
            "ja": "時系列：7月、Digital Chamberがイリノイ州当局を提訴。8月、Blockchain AssociationとCrypto Council for Innovationが2件目の訴訟。10月、州が2027年7月1日まで課税停止に同意。11月6日、米司法省、米商工会議所、SIFMAが訴訟を支持。11月11日、a16z、Paradigm、Uniswapが主導するDeFi連合が意見書を提出",
            "ko": "타임라인: 7월 디지털 챔버가 일리노이주 당국자를 제소, 8월 블록체인 협회와 크립토 카운슬 포 이노베이션이 두 번째 소송 제기, 10월 일리노이주가 2027년 7월 1일까지 세금 유예에 동의, 11월 6일 미 법무부·미 상공회의소·SIFMA가 소송 지지, 11월 11일 a16z·패러다임·유니스왑이 이끄는 디파이 연합이 의견서 제출",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Cointelegraph; Decrypt; Blockchain Association")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: an estimated 2.64 million Illinois residents hold digital assets, the fifth-highest total of any state, according to the DeFi coalition's brief; the tax is 0.2% of an asset's full value", {
            "es": "Tarjeta: se estima que 2,64 millones de residentes de Illinois tienen activos digitales, la quinta cifra más alta de cualquier estado, según el escrito de la coalición DeFi; el impuesto es del 0,2% del valor total del activo",
            "pt": "Cartão: estima-se que 2,64 milhões de moradores de Illinois tenham ativos digitais, o quinto maior total entre os estados, segundo o parecer da coalizão DeFi; o imposto é de 0,2% do valor total do ativo",
            "fr": "Encadré : environ 2,64 millions d'habitants de l'Illinois détiendraient des actifs numériques, le cinquième total le plus élevé des États, selon le mémoire de la coalition DeFi ; la taxe est de 0,2 % de la valeur totale de l'actif",
            "de": "Faktenkarte: Schätzungsweise 2,64 Millionen Einwohner von Illinois besitzen digitale Vermögenswerte, die fünfthöchste Zahl aller Bundesstaaten, so der Schriftsatz der DeFi-Koalition; die Steuer beträgt 0,2 % des vollen Werts",
            "ru": "Карточка: по оценке из записки DeFi-коалиции, цифровыми активами владеют около 2,64 млн жителей Иллинойса, это пятый показатель среди штатов; налог составляет 0,2% от полной стоимости актива",
            "tr": "Kart: DeFi koalisyonunun görüşüne göre tahminen 2,64 milyon Illinois sakini dijital varlık tutuyor, bu eyaletler arasında beşinci en yüksek sayı; vergi, varlığın tam değerinin %0,2'si",
            "id": "Kartu fakta: diperkirakan 2,64 juta penduduk Illinois memegang aset digital, tertinggi kelima di antara negara bagian, menurut berkas koalisi DeFi; pajaknya 0,2% dari nilai penuh aset",
            "ja": "カード：DeFi連合の意見書によると、デジタル資産を保有するイリノイ州民は推定264万人で全米5位。税率は資産の全額の0.2%",
            "ko": "카드: 디파이 연합 의견서에 따르면 디지털 자산을 보유한 일리노이 주민은 약 264만 명으로 주별 5위이며, 세금은 자산 전체 가치의 0.2%",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="DeFi coalition brief, via Decrypt")},
    ]


def build_dtcc_solana():
    slug = "dtcc-tokenized-stocks-solana-2027-nov-2026"
    d = OUT / slug
    # CoinDesk (Nov 12, 2026): DTC holds $114 trillion in securities; DTS debuted with 34 eligible securities worth ~$30 trillion.
    chart = make_bar_chart(
        d / "chart-dtc-custody-vs-eligible",
        ["Securities held at DTC", "Eligible for tokenization\n(34 securities)"],
        [114, 30],
        "DTCC's scale: custody vs. assets eligible for its tokenization service",
        colors=["#60a5fa", "#f7931a"],
        value_fmt=lambda v: f"${v:g} trillion" if v != 30 else "about $30 trillion",
        axis_fmt=lambda x, _p: f"${x:g}T",
    )
    # DTCC press release (Nov 12, 2026); The Block; CoinDesk.
    tl = make_timeline_card(
        d / "timeline-dtcc-tokenization",
        "DTCC's road to Solana",
        [
            ("July", "First limited tokenized trades on Canton and Besu", (96, 165, 250)),
            ("Oct. 28", "DTCC Tokenization Service launches", (52, 211, 153)),
            ("Nov. 12", "DTCC announces plans to connect to Solana", ORANGE),
            ("H2 2027", "DTC-tokenized assets expected on Solana", ORANGE),
        ],
        footer="DTCC press release; The Block; CoinDesk · Nov. 12, 2026",
        margin=170, wrap_w=240,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart: DTC holds $114 trillion in securities, while the 34 securities eligible for DTCC's tokenization service represent about $30 trillion", {
            "es": "Gráfico de barras: DTC custodia 114 billones de dólares en valores, mientras que los 34 valores elegibles para el servicio de tokenización de DTCC suman unos 30 billones",
            "pt": "Gráfico de barras: a DTC guarda US$ 114 trilhões em valores mobiliários, enquanto os 34 títulos elegíveis ao serviço de tokenização da DTCC somam cerca de US$ 30 trilhões",
            "fr": "Graphique en barres : la DTC conserve 114 000 milliards de dollars de titres, tandis que les 34 titres éligibles au service de tokenisation de la DTCC représentent environ 30 000 milliards",
            "de": "Balkendiagramm: Die DTC verwahrt Wertpapiere im Wert von 114 Billionen $, die 34 für den Tokenisierungsdienst der DTCC zugelassenen Wertpapiere stehen für rund 30 Billionen $",
            "ru": "Столбчатая диаграмма: DTC хранит ценные бумаги на $114 трлн, а 34 бумаги, допущенные к токенизации в сервисе DTCC, стоят около $30 трлн",
            "tr": "Çubuk grafik: DTC 114 trilyon dolarlık menkul kıymet saklıyor; DTCC'nin tokenizasyon hizmetine uygun 34 menkul kıymet ise yaklaşık 30 trilyon dolar değerinde",
            "id": "Grafik batang: DTC menyimpan efek senilai US$114 triliun, sedangkan 34 efek yang memenuhi syarat untuk layanan tokenisasi DTCC bernilai sekitar US$30 triliun",
            "ja": "棒グラフ：DTCが保管する証券は114兆ドル、DTCCのトークン化サービスの対象となる34銘柄は約30兆ドル",
            "ko": "막대 차트: DTC가 보관하는 증권은 114조 달러, DTCC 토큰화 서비스 대상 34개 종목은 약 30조 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinDesk, DTCC")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: in July, first limited tokenized trades on Canton and Besu; on Oct. 28, the DTCC Tokenization Service launched; on Nov. 12, DTCC announced plans to connect to Solana; in the second half of 2027, DTC-tokenized assets are expected on Solana", {
            "es": "Cronología: en julio, primeras operaciones tokenizadas limitadas en Canton y Besu; el 28 de octubre se lanzó el servicio de tokenización de DTCC; el 12 de noviembre DTCC anunció su conexión con Solana; en el segundo semestre de 2027 se esperan activos tokenizados de DTC en Solana",
            "pt": "Linha do tempo: em julho, primeiras operações tokenizadas limitadas na Canton e na Besu; em 28 de outubro, lançamento do serviço de tokenização da DTCC; em 12 de novembro, a DTCC anunciou a conexão com a Solana; no segundo semestre de 2027, ativos tokenizados da DTC devem chegar à Solana",
            "fr": "Chronologie : en juillet, premières transactions tokenisées limitées sur Canton et Besu ; le 28 octobre, lancement du service de tokenisation de la DTCC ; le 12 novembre, la DTCC annonce sa connexion à Solana ; au second semestre 2027, des actifs tokenisés de la DTC sont attendus sur Solana",
            "de": "Zeitleiste: Im Juli erste begrenzte tokenisierte Geschäfte auf Canton und Besu; am 28. Oktober Start des DTCC-Tokenisierungsdienstes; am 12. November kündigt die DTCC die Anbindung an Solana an; in der zweiten Jahreshälfte 2027 sollen DTC-tokenisierte Werte auf Solana verfügbar sein",
            "ru": "Хронология: в июле первые ограниченные сделки с токенизированными бумагами в Canton и Besu; 28 октября запущен сервис токенизации DTCC; 12 ноября DTCC объявила о подключении к Solana; во второй половине 2027 года токенизированные активы DTC должны появиться в Solana",
            "tr": "Zaman çizelgesi: Temmuz'da Canton ve Besu'da ilk sınırlı tokenize işlemler; 28 Ekim'de DTCC Tokenizasyon Hizmeti başladı; 12 Kasım'da DTCC Solana bağlantısını duyurdu; 2027'nin ikinci yarısında DTC tokenize varlıklarının Solana'da olması bekleniyor",
            "id": "Linimasa: Juli, transaksi tokenisasi terbatas pertama di Canton dan Besu; 28 Oktober, Layanan Tokenisasi DTCC diluncurkan; 12 November, DTCC mengumumkan rencana terhubung ke Solana; paruh kedua 2027, aset tokenisasi DTC diharapkan hadir di Solana",
            "ja": "時系列：7月、CantonとBesuで初の限定的なトークン化取引。10月28日、DTCCトークン化サービス開始。11月12日、DTCCがSolanaへの接続計画を発表。2027年後半、DTCのトークン化資産がSolanaで利用可能になる見通し",
            "ko": "타임라인: 7월 캔턴과 베수에서 첫 제한적 토큰화 거래, 10월 28일 DTCC 토큰화 서비스 출시, 11월 12일 DTCC가 솔라나 연결 계획 발표, 2027년 하반기 DTC 토큰화 자산이 솔라나에 나올 예정",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="DTCC press release; The Block; CoinDesk")},
    ]


def build_payward_q3():
    slug = "kraken-payward-q3-2026-results-nov-2026"
    d = OUT / slug
    # The Block (Nov 13, 2026): adjusted EBITDA $178.6M in Q3 2025, $23M in Q2 2026, $60M in Q3 2026 (Payward highlights).
    chart = make_bar_chart(
        d / "chart-payward-adjusted-ebitda",
        ["Q3 2025", "Q2 2026", "Q3 2026"],
        [178.6, 23, 60],
        "Payward (Kraken) adjusted EBITDA by quarter, $ millions",
        colors=["#60a5fa", "#94a3b8", "#f7931a"],
        value_fmt=lambda v: f"${v:g}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    # Payward Q3 2026 financial highlights (Nov 13, 2026).
    card = make_fact_card(
        d / "fact-payward-funded-accounts",
        label="Kraken parent Payward, Q3 2026",
        big="7.1 million",
        sub="Funded accounts at the end of September, up 37% from a year earlier. Trading volume: $353 billion, down 30% from a year earlier.",
        footer="Payward Q3 2026 financial highlights · Nov. 13, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of Payward's adjusted EBITDA: $178.6 million in Q3 2025, $23 million in Q2 2026 and $60 million in Q3 2026", {
            "es": "Gráfico de barras del EBITDA ajustado de Payward: 178,6 millones de dólares en el tercer trimestre de 2025, 23 millones en el segundo trimestre de 2026 y 60 millones en el tercer trimestre de 2026",
            "pt": "Gráfico de barras do EBITDA ajustado da Payward: US$ 178,6 milhões no 3º trimestre de 2025, US$ 23 milhões no 2º trimestre de 2026 e US$ 60 milhões no 3º trimestre de 2026",
            "fr": "Graphique en barres de l'EBITDA ajusté de Payward : 178,6 millions de dollars au 3e trimestre 2025, 23 millions au 2e trimestre 2026 et 60 millions au 3e trimestre 2026",
            "de": "Balkendiagramm des bereinigten EBITDA von Payward: 178,6 Mio. $ im 3. Quartal 2025, 23 Mio. $ im 2. Quartal 2026 und 60 Mio. $ im 3. Quartal 2026",
            "ru": "Столбчатая диаграмма скорректированной EBITDA Payward: $178,6 млн в третьем квартале 2025 года, $23 млн во втором квартале 2026 года и $60 млн в третьем квартале 2026 года",
            "tr": "Payward'ın düzeltilmiş FAVÖK'ünün çubuk grafiği: 2025'in 3. çeyreğinde 178,6 milyon $, 2026'nın 2. çeyreğinde 23 milyon $ ve 2026'nın 3. çeyreğinde 60 milyon $",
            "id": "Grafik batang EBITDA yang disesuaikan Payward: US$178,6 juta pada kuartal III 2025, US$23 juta pada kuartal II 2026, dan US$60 juta pada kuartal III 2026",
            "ja": "Paywardの調整後EBITDAの棒グラフ：2025年第3四半期は1億7860万ドル、2026年第2四半期は2300万ドル、2026年第3四半期は6000万ドル",
            "ko": "페이워드 조정 EBITDA 막대 차트: 2025년 3분기 1억 7,860만 달러, 2026년 2분기 2,300만 달러, 2026년 3분기 6,000만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Payward, The Block")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Kraken parent Payward had 7.1 million funded accounts at the end of September 2026, up 37% from a year earlier; trading volume was $353 billion, down 30% from a year earlier", {
            "es": "Tarjeta: Payward, matriz de Kraken, tenía 7,1 millones de cuentas con fondos a finales de septiembre de 2026, un 37% más que un año antes; el volumen negociado fue de 353.000 millones de dólares, un 30% menos que un año antes",
            "pt": "Cartão: a Payward, controladora da Kraken, tinha 7,1 milhões de contas com saldo no fim de setembro de 2026, 37% a mais que um ano antes; o volume negociado foi de US$ 353 bilhões, 30% menor que um ano antes",
            "fr": "Encadré : Payward, maison mère de Kraken, comptait 7,1 millions de comptes approvisionnés fin septembre 2026, soit 37 % de plus qu'un an plus tôt ; le volume de transactions a atteint 353 milliards de dollars, en baisse de 30 % sur un an",
            "de": "Faktenkarte: Die Kraken-Mutter Payward hatte Ende September 2026 7,1 Millionen Konten mit Guthaben, 37 % mehr als ein Jahr zuvor; das Handelsvolumen lag bei 353 Mrd. $, 30 % weniger als ein Jahr zuvor",
            "ru": "Карточка: у Payward, материнской компании Kraken, на конец сентября 2026 года было 7,1 млн пополненных счетов, на 37% больше, чем годом ранее; объем операций составил $353 млрд, на 30% меньше, чем годом ранее",
            "tr": "Kart: Kraken'in ana şirketi Payward'ın Eylül 2026 sonunda 7,1 milyon bakiyeli hesabı vardı, bir yıl öncesine göre %37 fazla; işlem hacmi 353 milyar $ ile bir yıl öncesine göre %30 düştü",
            "id": "Kartu fakta: Payward, induk Kraken, memiliki 7,1 juta akun berdana pada akhir September 2026, naik 37% dari setahun sebelumnya; volume transaksi US$353 miliar, turun 30% dari setahun sebelumnya",
            "ja": "カード：Kraken親会社Paywardの残高のある口座数は2026年9月末で710万件、前年比37%増。取引高は3530億ドルで前年比30%減",
            "ko": "카드: 크라켄 모회사 페이워드의 잔고 보유 계좌는 2026년 9월 말 710만 개로 1년 전보다 37% 증가, 거래량은 3,530억 달러로 1년 전보다 30% 감소",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Payward Q3 2026 financial highlights")},
    ]


def build_treasury_loans():
    slug = "crypto-treasury-firms-loans-nakamoto-btcs-nov-2026"
    d = OUT / slug
    # CoinDesk (Nov 13, 2026): Nakamoto owes Kraken 165M USDT; pledged 3,030 BTC worth ~$208M at <$69K;
    # market value ~$104M at Thursday close ($5.79/share).
    chart = make_bar_chart(
        d / "chart-nakamoto-loan-vs-collateral",
        ["Owed to Kraken\n(165M USDT)", "Pledged bitcoin\n(3,030 BTC, approx.)", "Nakamoto stock\nmarket value (approx.)"],
        [165, 208, 104],
        "Nakamoto: loan vs. pledged bitcoin vs. company value, $ millions",
        colors=["#f87171", "#f7931a", "#60a5fa"],
        value_fmt=lambda v: f"${v:g}M" if v == 165 else f"about ${v:g}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    # CoinDesk (Nov 13, 2026) calculation from BTCS's Nov. 9 figures.
    card = make_fact_card(
        d / "fact-btcs-aave-liquidation-line",
        label="BTCS Aave loan",
        big="About $1,717",
        sub="Ether price near which BTCS's $64.1 million Aave loan could face liquidation, per CoinDesk's math from Nov. 9 data (46,676 ETH as collateral).",
        footer="BTCS filing via CoinDesk · Nov. 13, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart: Nakamoto owes Kraken 165 million USDT, its 3,030 pledged bitcoin are worth about $208 million, and its stock market value is about $104 million", {
            "es": "Gráfico de barras: Nakamoto debe a Kraken 165 millones de USDT, sus 3.030 bitcoins pignorados valen unos 208 millones de dólares y su valor en bolsa ronda los 104 millones",
            "pt": "Gráfico de barras: a Nakamoto deve à Kraken 165 milhões de USDT, seus 3.030 bitcoins dados em garantia valem cerca de US$ 208 milhões e seu valor de mercado na bolsa é de cerca de US$ 104 milhões",
            "fr": "Graphique en barres : Nakamoto doit 165 millions d'USDT à Kraken, ses 3 030 bitcoins nantis valent environ 208 millions de dollars et sa capitalisation boursière avoisine 104 millions",
            "de": "Balkendiagramm: Nakamoto schuldet Kraken 165 Mio. USDT, die 3.030 verpfändeten Bitcoin sind rund 208 Mio. $ wert, der Börsenwert liegt bei rund 104 Mio. $",
            "ru": "Столбчатая диаграмма: Nakamoto должна Kraken 165 млн USDT, 3030 заложенных биткоинов стоят около $208 млн, а рыночная капитализация компании около $104 млн",
            "tr": "Çubuk grafik: Nakamoto'nun Kraken'e 165 milyon USDT borcu var, rehin verdiği 3.030 bitcoin yaklaşık 208 milyon $ değerinde, şirketin piyasa değeri ise yaklaşık 104 milyon $",
            "id": "Grafik batang: Nakamoto berutang 165 juta USDT kepada Kraken, 3.030 bitcoin yang dijaminkan bernilai sekitar US$208 juta, dan nilai pasar sahamnya sekitar US$104 juta",
            "ja": "棒グラフ：NakamotoのKrakenへの債務は1億6500万USDT、担保の3030BTCは約2億800万ドル、株式時価総額は約1億400万ドル",
            "ko": "막대 차트: 나카모토가 크라켄에 진 빚은 1억 6,500만 USDT, 담보로 잡힌 비트코인 3,030개의 가치는 약 2억 800만 달러, 시가총액은 약 1억 400만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinDesk, Nakamoto")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: BTCS's $64.1 million Aave loan, backed by 46,676 ETH, could face liquidation if ether falls to about $1,717, according to CoinDesk's calculation from Nov. 9 data", {
            "es": "Tarjeta: el préstamo de 64,1 millones de dólares de BTCS en Aave, respaldado por 46.676 ETH, podría ser liquidado si el ether cae a unos 1.717 dólares, según el cálculo de CoinDesk con datos del 9 de noviembre",
            "pt": "Cartão: o empréstimo de US$ 64,1 milhões da BTCS no Aave, garantido por 46.676 ETH, pode ser liquidado se o ether cair para cerca de US$ 1.717, segundo cálculo do CoinDesk com dados de 9 de novembro",
            "fr": "Encadré : le prêt de 64,1 millions de dollars de BTCS sur Aave, garanti par 46 676 ETH, pourrait être liquidé si l'ether tombe vers 1 717 dollars, selon le calcul de CoinDesk à partir des données du 9 novembre",
            "de": "Faktenkarte: Der Aave-Kredit von BTCS über 64,1 Mio. $, besichert mit 46.676 ETH, könnte liquidiert werden, wenn Ether auf rund 1.717 $ fällt, so die Berechnung von CoinDesk mit Daten vom 9. November",
            "ru": "Карточка: кредит BTCS в Aave на $64,1 млн под залог 46 676 ETH может быть ликвидирован, если эфир упадет примерно до $1717, по расчету CoinDesk на основе данных на 9 ноября",
            "tr": "Kart: BTCS'nin 46.676 ETH teminatlı 64,1 milyon $'lık Aave kredisi, CoinDesk'in 9 Kasım verilerine dayanan hesabına göre ether yaklaşık 1.717 $'a düşerse tasfiye edilebilir",
            "id": "Kartu fakta: pinjaman Aave BTCS senilai US$64,1 juta dengan jaminan 46.676 ETH bisa dilikuidasi jika ether turun ke sekitar US$1.717, menurut perhitungan CoinDesk dari data 9 November",
            "ja": "カード：46,676ETHを担保とするBTCSのAaveでの6410万ドルの借り入れは、イーサが約1717ドルまで下がると清算の恐れ（11月9日のデータに基づくCoinDeskの計算）",
            "ko": "카드: 46,676 ETH를 담보로 한 BTCS의 6,410만 달러 에이브 대출은 이더가 약 1,717달러까지 떨어지면 청산될 수 있다(11월 9일 자료 기준 CoinDesk 계산)",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="BTCS filing via CoinDesk")},
    ]


def build_btc_below_67k():
    slug = "bitcoin-below-67000-sixth-weekly-loss-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 9 00:00 UTC - Nov 14 13:00 UTC (last bar). Lowest trade: $66,402.4 in the
    # Nov 14 04:00 UTC hour, lowest since Aug 19 on Kraken daily lows.
    xs, ys = fetch_kraken_hourly(1794182400, 1794664800)
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-9-14",
        xs, ys,
        title="Bitcoin hourly price, Nov. 9-14, 2026 (Kraken, UTC)",
        hline=66402.4,
        hlabel="Nov. 14 low ≈ $66,400 (Kraken)",
        date_fmt="%b %d",
    )
    # Farside Investors daily U.S. spot bitcoin ETF net flows (US$m), read Nov 14, 2026.
    flows = make_bar_chart(
        d / "chart-etf-outflows-nov-5-13",
        ["Nov 5", "Nov 6", "Nov 9", "Nov 10", "Nov 11", "Nov 12", "Nov 13"],
        [430.2, 411.9, 201.0, 95.0, 299.8, 284.1, 185.4],
        "U.S. spot bitcoin ETF net outflows by day, $ millions (Farside)",
        colors=["#f87171"] * 7,
        value_fmt=lambda v: f"-${v:,.1f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    # Alternative.me Crypto Fear and Greed Index, Nov 12-14, 2026: 28, 20, 13.
    card = make_fact_card(
        d / "fact-fear-greed-13",
        label="Crypto Fear and Greed Index",
        big="13: Extreme Fear",
        sub="Saturday's reading, down from 20 on Friday and 28 on Thursday (scale of 0 to 100).",
        footer="Alternative.me · Nov. 14, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 9 to Nov. 14, 2026, falling from about $75,000 to under $67,000, with a dashed line at the Nov. 14 low of about $66,400", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 9 al 14 de noviembre de 2026: cae de unos 75.000 dólares a menos de 67.000, con una línea discontinua en el mínimo del 14 de noviembre, de unos 66.400 dólares",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 9 a 14 de novembro de 2026: cai de cerca de US$ 75.000 para menos de US$ 67.000, com uma linha tracejada na mínima de 14 de novembro, de cerca de US$ 66.400",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 9 au 14 novembre 2026 : il passe d'environ 75 000 dollars à moins de 67 000 dollars, avec une ligne pointillée au plus bas du 14 novembre, environ 66 400 dollars",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 9. bis 14. November 2026: Rückgang von rund 75.000 $ auf unter 67.000 $; gestrichelte Linie beim Tief vom 14. November von rund 66.400 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 9 по 14 ноября 2026 года: падение примерно с $75 000 до уровня ниже $67 000; пунктирная линия показывает минимум 14 ноября, около $66 400",
            "tr": "Bitcoin'in 9-14 Kasım 2026 arasında Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 75.000 $'dan 67.000 $'ın altına düşüyor; kesikli çizgi 14 Kasım'daki yaklaşık 66.400 $'lık dibi gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken dari 9 hingga 14 November 2026: turun dari sekitar US$75.000 ke bawah US$67.000, dengan garis putus-putus di level terendah 14 November sekitar US$66.400",
            "ja": "2026年11月9〜14日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約7万5000ドルから6万7000ドル未満に下落。破線は11月14日の安値（約6万6400ドル）",
            "ko": "2026년 11월 9~14일 크라켄 비트코인 시간별 가격 선 차트: 약 75,000달러에서 67,000달러 아래로 하락, 점선은 11월 14일 저점 약 66,400달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "flows", "file": flows.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of daily net outflows from U.S. spot bitcoin ETFs: $430.2 million on Nov. 5, $411.9 million on Nov. 6, $201.0 million on Nov. 9, $95.0 million on Nov. 10, $299.8 million on Nov. 11, $284.1 million on Nov. 12 and $185.4 million on Nov. 13", {
            "es": "Gráfico de barras de las salidas netas diarias de los ETF de bitcoin al contado en EE. UU.: 430,2 millones de dólares el 5 de noviembre, 411,9 millones el 6, 201,0 millones el 9, 95,0 millones el 10, 299,8 millones el 11, 284,1 millones el 12 y 185,4 millones el 13",
            "pt": "Gráfico de barras das saídas líquidas diárias dos ETFs de bitcoin à vista dos EUA: US$ 430,2 milhões em 5 de novembro, US$ 411,9 milhões no dia 6, US$ 201,0 milhões no dia 9, US$ 95,0 milhões no dia 10, US$ 299,8 milhões no dia 11, US$ 284,1 milhões no dia 12 e US$ 185,4 milhões no dia 13",
            "fr": "Graphique en barres des sorties nettes quotidiennes des ETF bitcoin au comptant américains : 430,2 millions de dollars le 5 novembre, 411,9 millions le 6, 201,0 millions le 9, 95,0 millions le 10, 299,8 millions le 11, 284,1 millions le 12 et 185,4 millions le 13",
            "de": "Balkendiagramm der täglichen Nettoabflüsse aus US-Spot-Bitcoin-ETFs: 430,2 Mio. $ am 5. November, 411,9 Mio. $ am 6., 201,0 Mio. $ am 9., 95,0 Mio. $ am 10., 299,8 Mio. $ am 11., 284,1 Mio. $ am 12. und 185,4 Mio. $ am 13. November",
            "ru": "Столбчатая диаграмма дневного чистого оттока из американских спотовых биткоин-ETF: $430,2 млн 5 ноября, $411,9 млн 6 ноября, $201,0 млн 9 ноября, $95,0 млн 10 ноября, $299,8 млн 11 ноября, $284,1 млн 12 ноября и $185,4 млн 13 ноября",
            "tr": "ABD spot bitcoin ETF'lerinden günlük net çıkışların çubuk grafiği: 5 Kasım'da 430,2 milyon $, 6 Kasım'da 411,9 milyon $, 9 Kasım'da 201,0 milyon $, 10 Kasım'da 95,0 milyon $, 11 Kasım'da 299,8 milyon $, 12 Kasım'da 284,1 milyon $ ve 13 Kasım'da 185,4 milyon $",
            "id": "Grafik batang arus keluar bersih harian ETF bitcoin spot AS: US$430,2 juta pada 5 November, US$411,9 juta pada 6 November, US$201,0 juta pada 9 November, US$95,0 juta pada 10 November, US$299,8 juta pada 11 November, US$284,1 juta pada 12 November, dan US$185,4 juta pada 13 November",
            "ja": "米国の現物ビットコインETFの日次純流出額の棒グラフ：11月5日4億3020万ドル、6日4億1190万ドル、9日2億100万ドル、10日9500万ドル、11日2億9980万ドル、12日2億8410万ドル、13日1億8540万ドル",
            "ko": "미국 현물 비트코인 ETF 일별 순유출 막대 차트: 11월 5일 4억 3,020만 달러, 6일 4억 1,190만 달러, 9일 2억 100만 달러, 10일 9,500만 달러, 11일 2억 9,980만 달러, 12일 2억 8,410만 달러, 13일 1억 8,540만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the Crypto Fear and Greed Index read 13, extreme fear, on Nov. 14, down from 20 on Nov. 13 and 28 on Nov. 12", {
            "es": "Tarjeta: el índice de miedo y codicia cripto marcó 13, miedo extremo, el 14 de noviembre, frente a 20 el 13 y 28 el 12",
            "pt": "Cartão: o índice de medo e ganância cripto marcou 13, medo extremo, em 14 de novembro, ante 20 no dia 13 e 28 no dia 12",
            "fr": "Encadré : l'indice de peur et d'avidité crypto était à 13, peur extrême, le 14 novembre, contre 20 le 13 et 28 le 12",
            "de": "Faktenkarte: Der Crypto Fear and Greed Index lag am 14. November bei 13, extreme Angst, nach 20 am 13. und 28 am 12. November",
            "ru": "Карточка: индекс страха и жадности на криптовалютном рынке 14 ноября составил 13, «крайний страх», после 20 13 ноября и 28 12 ноября",
            "tr": "Kart: Kripto Korku ve Açgözlülük Endeksi 14 Kasım'da 13 ile aşırı korku seviyesindeydi; 13 Kasım'da 20, 12 Kasım'da 28'di",
            "id": "Kartu fakta: Crypto Fear and Greed Index berada di 13, ketakutan ekstrem, pada 14 November, turun dari 20 pada 13 November dan 28 pada 12 November",
            "ja": "カード：暗号資産の恐怖・強欲指数は11月14日に13（極度の恐怖）。13日は20、12日は28",
            "ko": "카드: 암호화폐 공포·탐욕 지수는 11월 14일 13(극단적 공포)으로, 13일 20, 12일 28에서 하락",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Alternative.me")},
    ]


def build_unocoin_hack():
    slug = "unocoin-hack-bitgo-backup-keys-nov-2026"
    d = OUT / slug
    # Unocoin incident updates (Nov 12, 13, 14, 2026) and BitGo blog (Nov 13, 2026).
    tl = make_timeline_card(
        d / "timeline-unocoin-incident",
        "How the Unocoin incident unfolded",
        [
            ("Nov. 6", "Suspicious activity found; BitGo and Fireblocks accounts frozen", (96, 165, 250)),
            ("Nov. 9", "More unauthorized activity; all services suspended", (248, 113, 113)),
            ("Nov. 13", "BitGo: transfers signed with Unocoin's user and backup keys", ORANGE),
            ("Nov. 14", "Loss estimated at about $200,000 from 3 hot wallets", (248, 113, 113)),
        ],
        footer="Unocoin incident updates · BitGo",
        margin=170, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-unocoin-200k",
        label="Estimated crypto loss",
        big="About $200,000",
        sub="Taken from 3 of Unocoin's 20+ operational wallets. Unocoin says it will cover the loss from its own resources.",
        footer="Unocoin security incident update · Nov. 14, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Nov. 6, Unocoin finds suspicious activity and freezes its BitGo and Fireblocks accounts; Nov. 9, more unauthorized activity and all services suspended; Nov. 13, BitGo says transfers were signed with Unocoin's user and backup keys; Nov. 14, loss estimated at about $200,000 from three hot wallets", {
            "es": "Cronología: 6 de nov., Unocoin detecta actividad sospechosa y congela sus cuentas en BitGo y Fireblocks; 9 de nov., más actividad no autorizada y suspensión de todos los servicios; 13 de nov., BitGo dice que las transferencias se firmaron con las claves de usuario y de respaldo de Unocoin; 14 de nov., pérdida estimada en unos 200.000 dólares de tres billeteras calientes",
            "pt": "Linha do tempo: 6 de nov., a Unocoin detecta atividade suspeita e congela suas contas na BitGo e na Fireblocks; 9 de nov., mais atividade não autorizada e suspensão de todos os serviços; 13 de nov., a BitGo diz que as transferências foram assinadas com as chaves de usuário e de backup da Unocoin; 14 de nov., perda estimada em cerca de US$ 200.000 de três carteiras quentes",
            "fr": "Chronologie : 6 nov., Unocoin repère une activité suspecte et gèle ses comptes chez BitGo et Fireblocks ; 9 nov., nouvelle activité non autorisée et suspension de tous les services ; 13 nov., BitGo indique que les transferts ont été signés avec les clés utilisateur et de secours d'Unocoin ; 14 nov., perte estimée à environ 200 000 dollars sur trois portefeuilles chauds",
            "de": "Zeitleiste: 6. Nov., Unocoin entdeckt verdächtige Aktivitäten und friert seine Konten bei BitGo und Fireblocks ein; 9. Nov., weitere unbefugte Aktivitäten, alle Dienste ausgesetzt; 13. Nov., BitGo: Überweisungen wurden mit Unocoins Nutzer- und Backup-Schlüssel signiert; 14. Nov., Verlust auf rund 200.000 $ aus drei Hot Wallets geschätzt",
            "ru": "Хронология: 6 ноября Unocoin обнаруживает подозрительную активность и замораживает аккаунты в BitGo и Fireblocks; 9 ноября новая несанкционированная активность, все сервисы приостановлены; 13 ноября BitGo сообщает, что переводы подписаны пользовательским и резервным ключами Unocoin; 14 ноября потери оценены примерно в $200 000 из трех горячих кошельков",
            "tr": "Zaman çizelgesi: 6 Kasım'da Unocoin şüpheli hareket tespit edip BitGo ve Fireblocks hesaplarını donduruyor; 9 Kasım'da yeni yetkisiz hareketler, tüm hizmetler askıya alınıyor; 13 Kasım'da BitGo transferlerin Unocoin'in kullanıcı ve yedek anahtarlarıyla imzalandığını söylüyor; 14 Kasım'da üç sıcak cüzdandan yaklaşık 200.000 $ kayıp tahmin ediliyor",
            "id": "Linimasa: 6 Nov, Unocoin menemukan aktivitas mencurigakan dan membekukan akun BitGo serta Fireblocks; 9 Nov, aktivitas tidak sah lagi dan semua layanan dihentikan; 13 Nov, BitGo menyatakan transfer ditandatangani dengan kunci pengguna dan kunci cadangan Unocoin; 14 Nov, kerugian diperkirakan sekitar US$200.000 dari tiga hot wallet",
            "ja": "時系列：11月6日、Unocoinが不審な動きを検知しBitGoとFireblocksの口座を凍結。11月9日、さらなる不正な動きで全サービス停止。11月13日、BitGoが送金はUnocoinのユーザー鍵とバックアップ鍵で署名されたと説明。11月14日、ホットウォレット3つから約20万ドルの損失と推計",
            "ko": "타임라인: 11월 6일 유노코인이 의심 활동을 발견하고 BitGo·Fireblocks 계정 동결, 11월 9일 추가 무단 활동으로 전체 서비스 중단, 11월 13일 BitGo가 유노코인의 사용자 키와 백업 키로 서명됐다고 발표, 11월 14일 핫월렛 3개에서 약 20만 달러 손실 추정",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Unocoin incident updates; BitGo")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Unocoin estimates its crypto loss at about $200,000, taken from 3 of its more than 20 operational wallets, and says it will cover the loss from its own resources", {
            "es": "Tarjeta: Unocoin estima su pérdida en criptomonedas en unos 200.000 dólares, sustraídos de 3 de sus más de 20 billeteras operativas, y dice que la cubrirá con recursos propios",
            "pt": "Cartão: a Unocoin estima sua perda em cripto em cerca de US$ 200.000, retirados de 3 de suas mais de 20 carteiras operacionais, e diz que vai cobrir a perda com recursos próprios",
            "fr": "Encadré : Unocoin estime sa perte en cryptos à environ 200 000 dollars, prélevés sur 3 de ses plus de 20 portefeuilles opérationnels, et dit qu'elle la couvrira sur ses fonds propres",
            "de": "Faktenkarte: Unocoin schätzt seinen Kryptoverlust auf rund 200.000 $ aus 3 seiner mehr als 20 Betriebs-Wallets und will den Verlust aus eigenen Mitteln decken",
            "ru": "Карточка: Unocoin оценивает потери в криптовалюте примерно в $200 000 из 3 из более чем 20 рабочих кошельков и обещает покрыть их из собственных средств",
            "tr": "Kart: Unocoin kripto kaybını 20'den fazla operasyonel cüzdanından 3'ünden alınan yaklaşık 200.000 $ olarak tahmin ediyor ve kaybı kendi kaynaklarından karşılayacağını söylüyor",
            "id": "Kartu fakta: Unocoin memperkirakan kerugian kripto sekitar US$200.000 dari 3 dari lebih 20 dompet operasionalnya dan akan menanggungnya dari dana sendiri",
            "ja": "カード：Unocoinは20を超える運用ウォレットのうち3つから約20万ドルの暗号資産が失われたと推計し、自己資金で補填すると説明",
            "ko": "카드: 유노코인은 20개가 넘는 운영 지갑 중 3개에서 약 20만 달러의 암호화폐 손실이 났다고 추정하며, 자체 자금으로 보전하겠다고 밝혔다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Unocoin security incident update")},
    ]


def _kraken_open(pair: str, ts: int) -> float:
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=60"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = next(v for k, v in data["result"].items() if k != "last")
    return next(float(r[1]) for r in rows if int(r[0]) == ts)


def build_alt_selloff():
    slug = "ether-solana-xrp-lead-selloff-bitcoin-65000-nov-2026"
    d = OUT / slug
    # 24h change on Kraken: open of the Nov 13 19:00 UTC hourly bar vs open of the Nov 14 19:00 UTC bar (1 p.m. CT).
    t1 = 1794682800
    t0 = t1 - 86400
    pairs = [("Bitcoin", "XBTUSD"), ("Ether", "ETHUSD"), ("XRP", "XRPUSD"), ("Solana", "SOLUSD")]
    drops = []
    for _name, pair in pairs:
        a, b = _kraken_open(pair, t0), _kraken_open(pair, t1)
        drops.append(round((1 - b / a) * 100, 1))
    print("  24h drops", drops)  # expected about 5.0, 5.8, 6.7, 9.8
    chart = make_bar_chart(
        d / "chart-24h-drops-nov-14",
        [p[0] for p in pairs], drops,
        "24-hour price drop to 1 p.m. CT, Nov. 14, 2026 (Kraken), %",
        colors=["#f7931a", "#818cf8", "#94a3b8", "#f87171"],
        value_fmt=lambda v: f"-{v:.1f}%",
        axis_fmt=lambda x, _p: f"{x:.0f}%",
    )
    # Kraken ETHUSD hourly closes, Nov 13 00:00 UTC - Nov 14 19:00 UTC. Low: $1,808.25 in the Nov 14 16:00 UTC hour.
    xs, ys = fetch_kraken_hourly(t1 - 86400 - 19 * 3600, t1, pair="ETHUSD")
    eth = make_line_chart(
        d / "chart-eth-hourly-nov-13-14",
        xs, ys,
        title="Ether hourly price, Nov. 13-14, 2026 (Kraken, UTC)",
        hline=1808.25,
        hlabel="Nov. 14 low ≈ $1,808 (Kraken)",
        date_fmt="%b %d %H:%M",
    )
    card = make_fact_card(
        d / "fact-liquidations-1-01b",
        label="Crypto liquidations in 24 hours",
        big="$1.01 billion",
        sub="93% were bets on rising prices. More than 195,000 traders were affected.",
        footer="CoinGlass data via Trending Topics · Nov. 14, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of 24-hour price drops on Kraken to 1 p.m. Central time on Nov. 14, 2026: bitcoin down 5.0%, ether 5.8%, XRP 6.7% and solana 9.8%", {
            "es": "Gráfico de barras de las caídas de precio en 24 horas en Kraken hasta la 1 p. m. (hora central de EE. UU.) del 14 de noviembre de 2026: bitcoin bajó un 5,0 %, ether un 5,8 %, XRP un 6,7 % y solana un 9,8 %",
            "pt": "Gráfico de barras das quedas de preço em 24 horas na Kraken até 13h (horário central dos EUA) de 14 de novembro de 2026: bitcoin caiu 5,0%, ether 5,8%, XRP 6,7% e solana 9,8%",
            "fr": "Graphique en barres des baisses de prix sur 24 heures sur Kraken jusqu'à 13 h (heure du Centre des États-Unis) le 14 novembre 2026 : bitcoin en baisse de 5,0 %, ether de 5,8 %, XRP de 6,7 % et solana de 9,8 %",
            "de": "Balkendiagramm der 24-Stunden-Kursverluste bei Kraken bis 13 Uhr US-Central-Zeit am 14. November 2026: Bitcoin minus 5,0 %, Ether 5,8 %, XRP 6,7 % und Solana 9,8 %",
            "ru": "Столбчатая диаграмма падения цен за 24 часа на Kraken к 13:00 по центральному времени США 14 ноября 2026 года: биткоин минус 5,0%, эфир 5,8%, XRP 6,7%, солана 9,8%",
            "tr": "14 Kasım 2026'da ABD Merkezi saatiyle 13.00'e kadar Kraken'de 24 saatlik fiyat düşüşlerinin çubuk grafiği: bitcoin %5,0, ether %5,8, XRP %6,7 ve solana %9,8 düştü",
            "id": "Grafik batang penurunan harga 24 jam di Kraken hingga pukul 13.00 waktu Central AS pada 14 November 2026: bitcoin turun 5,0%, ether 5,8%, XRP 6,7%, dan solana 9,8%",
            "ja": "2026年11月14日午後1時（米中部時間）までの24時間のKrakenでの下落率の棒グラフ：ビットコイン5.0%、イーサ5.8%、XRP6.7%、ソラナ9.8%",
            "ko": "2026년 11월 14일 오후 1시(미국 중부시간)까지 24시간 동안 크라켄 가격 하락률 막대 차트: 비트코인 5.0%, 이더 5.8%, XRP 6.7%, 솔라나 9.8% 하락",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken hourly prices")},
        {"id": "ether", "file": eth.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of ether's hourly price on Kraken from Nov. 13 to Nov. 14, 2026, falling from about $2,000 to about $1,830, with a dashed line at the Nov. 14 low of about $1,808", {
            "es": "Gráfico de líneas del precio horario de ether en Kraken del 13 al 14 de noviembre de 2026: cae de unos 2.000 dólares a unos 1.830, con una línea discontinua en el mínimo del 14 de noviembre, de unos 1.808 dólares",
            "pt": "Gráfico de linha do preço horário do ether na Kraken de 13 a 14 de novembro de 2026: cai de cerca de US$ 2.000 para cerca de US$ 1.830, com uma linha tracejada na mínima de 14 de novembro, de cerca de US$ 1.808",
            "fr": "Courbe du cours horaire de l'ether sur Kraken du 13 au 14 novembre 2026 : il passe d'environ 2 000 dollars à environ 1 830 dollars, avec une ligne pointillée au plus bas du 14 novembre, environ 1 808 dollars",
            "de": "Liniendiagramm des stündlichen Ether-Kurses bei Kraken vom 13. bis 14. November 2026: Rückgang von rund 2.000 $ auf rund 1.830 $; gestrichelte Linie beim Tief vom 14. November von rund 1.808 $",
            "ru": "Линейный график почасовой цены эфира на Kraken 13 и 14 ноября 2026 года: падение примерно с $2000 до около $1830; пунктирная линия показывает минимум 14 ноября, около $1808",
            "tr": "Ether'in 13-14 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 2.000 $'dan yaklaşık 1.830 $'a düşüyor; kesikli çizgi 14 Kasım'daki yaklaşık 1.808 $'lık dibi gösteriyor",
            "id": "Grafik garis harga ether per jam di Kraken pada 13 hingga 14 November 2026: turun dari sekitar US$2.000 ke sekitar US$1.830, dengan garis putus-putus di level terendah 14 November sekitar US$1.808",
            "ja": "2026年11月13〜14日のKrakenにおけるイーサ1時間足の折れ線グラフ：約2000ドルから約1830ドルに下落。破線は11月14日の安値（約1808ドル）",
            "ko": "2026년 11월 13~14일 크라켄 이더 시간별 가격 선 차트: 약 2,000달러에서 약 1,830달러로 하락, 점선은 11월 14일 저점 약 1,808달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken ETH/USD hourly closes")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $1.01 billion in crypto positions were liquidated in 24 hours on Nov. 14, 93% of them bets on rising prices, affecting more than 195,000 traders", {
            "es": "Tarjeta: unos 1.010 millones de dólares en posiciones cripto fueron liquidados en 24 horas el 14 de noviembre; el 93 % eran apuestas al alza y hubo más de 195.000 operadores afectados",
            "pt": "Cartão: cerca de US$ 1,01 bilhão em posições de cripto foram liquidadas em 24 horas em 14 de novembro; 93% eram apostas na alta, e mais de 195.000 traders foram afetados",
            "fr": "Encadré : environ 1,01 milliard de dollars de positions crypto ont été liquidées en 24 heures le 14 novembre, dont 93 % de paris à la hausse, touchant plus de 195 000 traders",
            "de": "Faktenkarte: Rund 1,01 Mrd. $ an Kryptopositionen wurden am 14. November binnen 24 Stunden liquidiert, 93 % davon Wetten auf steigende Kurse; mehr als 195.000 Trader waren betroffen",
            "ru": "Карточка: около $1,01 млрд криптопозиций ликвидировано за 24 часа 14 ноября, 93% из них были ставками на рост; пострадали более 195 000 трейдеров",
            "tr": "Kart: 14 Kasım'da 24 saatte yaklaşık 1,01 milyar $'lık kripto pozisyonu tasfiye edildi; bunların %93'ü yükseliş bahsiydi ve 195.000'den fazla yatırımcı etkilendi",
            "id": "Kartu fakta: sekitar US$1,01 miliar posisi kripto dilikuidasi dalam 24 jam pada 14 November, 93% di antaranya taruhan harga naik, dan lebih dari 195.000 trader terdampak",
            "ja": "カード：11月14日の24時間で約10億1000万ドルの暗号資産ポジションが清算され、93%が上昇に賭けたポジション。影響を受けたトレーダーは19万5000人超",
            "ko": "카드: 11월 14일 24시간 동안 약 10억 1,000만 달러 규모의 암호화폐 포지션이 청산됐고, 93%가 상승 베팅이었으며 19만 5,000명 넘는 트레이더가 영향을 받았다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via Trending Topics")},
    ]


def build_binance_reopen():
    slug = "binance-reopens-withdrawals-87-networks-nov-2026"
    d = OUT / slug
    # Binance recovery updates (Nov 1, Nov 12, Nov 14, 2026); CoinDesk, Reuters, Bitcoin Magazine.
    tl = make_timeline_card(
        d / "timeline-binance-withdrawals",
        "Binance hack recovery so far",
        [
            ("Oct. 29", "Hackers take about $6.3 billion from hot wallets", (248, 113, 113)),
            ("Nov. 1", "Withdrawals restart for 15 assets and networks, led by bitcoin", (96, 165, 250)),
            ("Nov. 12", "Binance says it has covered all affected assets", GREEN),
            ("Nov. 14", "87 more networks reopened this week; rest targeted by end of next week", ORANGE),
        ],
        footer="Binance updates · CoinDesk · Reuters · Bitcoin Magazine",
        margin=170, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-87-networks",
        label="Binance withdrawals reopened this week",
        big="87 networks",
        sub="Binance aims to reopen withdrawals for all remaining networks and assets by the end of next week.",
        footer="Binance on X · Nov. 14, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Oct. 29, hackers take about $6.3 billion from Binance hot wallets; Nov. 1, withdrawals restart for 15 assets and networks, led by bitcoin; Nov. 12, Binance says it has covered all affected assets; Nov. 14, 87 more networks reopened this week and the rest targeted by the end of next week", {
            "es": "Cronología: 29 de oct., los hackers se llevan unos 6.300 millones de dólares de las billeteras calientes de Binance; 1 de nov., se reanudan los retiros de 15 activos y redes, empezando por bitcoin; 12 de nov., Binance dice que ha cubierto todos los activos afectados; 14 de nov., 87 redes más reabiertas esta semana y el resto previsto para finales de la próxima",
            "pt": "Linha do tempo: 29 de out., hackers levam cerca de US$ 6,3 bilhões das carteiras quentes da Binance; 1º de nov., os saques voltam para 15 ativos e redes, a começar pelo bitcoin; 12 de nov., a Binance diz que cobriu todos os ativos afetados; 14 de nov., mais 87 redes reabertas nesta semana e o restante previsto para o fim da próxima",
            "fr": "Chronologie : 29 oct., des pirates dérobent environ 6,3 milliards de dollars dans les portefeuilles chauds de Binance ; 1er nov., reprise des retraits pour 15 actifs et réseaux, à commencer par le bitcoin ; 12 nov., Binance dit avoir couvert tous les actifs touchés ; 14 nov., 87 réseaux de plus rouverts cette semaine, le reste visé d'ici la fin de la semaine prochaine",
            "de": "Zeitleiste: 29. Okt., Hacker erbeuten rund 6,3 Mrd. $ aus Binances Hot Wallets; 1. Nov., Auszahlungen für 15 Assets und Netzwerke laufen wieder an, angeführt von Bitcoin; 12. Nov., Binance meldet die vollständige Deckung aller betroffenen Assets; 14. Nov., 87 weitere Netzwerke diese Woche geöffnet, der Rest bis Ende nächster Woche geplant",
            "ru": "Хронология: 29 октября хакеры похищают около $6,3 млрд из горячих кошельков Binance; 1 ноября вывод возобновлен для 15 активов и сетей, первым стал биткоин; 12 ноября Binance заявляет, что покрыла все затронутые активы; 14 ноября на этой неделе открыты еще 87 сетей, остальные планируется открыть к концу следующей недели",
            "tr": "Zaman çizelgesi: 29 Ekim'de bilgisayar korsanları Binance'in sıcak cüzdanlarından yaklaşık 6,3 milyar $ alıyor; 1 Kasım'da bitcoin başta olmak üzere 15 varlık ve ağda çekimler yeniden başlıyor; 12 Kasım'da Binance etkilenen tüm varlıkları karşıladığını söylüyor; 14 Kasım'da bu hafta 87 ağ daha açıldı, kalanlar gelecek hafta sonuna kadar hedefleniyor",
            "id": "Linimasa: 29 Okt, peretas mengambil sekitar US$6,3 miliar dari hot wallet Binance; 1 Nov, penarikan dibuka lagi untuk 15 aset dan jaringan, diawali bitcoin; 12 Nov, Binance menyatakan telah menutup semua aset terdampak; 14 Nov, 87 jaringan lagi dibuka pekan ini dan sisanya ditargetkan akhir pekan depan",
            "ja": "時系列：10月29日、ハッカーがBinanceのホットウォレットから約63億ドルを奪う。11月1日、ビットコインを筆頭に15の資産・ネットワークで出金再開。11月12日、Binanceが影響を受けた資産の補填完了を発表。11月14日、今週さらに87ネットワークを再開し、残りは来週末までを目標",
            "ko": "타임라인: 10월 29일 해커가 바이낸스 핫월렛에서 약 63억 달러 탈취, 11월 1일 비트코인을 시작으로 15개 자산·네트워크 출금 재개, 11월 12일 바이낸스가 피해 자산 보전 완료 발표, 11월 14일 이번 주 87개 네트워크 추가 재개, 나머지는 다음 주 말까지 목표",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Binance; CoinDesk; Reuters; Bitcoin Magazine")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Binance reopened withdrawals on 87 networks this week and aims to reopen all remaining networks and assets by the end of next week", {
            "es": "Tarjeta: Binance reabrió los retiros en 87 redes esta semana y aspira a reabrir todas las redes y activos restantes antes de que termine la próxima semana",
            "pt": "Cartão: a Binance reabriu os saques em 87 redes nesta semana e pretende reabrir todas as redes e ativos restantes até o fim da próxima semana",
            "fr": "Encadré : Binance a rouvert les retraits sur 87 réseaux cette semaine et vise à rouvrir tous les réseaux et actifs restants d'ici la fin de la semaine prochaine",
            "de": "Faktenkarte: Binance hat diese Woche Auszahlungen in 87 Netzwerken wieder geöffnet und will alle übrigen Netzwerke und Assets bis Ende nächster Woche freigeben",
            "ru": "Карточка: на этой неделе Binance открыла вывод в 87 сетях и стремится открыть все оставшиеся сети и активы до конца следующей недели",
            "tr": "Kart: Binance bu hafta 87 ağda çekimleri yeniden açtı ve kalan tüm ağ ve varlıkları gelecek hafta sonuna kadar açmayı hedefliyor",
            "id": "Kartu fakta: Binance membuka kembali penarikan di 87 jaringan pekan ini dan menargetkan membuka semua jaringan dan aset yang tersisa paling lambat akhir pekan depan",
            "ja": "カード：Binanceは今週87のネットワークで出金を再開し、残りすべてのネットワークと資産を来週末までに再開することを目指す",
            "ko": "카드: 바이낸스는 이번 주 87개 네트워크에서 출금을 재개했으며, 나머지 모든 네트워크와 자산을 다음 주 말까지 재개하는 것을 목표로 한다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Binance on X")},
    ]


def build_btc_below_64k():
    slug = "bitcoin-falls-below-64000-three-month-low-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Mon Nov 9 00:00 UTC to Nov 15 00:00 UTC. Low $63,242.60 in the Nov 14 22:00 UTC hour.
    t_end = 1794700800
    xs, ys = fetch_kraken_hourly(t_end - 6 * 86400, t_end, pair="XBTUSD")
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-9-14",
        xs, ys,
        title="Bitcoin hourly price, Nov. 9-14, 2026 (Kraken, UTC)",
        hline=63242.6,
        hlabel="Nov. 14 low ≈ $63,243 (Kraken)",
    )
    card = make_fact_card(
        d / "fact-fear-greed-10",
        label="Crypto Fear and Greed Index",
        big="10 out of 100",
        sub="Extreme fear. Down from 13 on Nov. 14 and 20 on Nov. 13.",
        footer="Alternative.me · reading for Nov. 15, 2026 (UTC)",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 9 to Nov. 14, 2026, falling from about $75,000 to about $64,000, with a dashed line at the Nov. 14 low of about $63,243", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 9 al 14 de noviembre de 2026: cae de unos 75.000 dólares a unos 64.000, con una línea discontinua en el mínimo del 14 de noviembre, de unos 63.243 dólares",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 9 a 14 de novembro de 2026: cai de cerca de US$ 75.000 para cerca de US$ 64.000, com uma linha tracejada na mínima de 14 de novembro, de cerca de US$ 63.243",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 9 au 14 novembre 2026 : il passe d'environ 75 000 dollars à environ 64 000 dollars, avec une ligne pointillée au plus bas du 14 novembre, environ 63 243 dollars",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 9. bis 14. November 2026: Rückgang von rund 75.000 $ auf rund 64.000 $; gestrichelte Linie beim Tief vom 14. November von rund 63.243 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 9 по 14 ноября 2026 года: падение примерно с $75 000 до около $64 000; пунктирная линия показывает минимум 14 ноября, около $63 243",
            "tr": "Bitcoin'in 9-14 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 75.000 $'dan yaklaşık 64.000 $'a düşüyor; kesikli çizgi 14 Kasım'daki yaklaşık 63.243 $'lık dibi gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 9 hingga 14 November 2026: turun dari sekitar US$75.000 ke sekitar US$64.000, dengan garis putus-putus di level terendah 14 November sekitar US$63.243",
            "ja": "2026年11月9〜14日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約7万5000ドルから約6万4000ドルに下落。破線は11月14日の安値（約6万3243ドル）",
            "ko": "2026년 11월 9~14일 크라켄 비트코인 시간별 가격 선 차트: 약 7만 5,000달러에서 약 6만 4,000달러로 하락, 점선은 11월 14일 저점 약 6만 3,243달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the Crypto Fear and Greed Index read 10 out of 100, extreme fear, down from 13 on Nov. 14 and 20 on Nov. 13", {
            "es": "Tarjeta: el índice Crypto Fear and Greed marcó 10 sobre 100, miedo extremo, frente a 13 el 14 de noviembre y 20 el 13 de noviembre",
            "pt": "Cartão: o índice Crypto Fear and Greed marcou 10 de 100, medo extremo, ante 13 em 14 de novembro e 20 em 13 de novembro",
            "fr": "Encadré : l'indice Crypto Fear and Greed est tombé à 10 sur 100, peur extrême, contre 13 le 14 novembre et 20 le 13 novembre",
            "de": "Faktenkarte: Der Crypto Fear and Greed Index stand bei 10 von 100, extreme Angst, nach 13 am 14. November und 20 am 13. November",
            "ru": "Карточка: индекс страха и жадности криптовалют (Crypto Fear and Greed) опустился до 10 из 100, крайний страх; 14 ноября было 13, 13 ноября 20",
            "tr": "Kart: Kripto Korku ve Açgözlülük Endeksi 100 üzerinden 10'a, aşırı korku seviyesine indi; 14 Kasım'da 13, 13 Kasım'da 20'ydi",
            "id": "Kartu fakta: Crypto Fear and Greed Index berada di 10 dari 100, ketakutan ekstrem, turun dari 13 pada 14 November dan 20 pada 13 November",
            "ja": "カード：暗号資産の恐怖・強欲指数は100点中10の「極度の恐怖」。11月14日は13、11月13日は20だった",
            "ko": "카드: 암호화폐 공포·탐욕 지수가 100점 만점에 10으로 '극단적 공포' 수준, 11월 14일 13, 11월 13일 20에서 하락",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Alternative.me Crypto Fear and Greed Index")},
    ]


def build_kava_hack():
    slug = "kava-lend-hack-3-8-million-kava-falls-nov-2026"
    d = OUT / slug
    # Kraken KAVAUSD hourly closes, Nov 13 12:00 UTC to Nov 15 00:00 UTC. Low $0.0344 in the Nov 14 11:00 UTC hour.
    t_end = 1794700800
    xs, ys = fetch_kraken_hourly(t_end - 36 * 3600, t_end, pair="KAVAUSD")
    chart = make_line_chart(
        d / "chart-kava-hourly-nov-13-14",
        xs, ys,
        title="KAVA hourly price, Nov. 13-14, 2026 (Kraken, UTC)",
        hline=0.0344,
        hlabel="Nov. 14 low ≈ $0.0344 (Kraken)",
        date_fmt="%b %d %H:%M",
        yfmt=lambda x, _p: f"${x:.3f}",
    )
    tl = make_timeline_card(
        d / "timeline-kava-lend-attack",
        "Kava Lend attack (U.S. Central time)",
        [
            ("Fri 10:01 p.m.", "Attacker inflates BUSD deposits about 243,000-fold", (248, 113, 113)),
            ("Fri night", "KAVA borrowed 127 times; pool falls from 55.33M to 0.19 KAVA", (248, 113, 113)),
            ("Sat 3:59 a.m.", "About 49.2M KAVA bridged to BNB Chain and sold for about $2.1M", ORANGE),
            ("Sat 5:28 a.m.", "Kava confirms the incident; exchanges pause KAVA transfers", (96, 165, 250)),
        ],
        footer="The Block · Kava on X",
        margin=170, wrap_w=250,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of KAVA's hourly price on Kraken from Nov. 13 to Nov. 14, 2026: flat near $0.068, then a plunge on Nov. 14 to a low of about $0.0344 and a partial rebound to about $0.043", {
            "es": "Gráfico de líneas del precio horario de KAVA en Kraken del 13 al 14 de noviembre de 2026: estable cerca de 0,068 dólares, luego un desplome el 14 de noviembre hasta un mínimo de unos 0,0344 dólares y un rebote parcial hasta unos 0,043",
            "pt": "Gráfico de linha do preço horário do KAVA na Kraken de 13 a 14 de novembro de 2026: estável perto de US$ 0,068, depois um tombo em 14 de novembro até a mínima de cerca de US$ 0,0344 e uma recuperação parcial para cerca de US$ 0,043",
            "fr": "Courbe du cours horaire du KAVA sur Kraken du 13 au 14 novembre 2026 : stable vers 0,068 dollar, puis une chute le 14 novembre jusqu'à un plus bas d'environ 0,0344 dollar et un rebond partiel vers 0,043 dollar",
            "de": "Liniendiagramm des stündlichen KAVA-Kurses bei Kraken vom 13. bis 14. November 2026: stabil bei rund 0,068 $, dann am 14. November ein Absturz auf ein Tief von rund 0,0344 $ und eine teilweise Erholung auf rund 0,043 $",
            "ru": "Линейный график почасовой цены KAVA на Kraken 13 и 14 ноября 2026 года: около $0,068, затем обвал 14 ноября до минимума около $0,0344 и частичный отскок примерно до $0,043",
            "tr": "KAVA'nın 13-14 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: 0,068 $ civarında yatay, ardından 14 Kasım'da yaklaşık 0,0344 $'lık dibe sert düşüş ve yaklaşık 0,043 $'a kısmi toparlanma",
            "id": "Grafik garis harga KAVA per jam di Kraken pada 13 hingga 14 November 2026: datar di sekitar US$0,068, lalu anjlok pada 14 November ke titik terendah sekitar US$0,0344 dan pulih sebagian ke sekitar US$0,043",
            "ja": "2026年11月13〜14日のKrakenにおけるKAVA1時間足の折れ線グラフ：約0.068ドルで横ばいの後、11月14日に約0.0344ドルまで急落し、約0.043ドルまで一部回復",
            "ko": "2026년 11월 13~14일 크라켄 KAVA 시간별 가격 선 차트: 약 0.068달러에서 횡보하다 11월 14일 약 0.0344달러까지 급락한 뒤 약 0.043달러로 일부 반등",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken KAVA/USD hourly closes")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline in U.S. Central time: Friday 10:01 p.m., the attacker inflates BUSD deposits about 243,000-fold; Friday night, KAVA is borrowed 127 times and the pool falls from 55.33 million to 0.19 KAVA; Saturday 3:59 a.m., about 49.2 million KAVA is bridged to BNB Chain and sold for about $2.1 million; Saturday 5:28 a.m., Kava confirms the incident and exchanges pause KAVA transfers", {
            "es": "Cronología en hora central de EE. UU.: viernes 22:01, el atacante infla los depósitos de BUSD unas 243.000 veces; viernes por la noche, pide prestado KAVA 127 veces y el fondo baja de 55,33 millones a 0,19 KAVA; sábado 3:59, unos 49,2 millones de KAVA pasan a BNB Chain y se venden por unos 2,1 millones de dólares; sábado 5:28, Kava confirma el incidente y los exchanges pausan las transferencias de KAVA",
            "pt": "Linha do tempo no horário central dos EUA: sexta, 22h01, o atacante infla os depósitos de BUSD cerca de 243.000 vezes; sexta à noite, toma KAVA emprestado 127 vezes e o pool cai de 55,33 milhões para 0,19 KAVA; sábado, 3h59, cerca de 49,2 milhões de KAVA vão para a BNB Chain e são vendidos por cerca de US$ 2,1 milhões; sábado, 5h28, a Kava confirma o incidente e as corretoras pausam as transferências de KAVA",
            "fr": "Chronologie (heure du Centre des États-Unis) : vendredi 22 h 01, l'attaquant gonfle les dépôts en BUSD d'environ 243 000 fois ; vendredi soir, il emprunte du KAVA 127 fois et la réserve passe de 55,33 millions à 0,19 KAVA ; samedi 3 h 59, environ 49,2 millions de KAVA sont transférés vers BNB Chain et vendus pour environ 2,1 millions de dollars ; samedi 5 h 28, Kava confirme l'incident et les plateformes suspendent les transferts de KAVA",
            "de": "Zeitleiste (US-Central-Zeit): Freitag 22:01 Uhr, der Angreifer bläht BUSD-Einlagen rund 243.000-fach auf; Freitagnacht leiht er 127-mal KAVA, der Pool fällt von 55,33 Mio. auf 0,19 KAVA; Samstag 3:59 Uhr, rund 49,2 Mio. KAVA gehen über die Bridge zur BNB Chain und werden für rund 2,1 Mio. $ verkauft; Samstag 5:28 Uhr, Kava bestätigt den Vorfall, Börsen stoppen KAVA-Transfers",
            "ru": "Хронология по центральному времени США: пятница, 22:01, злоумышленник раздувает депозиты BUSD примерно в 243 000 раз; ночь на субботу, он 127 раз занимает KAVA, и пул сокращается с 55,33 млн до 0,19 KAVA; суббота, 3:59, около 49,2 млн KAVA переводятся в BNB Chain и продаются примерно за $2,1 млн; суббота, 5:28, Kava подтверждает инцидент, биржи приостанавливают переводы KAVA",
            "tr": "ABD Merkezi saatiyle zaman çizelgesi: cuma 22.01'de saldırgan BUSD mevduatlarını yaklaşık 243.000 kat şişiriyor; cuma gecesi 127 kez KAVA borç alıyor ve havuz 55,33 milyondan 0,19 KAVA'ya düşüyor; cumartesi 03.59'da yaklaşık 49,2 milyon KAVA BNB Chain'e aktarılıp yaklaşık 2,1 milyon $'a satılıyor; cumartesi 05.28'de Kava olayı doğruluyor ve borsalar KAVA transferlerini durduruyor",
            "id": "Linimasa waktu Central AS: Jumat 22.01, penyerang menggelembungkan deposit BUSD sekitar 243.000 kali; Jumat malam, KAVA dipinjam 127 kali dan pool turun dari 55,33 juta menjadi 0,19 KAVA; Sabtu 03.59, sekitar 49,2 juta KAVA dipindahkan ke BNB Chain dan dijual sekitar US$2,1 juta; Sabtu 05.28, Kava mengonfirmasi insiden dan bursa menghentikan transfer KAVA",
            "ja": "時系列（米中部時間）：金曜午後10時1分、攻撃者がBUSD預け入れを約24万3000倍に水増し。金曜夜、KAVAを127回借り入れ、プールは5533万KAVAから0.19KAVAに。土曜午前3時59分、約4920万KAVAをBNBチェーンにブリッジし約210万ドルで売却。土曜午前5時28分、Kavaが事案を認め、取引所がKAVAの入出金を停止",
            "ko": "타임라인(미국 중부시간): 금요일 오후 10시 1분 공격자가 BUSD 예치금을 약 24만 3,000배 부풀림, 금요일 밤 KAVA를 127번 대출해 풀이 5,533만 KAVA에서 0.19 KAVA로 감소, 토요일 오전 3시 59분 약 4,920만 KAVA를 BNB 체인으로 옮겨 약 210만 달러에 매도, 토요일 오전 5시 28분 Kava가 사고를 확인하고 거래소들이 KAVA 입출금 중단",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="The Block; Kava on X")},
    ]


def build_btc_62k_liquidations():
    slug = "bitcoin-four-month-low-62000-liquidations-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 12 00:00 UTC to Nov 15 15:00 UTC. Intrahour low $61,970.30 in the Nov 15 01:00 UTC hour.
    xs, ys = fetch_kraken_hourly(1794441600, 1794754800, pair="XBTUSD")
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-12-15",
        xs, ys,
        title="Bitcoin hourly price, Nov. 12-15, 2026 (Kraken, UTC)",
        hline=61970.3,
        hlabel="Low ≈ $61,970 (Kraken, Nov. 15 UTC)",
    )
    card = make_fact_card(
        d / "fact-liquidations-1-96b",
        label="Crypto liquidations in 24 hours",
        big="$1.96 billion",
        sub="About $750 million in bitcoin, $600.5 million of it from bets on higher prices.",
        footer="CoinGlass data via crypto.news · Nov. 15, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 12 to Nov. 15, 2026, falling from about $74,000 to about $62,600 at the worst hourly close and rebounding to about $65,000, with a dashed line at the intrahour low of about $61,970", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 12 al 15 de noviembre de 2026: cae de unos 74.000 dólares a unos 62.600 en el peor cierre horario y rebota hasta unos 65.000, con una línea discontinua en el mínimo intrahorario de unos 61.970 dólares",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 12 a 15 de novembro de 2026: cai de cerca de US$ 74.000 para cerca de US$ 62.600 no pior fechamento horário e volta para cerca de US$ 65.000, com uma linha tracejada na mínima intra-hora de cerca de US$ 61.970",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 12 au 15 novembre 2026 : il passe d'environ 74 000 dollars à environ 62 600 dollars au pire cours de clôture horaire, puis remonte vers 65 000 dollars, avec une ligne pointillée au plus bas intrahoraire d'environ 61 970 dollars",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 12. bis 15. November 2026: Rückgang von rund 74.000 $ auf rund 62.600 $ beim tiefsten Stundenschluss und Erholung auf rund 65.000 $; gestrichelte Linie beim Tief innerhalb der Stunde von rund 61.970 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 12 по 15 ноября 2026 года: падение примерно с $74 000 до около $62 600 на худшем часовом закрытии и отскок примерно до $65 000; пунктирная линия показывает внутричасовой минимум около $61 970",
            "tr": "Bitcoin'in 12-15 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 74.000 $'dan en kötü saatlik kapanışta yaklaşık 62.600 $'a düşüyor ve yaklaşık 65.000 $'a toparlanıyor; kesikli çizgi yaklaşık 61.970 $'lık saat içi dibi gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 12 hingga 15 November 2026: turun dari sekitar US$74.000 ke sekitar US$62.600 pada penutupan per jam terendah lalu pulih ke sekitar US$65.000, dengan garis putus-putus di titik terendah dalam satu jam sekitar US$61.970",
            "ja": "2026年11月12〜15日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約7万4000ドルから最も低い1時間終値の約6万2600ドルまで下落し、約6万5000ドルまで反発。破線は時間内安値（約6万1970ドル）",
            "ko": "2026년 11월 12~15일 크라켄 비트코인 시간별 가격 선 차트: 약 7만 4,000달러에서 가장 낮은 시간별 종가인 약 6만 2,600달러까지 하락한 뒤 약 6만 5,000달러로 반등, 점선은 시간 중 저점 약 6만 1,970달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $1.96 billion of leveraged crypto positions were liquidated in 24 hours, including about $750 million in bitcoin, $600.5 million of it from bets on higher prices", {
            "es": "Tarjeta: unos 1.960 millones de dólares en posiciones cripto apalancadas se liquidaron en 24 horas, de ellos unos 750 millones en bitcoin, 600,5 millones de apuestas alcistas",
            "pt": "Cartão: cerca de US$ 1,96 bilhão em posições alavancadas de cripto foram liquidadas em 24 horas, incluindo cerca de US$ 750 milhões em bitcoin, dos quais US$ 600,5 milhões em apostas na alta",
            "fr": "Encadré : environ 1,96 milliard de dollars de positions crypto à effet de levier ont été liquidées en 24 heures, dont environ 750 millions en bitcoin, parmi lesquels 600,5 millions de paris à la hausse",
            "de": "Faktenkarte: Rund 1,96 Mrd. $ an gehebelten Krypto-Positionen wurden in 24 Stunden liquidiert, davon rund 750 Mio. $ bei Bitcoin, 600,5 Mio. $ davon Wetten auf steigende Kurse",
            "ru": "Карточка: за 24 часа ликвидировано около $1,96 млрд позиций с плечом на криптовалютном рынке, из них около $750 млн в биткоине, в том числе $600,5 млн ставок на рост",
            "tr": "Kart: 24 saatte yaklaşık 1,96 milyar $'lık kaldıraçlı kripto pozisyonu tasfiye edildi; bunun yaklaşık 750 milyon $'ı bitcoin'de, 600,5 milyon $'ı yükseliş bahislerinden",
            "id": "Kartu fakta: sekitar US$1,96 miliar posisi kripto berleverage dilikuidasi dalam 24 jam, termasuk sekitar US$750 juta di bitcoin, US$600,5 juta di antaranya dari taruhan harga naik",
            "ja": "カード：24時間で約19億6000万ドルのレバレッジ付き暗号資産ポジションが清算され、うちビットコインが約7億5000万ドル、そのうち6億50万ドルが値上がりに賭けたポジション",
            "ko": "카드: 24시간 동안 약 19억 6,000만 달러 규모의 레버리지 암호화폐 포지션이 청산됐고, 이 중 비트코인이 약 7억 5,000만 달러, 그중 6억 50만 달러가 상승 베팅",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinGlass data via crypto.news")},
    ]


def build_coinone_breach():
    slug = "coinone-data-breach-support-contractor-passwords-nov-2026"
    d = OUT / slug
    tl = make_timeline_card(
        d / "timeline-coinone-breach",
        "Coinone support data breach (Korea time)",
        [
            ("Thu 4 a.m.", "Attacker accesses servers of MetaM, Coinone's support contractor", RED),
            ("Thu 9:20 a.m.", "MetaM reports the breach to Coinone", ORANGE),
            ("Next steps", "Attack IPs blocked, support moved to email, regulators notified", (96, 165, 250)),
            ("Sun 8 a.m.", "Coinone posts its public notice and apology", GREEN),
        ],
        footer="Coinone notice, Nov. 15, 2026",
        margin=170, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-coinone-11-data-types",
        label="Coinone support data breach",
        big="11 kinds of data",
        sub="may have leaked from support chats and calls, including passwords, national ID numbers, bank account numbers and wallet addresses.",
        footer="Coinone notice, Nov. 15, 2026 (Korea time)",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline in Korea time: Thursday 4 a.m., an attacker accesses servers of MetaM, Coinone's support contractor; Thursday 9:20 a.m., MetaM reports the breach to Coinone; next, attack IPs are blocked, support moves to email and regulators are notified; Sunday 8 a.m., Coinone posts its public notice and apology", {
            "es": "Cronología en hora de Corea: jueves 4:00, un atacante accede a los servidores de MetaM, la contratista de soporte de Coinone; jueves 9:20, MetaM informa de la brecha a Coinone; después, se bloquean las IP del ataque, el soporte pasa al correo electrónico y se avisa a los reguladores; domingo 8:00, Coinone publica su aviso y pide disculpas",
            "pt": "Linha do tempo no horário da Coreia: quinta, 4h, um invasor acessa os servidores da MetaM, terceirizada de atendimento da Coinone; quinta, 9h20, a MetaM informa o vazamento à Coinone; em seguida, os IPs do ataque são bloqueados, o atendimento passa para e-mail e os reguladores são avisados; domingo, 8h, a Coinone publica o aviso e pede desculpas",
            "fr": "Chronologie (heure de Corée) : jeudi 4 h, un attaquant accède aux serveurs de MetaM, le prestataire de support de Coinone ; jeudi 9 h 20, MetaM signale la fuite à Coinone ; ensuite, les adresses IP de l'attaque sont bloquées, le support passe par e-mail et les autorités sont prévenues ; dimanche 8 h, Coinone publie son avis et s'excuse",
            "de": "Zeitleiste (koreanische Zeit): Donnerstag 4 Uhr, ein Angreifer greift auf Server von MetaM zu, dem Support-Dienstleister von Coinone; Donnerstag 9:20 Uhr, MetaM meldet den Vorfall an Coinone; danach werden die Angriffs-IPs gesperrt, der Support läuft nur noch per E-Mail und Behörden werden informiert; Sonntag 8 Uhr, Coinone veröffentlicht seine Mitteilung und entschuldigt sich",
            "ru": "Хронология по корейскому времени: четверг, 4:00, злоумышленник получает доступ к серверам MetaM, подрядчика Coinone по поддержке клиентов; четверг, 9:20, MetaM сообщает Coinone об утечке; затем IP-адреса атаки блокируются, поддержка переводится на электронную почту, регуляторы уведомлены; воскресенье, 8:00, Coinone публикует уведомление и извинения",
            "tr": "Kore saatiyle zaman çizelgesi: perşembe 04.00, bir saldırgan Coinone'un destek yüklenicisi MetaM'in sunucularına erişiyor; perşembe 09.20, MetaM ihlali Coinone'a bildiriyor; ardından saldırı IP'leri engelleniyor, destek e-postaya taşınıyor ve düzenleyiciler bilgilendiriliyor; pazar 08.00, Coinone duyurusunu ve özrünü yayımlıyor",
            "id": "Linimasa waktu Korea: Kamis pukul 04.00, penyerang mengakses server MetaM, kontraktor layanan pelanggan Coinone; Kamis pukul 09.20, MetaM melaporkan kebocoran ke Coinone; selanjutnya IP penyerang diblokir, layanan dukungan dialihkan ke email, dan regulator diberi tahu; Minggu pukul 08.00, Coinone menerbitkan pemberitahuan dan permintaan maaf",
            "ja": "韓国時間のタイムライン：木曜午前4時、攻撃者がCoinoneの顧客対応委託先MetaMのサーバーにアクセス。木曜午前9時20分、MetaMがCoinoneに報告。その後、攻撃元IPを遮断し、サポートをメールに切り替え、当局に届け出。日曜午前8時、Coinoneが公式告知と謝罪を掲載",
            "ko": "한국 시간 기준 타임라인: 목요일 오전 4시, 공격자가 코인원의 고객상담 수탁사 메타엠 서버에 접근; 목요일 오전 9시 20분, 메타엠이 코인원에 유출 사실 보고; 이후 공격 IP 차단, 상담을 이메일로 전환, 관계 기관 신고; 일요일 오전 8시, 코인원이 공지와 사과문 게시",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Coinone notice")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: 11 kinds of personal data may have leaked from Coinone support chats and calls, including passwords, national ID numbers, bank account numbers and wallet addresses", {
            "es": "Tarjeta: 11 tipos de datos personales pueden haberse filtrado de los chats y llamadas de soporte de Coinone, entre ellos contraseñas, números de identidad nacional, cuentas bancarias y direcciones de billetera",
            "pt": "Cartão: 11 tipos de dados pessoais podem ter vazado de chats e ligações de atendimento da Coinone, incluindo senhas, números de identidade nacional, contas bancárias e endereços de carteira",
            "fr": "Encadré : 11 types de données personnelles ont pu fuiter des échanges avec le support de Coinone (chat et téléphone), dont des mots de passe, des numéros d'identité nationale, des numéros de compte bancaire et des adresses de portefeuille",
            "de": "Faktenkarte: 11 Arten persönlicher Daten könnten aus Support-Chats und Anrufen bei Coinone abgeflossen sein, darunter Passwörter, nationale Ausweisnummern, Kontonummern und Wallet-Adressen",
            "ru": "Карточка: из чатов и звонков в поддержку Coinone могли утечь 11 видов персональных данных, включая пароли, национальные идентификационные номера, номера банковских счетов и адреса кошельков",
            "tr": "Kart: Coinone destek sohbetleri ve aramalarından şifreler, ulusal kimlik numaraları, banka hesap numaraları ve cüzdan adresleri dahil 11 tür kişisel veri sızmış olabilir",
            "id": "Kartu fakta: 11 jenis data pribadi mungkin bocor dari chat dan panggilan layanan pelanggan Coinone, termasuk kata sandi, nomor identitas nasional, nomor rekening bank, dan alamat dompet",
            "ja": "カード：Coinoneのサポートのチャットや電話から、パスワード、住民登録番号、銀行口座番号、ウォレットアドレスなど11種類の個人情報が流出した可能性",
            "ko": "카드: 코인원 채팅·전화 상담 기록에서 비밀번호, 주민등록번호, 계좌번호, 지갑 주소 등 11가지 개인정보가 유출됐을 가능성",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Coinone notice, Nov. 15, 2026")},
    ]


def fetch_defillama_tvl(slug: str, end_ts: int):
    url = f"https://api.llama.fi/protocol/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    xs, ys = [], []
    for r in data["tvl"]:
        if int(r["date"]) <= end_ts:
            xs.append(float(r["date"]))
            ys.append(float(r["totalLiquidityUSD"]) / 1e6)
    return np.array(xs), np.array(ys)


def build_stusdt_wind_down():
    slug = "stusdt-wind-down-redeem-by-may-2027-nov-2026"
    d = OUT / slug
    # DefiLlama stUSDT TVL, July 2023 to Nov 15, 2026 18:00 UTC. Peak about $2.30B on Nov 22, 2023; about $8.4M on Nov 15, 2026.
    xs, ys = fetch_defillama_tvl("stusdt", 1794765600)
    chart = make_line_chart(
        d / "chart-stusdt-tvl-2023-2026",
        xs, ys,
        title="stUSDT total value locked, July 2023 to Nov. 15, 2026 (DefiLlama)",
        date_fmt="%b %Y",
        yfmt=lambda x, _p: f"${x:,.0f}M",
    )
    card = make_fact_card(
        d / "fact-stusdt-deadline-may-14-2027",
        label="stUSDT redemption deadline",
        big="May 14, 2027",
        sub="The official portal closes at 23:59 UTC. Later requests go through customer support in monthly batches through August 2027.",
        footer="stUSDT notice, Nov. 14, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of stUSDT's total value locked from July 2023 to Nov. 15, 2026: a rise to a peak of about $2.3 billion in November 2023, a steep fall during 2024, a flat stretch near $55 million to $65 million, and a final drop to about $8.4 million", {
            "es": "Gráfico de líneas del valor total bloqueado en stUSDT de julio de 2023 al 15 de noviembre de 2026: sube hasta un máximo de unos 2.300 millones de dólares en noviembre de 2023, cae con fuerza en 2024, se mantiene entre unos 55 y 65 millones y baja al final a unos 8,4 millones",
            "pt": "Gráfico de linha do valor total bloqueado no stUSDT de julho de 2023 a 15 de novembro de 2026: sobe até o pico de cerca de US$ 2,3 bilhões em novembro de 2023, cai forte em 2024, fica estável entre cerca de US$ 55 milhões e US$ 65 milhões e despenca no fim para cerca de US$ 8,4 milhões",
            "fr": "Courbe de la valeur totale verrouillée de stUSDT de juillet 2023 au 15 novembre 2026 : hausse jusqu'à un pic d'environ 2,3 milliards de dollars en novembre 2023, forte baisse en 2024, palier entre environ 55 et 65 millions, puis chute finale à environ 8,4 millions",
            "de": "Liniendiagramm des gesamten gebundenen Werts von stUSDT von Juli 2023 bis 15. November 2026: Anstieg auf einen Höchststand von rund 2,3 Mrd. $ im November 2023, starker Rückgang 2024, Seitwärtsphase bei rund 55 bis 65 Mio. $ und zuletzt ein Absturz auf rund 8,4 Mio. $",
            "ru": "Линейный график общей заблокированной стоимости stUSDT с июля 2023 года по 15 ноября 2026 года: рост до пика около $2,3 млрд в ноябре 2023 года, резкое падение в 2024 году, затем ровный участок около $55–65 млн и финальное снижение примерно до $8,4 млн",
            "tr": "stUSDT'nin Temmuz 2023'ten 15 Kasım 2026'ya kadar kilitli toplam değerinin çizgi grafiği: Kasım 2023'te yaklaşık 2,3 milyar $'lık zirveye çıkış, 2024'te sert düşüş, yaklaşık 55 ile 65 milyon $ arasında yatay seyir ve sonunda yaklaşık 8,4 milyon $'a düşüş",
            "id": "Grafik garis nilai total terkunci stUSDT dari Juli 2023 hingga 15 November 2026: naik ke puncak sekitar US$2,3 miliar pada November 2023, turun tajam sepanjang 2024, datar di kisaran US$55 juta hingga US$65 juta, lalu anjlok ke sekitar US$8,4 juta",
            "ja": "2023年7月〜2026年11月15日のstUSDTの預かり資産総額（TVL）の折れ線グラフ：2023年11月に約23億ドルのピーク、2024年に急減、その後は約5500万〜6500万ドルで横ばい、最後に約840万ドルまで減少",
            "ko": "2023년 7월부터 2026년 11월 15일까지 stUSDT 총예치금(TVL) 선 차트: 2023년 11월 약 23억 달러로 정점, 2024년 급감, 약 5,500만~6,500만 달러에서 횡보한 뒤 약 840만 달러로 감소",
         }),
         "caption": tr_map(CAPTION_CHART, src="DefiLlama stUSDT TVL")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the stUSDT redemption deadline is May 14, 2027; the official portal closes at 23:59 UTC, and later requests go through customer support in monthly batches through August 2027", {
            "es": "Tarjeta: el plazo para canjear stUSDT termina el 14 de mayo de 2027; el portal oficial cierra a las 23:59 UTC y las solicitudes posteriores se tramitan por soporte en lotes mensuales hasta agosto de 2027",
            "pt": "Cartão: o prazo para resgatar stUSDT termina em 14 de maio de 2027; o portal oficial fecha às 23h59 UTC e os pedidos posteriores passam pelo suporte em lotes mensais até agosto de 2027",
            "fr": "Encadré : la date limite de remboursement des stUSDT est le 14 mai 2027 ; le portail officiel ferme à 23 h 59 UTC, puis les demandes passent par le support et sont traitées par lots mensuels jusqu'en août 2027",
            "de": "Faktenkarte: Die Einlösefrist für stUSDT endet am 14. Mai 2027; das offizielle Portal schließt um 23:59 Uhr UTC, spätere Anträge laufen über den Kundensupport in monatlichen Sammelbearbeitungen bis August 2027",
            "ru": "Карточка: срок погашения stUSDT истекает 14 мая 2027 года; официальный портал закрывается в 23:59 UTC, а более поздние заявки принимает поддержка и обрабатывает ежемесячными пакетами до августа 2027 года",
            "tr": "Kart: stUSDT itfa son tarihi 14 Mayıs 2027; resmi portal 23.59 UTC'de kapanıyor, sonraki talepler Ağustos 2027'ye kadar müşteri desteği üzerinden aylık gruplar halinde işleniyor",
            "id": "Kartu fakta: batas waktu penukaran stUSDT adalah 14 Mei 2027; portal resmi ditutup pukul 23.59 UTC, dan permintaan setelahnya diproses lewat layanan pelanggan secara bertahap tiap bulan hingga Agustus 2027",
            "ja": "カード：stUSDTの償還期限は2027年5月14日。公式ポータルはUTC 23時59分に閉鎖され、その後の申請はカスタマーサポート経由で2027年8月まで毎月まとめて処理",
            "ko": "카드: stUSDT 상환 마감일은 2027년 5월 14일. 공식 포털은 UTC 23시 59분에 닫히고, 이후 요청은 고객지원을 통해 2027년 8월까지 매월 일괄 처리",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="stUSDT notice, Nov. 14, 2026")},
    ]


def fetch_mempool_hashrate(period="3m"):
    url = f"https://mempool.space/api/v1/mining/hashrate/{period}"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    xs = np.array([float(r["timestamp"]) for r in data["hashrates"]])
    ys = np.array([float(r["avgHashrate"]) / 1e18 for r in data["hashrates"]])
    return xs, ys


def build_luxor_hashrate_hijack():
    slug = "luxor-commander-hack-bitcoin-miners-hashrate-ocean-nov-2026"
    d = OUT / slug
    # mempool.space daily average network hashrate, Aug 17 to Nov 15, 2026 (about 926 EH/s on Nov 15).
    xs, ys = fetch_mempool_hashrate("3m")
    chart = make_line_chart(
        d / "chart-bitcoin-network-hashrate-3m",
        xs, ys,
        title="Bitcoin network hashrate, daily average, Aug. 17 to Nov. 15, 2026 (mempool.space)",
        date_fmt="%b %d",
        yfmt=lambda x, _p: f"{x:,.0f} EH/s",
    )
    card = make_fact_card(
        d / "fact-luxor-13-ehs-redirected",
        label="Mining hashrate hijack",
        big="About 13 EH/s",
        sub="of mining power was reportedly pointed at the OCEAN pool. Luxor says just over a dozen client accounts were hit and the flaw was patched within two hours.",
        footer="CoreX Hosting reports; Luxor statement, Nov. 15, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of the bitcoin network's daily average hashrate from Aug. 17 to Nov. 15, 2026, moving between roughly 780 and 1,230 exahashes per second and ending near 926 EH/s", {
            "es": "Gráfico de líneas del hashrate medio diario de la red de bitcoin del 17 de agosto al 15 de noviembre de 2026: oscila entre unos 780 y 1.230 exahashes por segundo y termina cerca de 926 EH/s",
            "pt": "Gráfico de linha do hashrate médio diário da rede bitcoin de 17 de agosto a 15 de novembro de 2026, variando entre cerca de 780 e 1.230 exahashes por segundo e terminando perto de 926 EH/s",
            "fr": "Courbe du hashrate moyen quotidien du réseau bitcoin du 17 août au 15 novembre 2026 : il évolue entre environ 780 et 1 230 exahashs par seconde et termine près de 926 EH/s",
            "de": "Liniendiagramm der täglichen durchschnittlichen Hashrate des Bitcoin-Netzwerks vom 17. August bis 15. November 2026: zwischen rund 780 und 1.230 Exahash pro Sekunde, zuletzt bei rund 926 EH/s",
            "ru": "Линейный график среднесуточного хешрейта сети биткоина с 17 августа по 15 ноября 2026 года: колебания примерно от 780 до 1230 эксахешей в секунду, в конце около 926 EH/s",
            "tr": "Bitcoin ağının 17 Ağustos ile 15 Kasım 2026 arasındaki günlük ortalama hash oranının çizgi grafiği: saniyede yaklaşık 780 ile 1.230 eksahash arasında değişiyor ve 926 EH/s civarında bitiyor",
            "id": "Grafik garis hashrate rata-rata harian jaringan bitcoin dari 17 Agustus hingga 15 November 2026, bergerak antara sekitar 780 dan 1.230 exahash per detik dan berakhir di dekat 926 EH/s",
            "ja": "2026年8月17日から11月15日までのビットコインネットワークの日次平均ハッシュレートの折れ線グラフ。毎秒約780〜1,230エクサハッシュの間で推移し、最後は約926 EH/s",
            "ko": "2026년 8월 17일부터 11월 15일까지 비트코인 네트워크 일평균 해시레이트 선 그래프. 초당 약 780~1,230엑사해시 사이에서 움직이다 약 926 EH/s로 마감",
         }),
         "caption": tr_map(CAPTION_CHART, src="mempool.space")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about 13 exahashes per second of mining power was reportedly pointed at the OCEAN pool; Luxor says just over a dozen client accounts were hit and the flaw was patched within two hours", {
            "es": "Tarjeta: unos 13 exahashes por segundo de potencia de minería se habrían desviado al pool OCEAN; Luxor dice que se vieron afectadas algo más de una docena de cuentas de clientes y que corrigió el fallo en menos de dos horas",
            "pt": "Cartão: cerca de 13 exahashes por segundo de poder de mineração teriam sido desviados para o pool OCEAN; a Luxor diz que pouco mais de uma dúzia de contas de clientes foram afetadas e que corrigiu a falha em até duas horas",
            "fr": "Encadré : environ 13 exahashs par seconde de puissance de minage auraient été redirigés vers le pool OCEAN ; Luxor indique qu'un peu plus d'une douzaine de comptes clients ont été touchés et que la faille a été corrigée en moins de deux heures",
            "de": "Faktenkarte: Rund 13 Exahash pro Sekunde an Mining-Leistung wurden Berichten zufolge auf den Pool OCEAN umgeleitet; Luxor zufolge waren gut ein Dutzend Kundenkonten betroffen, die Lücke wurde binnen zwei Stunden geschlossen",
            "ru": "Карточка: около 13 эксахешей в секунду майнинговой мощности, по сообщениям, перенаправили в пул OCEAN; Luxor говорит, что пострадали чуть больше десятка клиентских аккаунтов, а уязвимость закрыли в течение двух часов",
            "tr": "Kart: bildirildiğine göre saniyede yaklaşık 13 eksahashlik madencilik gücü OCEAN havuzuna yönlendirildi; Luxor bir düzineyi biraz aşan müşteri hesabının etkilendiğini ve açığın iki saat içinde kapatıldığını söylüyor",
            "id": "Kartu fakta: sekitar 13 exahash per detik daya penambangan dilaporkan dialihkan ke pool OCEAN; Luxor mengatakan sedikit lebih dari selusin akun klien terdampak dan celahnya ditambal dalam dua jam",
            "ja": "カード：約13 EH/sの採掘能力がOCEANプールに向けられたと報じられた。Luxorによると被害は十数件の顧客アカウントで、脆弱性は2時間以内に修正された",
            "ko": "카드: 약 13 EH/s의 채굴 연산력이 OCEAN 풀로 돌려진 것으로 알려짐. 룩소르는 피해 고객 계정이 십여 개이며 2시간 안에 취약점을 패치했다고 밝힘",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoreX Hosting via Bitcoin.com News; Luxor statement, Nov. 15, 2026")},
    ]


def build_germany_customs_crypto():
    slug = "germany-customs-crypto-seizure-100000-euros-bundestag-nov-2026"
    d = OUT / slug
    tl = make_timeline_card(
        d / "timeline-germany-customs-law",
        "Germany's customs asset-seizure law (ZFG)",
        [
            ("Aug. 12", "Federal cabinet approves the customs reform bill", (96, 165, 250)),
            ("Nov. 12", "Bundestag passes it; Left votes no, Greens abstain", ORANGE),
            ("Next", "Bundesrat sessions on Nov. 20 or Dec. 18; states must consent", RED),
            ("Jan. 1, 2027", "Planned start date, with some parts staged later", GREEN),
        ],
        footer="Bundestag, BMF, AltcoinReporter, Nov. 2026",
        margin=170, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-germany-180-days",
        label="German customs crypto seizure",
        big="Up to 180 days",
        sub="Customs could hold assets worth over €100,000 of doubtful origin for 30 days; a finance court can add 150 more. Final confiscation needs a court ruling.",
        footer="Bundestag bill (Drucksache 21/9136), Nov. 12, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Aug. 12, Germany's federal cabinet approves the customs reform bill; Nov. 12, the Bundestag passes it while the Left votes no and the Greens abstain; Nov. 20 and Dec. 18, the remaining 2026 Bundesrat sessions where the states must consent; Jan. 1, 2027, the planned start date, with some parts staged later", {
            "es": "Cronología: 12 de agosto, el gobierno federal alemán aprueba el proyecto de reforma aduanera; 12 de noviembre, el Bundestag lo aprueba con el voto en contra de La Izquierda y la abstención de Los Verdes; 20 de noviembre y 18 de diciembre, últimas sesiones del Bundesrat en 2026, donde los estados deben dar su visto bueno; 1 de enero de 2027, fecha prevista de entrada en vigor, con algunas partes más tarde",
            "pt": "Linha do tempo: 12 de agosto, o gabinete federal alemão aprova o projeto de reforma da alfândega; 12 de novembro, o Bundestag aprova o texto, com voto contra da Esquerda e abstenção dos Verdes; 20 de novembro e 18 de dezembro, últimas sessões do Bundesrat em 2026, em que os estados precisam dar aval; 1º de janeiro de 2027, data prevista de vigência, com algumas partes depois",
            "fr": "Chronologie : 12 août, le gouvernement fédéral allemand adopte le projet de réforme des douanes ; 12 novembre, le Bundestag le vote, Die Linke contre et les Verts abstenus ; 20 novembre et 18 décembre, dernières séances du Bundesrat en 2026, où les Länder doivent donner leur accord ; 1er janvier 2027, entrée en vigueur prévue, certaines parties plus tard",
            "de": "Zeitleiste: 12. August, das Bundeskabinett beschließt den Entwurf zur Zollreform; 12. November, der Bundestag verabschiedet ihn, Die Linke stimmt dagegen, die Grünen enthalten sich; 20. November und 18. Dezember, die letzten Bundesratssitzungen 2026, die Länder müssen zustimmen; 1. Januar 2027, geplantes Inkrafttreten, einzelne Teile später",
            "ru": "Хронология: 12 августа федеральное правительство Германии одобряет законопроект о реформе таможни; 12 ноября бундестаг принимает его, Левые против, Зелёные воздержались; 20 ноября и 18 декабря: последние заседания бундесрата в 2026 году, где земли должны дать согласие; 1 января 2027 года: планируемая дата вступления в силу, часть положений позже",
            "tr": "Zaman çizelgesi: 12 Ağustos, Almanya federal kabinesi gümrük reformu tasarısını onaylıyor; 12 Kasım, Federal Meclis tasarıyı kabul ediyor, Sol Parti hayır oyu veriyor, Yeşiller çekimser kalıyor; 20 Kasım ve 18 Aralık, eyaletlerin onay vermesi gereken 2026'daki son Federal Konsey oturumları; 1 Ocak 2027, bazı bölümleri daha sonra olmak üzere planlanan yürürlük tarihi",
            "id": "Linimasa: 12 Agustus, kabinet federal Jerman menyetujui RUU reformasi bea cukai; 12 November, Bundestag mengesahkannya, partai Kiri menolak dan Partai Hijau abstain; 20 November dan 18 Desember, sidang terakhir Bundesrat pada 2026 tempat negara bagian harus memberi persetujuan; 1 Januari 2027, tanggal mulai berlaku yang direncanakan, dengan beberapa bagian menyusul",
            "ja": "タイムライン：8月12日、ドイツ連邦政府が税関改革法案を閣議決定。11月12日、連邦議会が可決（左翼党は反対、緑の党は棄権）。11月20日と12月18日、州の同意が必要な連邦参議院の2026年最後の会期。2027年1月1日、施行予定日（一部は後から施行）",
            "ko": "타임라인: 8월 12일, 독일 연방 내각이 세관 개혁 법안 의결; 11월 12일, 연방하원 통과(좌파당 반대, 녹색당 기권); 11월 20일과 12월 18일, 주 정부 동의가 필요한 연방참사원의 2026년 마지막 회의; 2027년 1월 1일, 시행 예정일(일부 조항은 이후 시행)",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bundestag, German Finance Ministry, AltcoinReporter")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: German customs could hold assets worth over 100,000 euros of doubtful origin for 30 days, and a finance court can add 150 more, up to 180 days; final confiscation needs a court ruling", {
            "es": "Tarjeta: la aduana alemana podría retener durante 30 días bienes de más de 100.000 euros de origen dudoso, y un tribunal financiero puede sumar otros 150, hasta 180 días; el decomiso definitivo requiere una resolución judicial",
            "pt": "Cartão: a alfândega alemã poderia reter por 30 dias bens de mais de 100 mil euros de origem duvidosa, e um tribunal financeiro pode somar mais 150, até 180 dias; o confisco definitivo exige decisão judicial",
            "fr": "Encadré : la douane allemande pourrait retenir pendant 30 jours des avoirs de plus de 100 000 euros d'origine douteuse, et un tribunal des finances peut ajouter 150 jours, soit jusqu'à 180 jours ; la confiscation définitive exige une décision de justice",
            "de": "Faktenkarte: Der Zoll könnte Vermögen über 100.000 Euro mit zweifelhafter Herkunft 30 Tage sicherstellen, ein Finanzgericht kann 150 Tage anhängen, insgesamt bis zu 180 Tage; die endgültige Einziehung braucht ein Gerichtsurteil",
            "ru": "Карточка: таможня Германии сможет удерживать активы дороже 100 000 евро сомнительного происхождения 30 дней, а финансовый суд может продлить срок ещё на 150 дней, всего до 180 дней; окончательная конфискация требует решения суда",
            "tr": "Kart: Alman gümrüğü kaynağı şüpheli, 100.000 eurodan değerli varlıkları 30 gün tutabilecek; bir maliye mahkemesi bu süreye 150 gün ekleyebilir, toplam 180 güne kadar; kalıcı el koyma için mahkeme kararı gerekiyor",
            "id": "Kartu fakta: bea cukai Jerman dapat menahan aset bernilai lebih dari 100.000 euro yang asal-usulnya diragukan selama 30 hari, dan pengadilan keuangan dapat menambah 150 hari, hingga total 180 hari; penyitaan permanen memerlukan putusan pengadilan",
            "ja": "カード：ドイツ税関は出所が疑わしい10万ユーロ超の資産を30日間差し押さえられ、財政裁判所はさらに150日延長でき、最長180日。最終的な没収には裁判所の判断が必要",
            "ko": "카드: 독일 세관은 출처가 의심스러운 10만 유로 초과 자산을 30일간 압류할 수 있고, 재정법원이 150일을 연장할 수 있어 최대 180일. 최종 몰수에는 법원 판결이 필요",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bundestag bill (Drucksache 21/9136), Nov. 12, 2026")},
    ]



def build_strategy_485_btc():
    slug = "strategy-buys-485-bitcoin-strive-251-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD daily closes, Aug 18 - Nov 15, 2026 (90 days). Peak close $86,593.8 (Sep 21), $65,314.6 on Nov 15.
    # Strategy average cost $75,452 per BTC (Form 8-K, Nov 16, 2026).
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since=1786924800"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = next(v for k, v in data["result"].items() if k != "last")
    rows = [r for r in rows if 1787011200 <= int(r[0]) < 1794787200]
    xs = np.array([float(r[0]) for r in rows]); ys = np.array([float(r[4]) for r in rows])
    chart = make_line_chart(
        d / "chart-btc-vs-strategy-cost",
        xs, ys,
        title="Bitcoin daily close vs. Strategy's average cost, Aug. 18 - Nov. 15, 2026",
        hline=75452,
        hlabel="Strategy average cost: $75,452 per BTC",
    )
    card = make_fact_card(
        d / "fact-strategy-850849-btc",
        label="Strategy bitcoin holdings",
        big="850,849 BTC",
        sub="bought for $64.20 billion, an average of $75,452 per coin. Last week's 485 BTC cost $68,887 each.",
        footer="Strategy Form 8-K, Nov. 16, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's daily closing price on Kraken from Aug. 18 to Nov. 15, 2026: about $64,700 in mid-August, a peak close of about $86,600 on Sep. 21, then a slide to about $64,100 on Nov. 14 and $65,300 on Nov. 15, now below a dashed line at Strategy's average cost of $75,452 per bitcoin", {
            "es": "Gráfico de líneas del precio de cierre diario de bitcoin en Kraken del 18 de agosto al 15 de noviembre de 2026: unos 64.700 dólares a mediados de agosto, un cierre máximo de unos 86.600 dólares el 21 de septiembre y luego una caída a unos 64.100 dólares el 14 de noviembre y 65.300 el 15 de noviembre, por debajo de la línea discontinua del costo medio de Strategy, 75.452 dólares por bitcoin",
            "pt": "Gráfico de linha do preço de fechamento diário do bitcoin na Kraken de 18 de agosto a 15 de novembro de 2026: cerca de US$ 64.700 em meados de agosto, fechamento máximo de cerca de US$ 86.600 em 21 de setembro e depois queda para cerca de US$ 64.100 em 14 de novembro e US$ 65.300 em 15 de novembro, abaixo da linha tracejada do custo médio da Strategy, US$ 75.452 por bitcoin",
            "fr": "Courbe du cours de clôture quotidien du bitcoin sur Kraken du 18 août au 15 novembre 2026 : environ 64 700 dollars mi-août, une clôture record d'environ 86 600 dollars le 21 septembre, puis une baisse à environ 64 100 dollars le 14 novembre et 65 300 dollars le 15 novembre, sous la ligne pointillée du coût moyen de Strategy, 75 452 dollars par bitcoin",
            "de": "Liniendiagramm des täglichen Bitcoin-Schlusskurses bei Kraken vom 18. August bis 15. November 2026: rund 64.700 $ Mitte August, Höchstschlusskurs von rund 86.600 $ am 21. September, danach Rückgang auf rund 64.100 $ am 14. November und 65.300 $ am 15. November, unter der gestrichelten Linie beim durchschnittlichen Einstandspreis von Strategy von 75.452 $ je Bitcoin",
            "ru": "Линейный график дневных цен закрытия биткоина на Kraken с 18 августа по 15 ноября 2026 года: около $64 700 в середине августа, максимальное закрытие около $86 600 21 сентября, затем снижение примерно до $64 100 14 ноября и $65 300 15 ноября, ниже пунктирной линии средней цены покупки Strategy, $75 452 за биткоин",
            "tr": "Bitcoin'in 18 Ağustos - 15 Kasım 2026 arasında Kraken'deki günlük kapanış fiyatının çizgi grafiği: ağustos ortasında yaklaşık 64.700 $, 21 Eylül'de yaklaşık 86.600 $ ile en yüksek kapanış, ardından 14 Kasım'da yaklaşık 64.100 $'a ve 15 Kasım'da 65.300 $'a düşüş; fiyat, Strategy'nin bitcoin başına 75.452 $'lık ortalama maliyetini gösteren kesikli çizginin altında",
            "id": "Grafik garis harga penutupan harian bitcoin di Kraken dari 18 Agustus hingga 15 November 2026: sekitar US$64.700 pada pertengahan Agustus, penutupan tertinggi sekitar US$86.600 pada 21 September, lalu turun ke sekitar US$64.100 pada 14 November dan US$65.300 pada 15 November, di bawah garis putus-putus biaya rata-rata Strategy sebesar US$75.452 per bitcoin",
            "ja": "2026年8月18日〜11月15日のKrakenにおけるビットコイン日次終値の折れ線グラフ：8月中旬は約6万4700ドル、9月21日に約8万6600ドルの最高終値を付けた後、11月14日に約6万4100ドル、11月15日に約6万5300ドルまで下落し、ストラテジーの平均取得単価7万5452ドル（破線）を下回っている",
            "ko": "2026년 8월 18일~11월 15일 크라켄 비트코인 일일 종가 선 차트: 8월 중순 약 64,700달러, 9월 21일 약 86,600달러로 최고 종가를 기록한 뒤 11월 14일 약 64,100달러, 11월 15일 65,300달러로 하락해 스트래티지의 평균 매입 단가 75,452달러(점선)를 밑돌고 있다",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD daily closes; Strategy Form 8-K")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Strategy holds 850,849 bitcoin, bought for $64.20 billion at an average of $75,452 per coin; last week's 485 bitcoin cost $68,887 each", {
            "es": "Tarjeta: Strategy tiene 850.849 bitcoins, comprados por 64.200 millones de dólares a un promedio de 75.452 dólares por moneda; los 485 bitcoins de la semana pasada costaron 68.887 dólares cada uno",
            "pt": "Cartão: a Strategy detém 850.849 bitcoins, comprados por US$ 64,20 bilhões a uma média de US$ 75.452 por moeda; os 485 bitcoins da semana passada custaram US$ 68.887 cada",
            "fr": "Encadré : Strategy détient 850 849 bitcoins, achetés 64,20 milliards de dollars, soit en moyenne 75 452 dollars pièce ; les 485 bitcoins de la semaine dernière ont coûté 68 887 dollars chacun",
            "de": "Faktenkarte: Strategy hält 850.849 Bitcoin, gekauft für 64,20 Mrd. $ zu durchschnittlich 75.452 $ je Coin; die 485 Bitcoin der vergangenen Woche kosteten je 68.887 $",
            "ru": "Карточка: у Strategy 850 849 биткоинов, купленных за $64,20 млрд по средней цене $75 452 за монету; 485 биткоинов прошлой недели обошлись по $68 887 за штуку",
            "tr": "Kart: Strategy'nin elinde 64,20 milyar $'a, coin başına ortalama 75.452 $'dan alınmış 850.849 bitcoin var; geçen haftaki 485 bitcoin'in her biri 68.887 $'a mal oldu",
            "id": "Kartu fakta: Strategy memegang 850.849 bitcoin yang dibeli seharga US$64,20 miliar dengan rata-rata US$75.452 per koin; 485 bitcoin pekan lalu dibeli masing-masing US$68.887",
            "ja": "カード：ストラテジーの保有量は850,849BTC。取得総額は642億ドル、平均取得単価は1枚7万5452ドル。先週買い増した485BTCは1枚6万8887ドル",
            "ko": "카드: 스트래티지는 비트코인 850,849개를 보유, 총 매입액 642억 달러, 평균 단가 개당 75,452달러; 지난주 매입한 485개는 개당 68,887달러",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Strategy Form 8-K, Nov. 16, 2026")},
    ]


def fetch_fear_greed(start_ts: int, end_ts: int):
    url = "https://api.alternative.me/fng/?limit=0"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())["data"]
    pts = sorted((int(r["timestamp"]), int(r["value"])) for r in data if start_ts <= int(r["timestamp"]) <= end_ts)
    return np.array([float(t) for t, _ in pts]), np.array([float(v) for _, v in pts])


def build_fear_greed_10():
    slug = "crypto-fear-greed-index-10-extreme-fear-nov-2026"
    d = OUT / slug
    # Alternative.me Crypto Fear & Greed Index, daily, Jan 1 - Nov 16, 2026. Jan 1: 20; low 5 (Feb 12, Feb 23);
    # high 78 (Sep 22); 9 on June 10; 10 on Nov 15 and 16. "Extreme Fear" = 25 or lower.
    xs, ys = fetch_fear_greed(1767225600, 1794787200)
    chart = make_line_chart(
        d / "chart-fear-greed-2026",
        xs, ys,
        title="Crypto Fear & Greed Index, Jan. 1 - Nov. 16, 2026 (Alternative.me)",
        hline=25,
        hlabel="Extreme fear: 25 and below",
        ylabel="",
        date_fmt="%b",
        yfmt=lambda x, _p: f"{x:.0f}",
    )
    card = make_fact_card(
        d / "fact-fear-greed-10",
        label="Crypto Fear & Greed Index",
        big="10 / 100",
        sub="Extreme fear on Nov. 15 and 16, 2026, the lowest reading since June 10. A week earlier: 29. A month earlier: 55.",
        footer="Alternative.me Crypto Fear & Greed Index",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of the Crypto Fear & Greed Index from Jan. 1 to Nov. 16, 2026: long stretches in extreme fear from February to April with lows of 5, another dip to 9 in June, a peak of 78 on Sep. 22, and a fall back to 10 in mid-November, with a dashed line at 25 marking the extreme fear zone", {
            "es": "Gráfico de líneas del índice Crypto Fear & Greed del 1 de enero al 16 de noviembre de 2026: largos periodos de miedo extremo de febrero a abril con mínimos de 5, otra caída a 9 en junio, un máximo de 78 el 22 de septiembre y una vuelta a 10 a mediados de noviembre; la línea discontinua en 25 marca la zona de miedo extremo",
            "pt": "Gráfico de linha do índice Crypto Fear & Greed de 1º de janeiro a 16 de novembro de 2026: longos períodos de medo extremo de fevereiro a abril com mínimas de 5, nova queda a 9 em junho, pico de 78 em 22 de setembro e volta a 10 em meados de novembro; a linha tracejada em 25 marca a zona de medo extremo",
            "fr": "Courbe de l'indice Crypto Fear & Greed du 1er janvier au 16 novembre 2026 : de longues périodes de peur extrême de février à avril avec des plus bas à 5, un nouveau creux à 9 en juin, un pic à 78 le 22 septembre, puis un retour à 10 mi-novembre ; la ligne pointillée à 25 marque la zone de peur extrême",
            "de": "Liniendiagramm des Crypto Fear & Greed Index vom 1. Januar bis 16. November 2026: lange Phasen extremer Angst von Februar bis April mit Tiefs bei 5, ein weiterer Rückgang auf 9 im Juni, ein Hoch von 78 am 22. September und ein Rückfall auf 10 Mitte November; die gestrichelte Linie bei 25 markiert die Zone extremer Angst",
            "ru": "Линейный график индекса Crypto Fear & Greed с 1 января по 16 ноября 2026 года: длительные периоды крайнего страха с февраля по апрель с минимумами на уровне 5, ещё одно падение до 9 в июне, пик 78 22 сентября и возврат к 10 в середине ноября; пунктирная линия на уровне 25 отмечает зону крайнего страха",
            "tr": "Crypto Fear & Greed Endeksi'nin 1 Ocak - 16 Kasım 2026 çizgi grafiği: şubattan nisana kadar 5'e varan diplerle uzun aşırı korku dönemleri, haziranda 9'a bir düşüş daha, 22 Eylül'de 78 ile zirve ve kasım ortasında yeniden 10; 25'teki kesikli çizgi aşırı korku bölgesini gösteriyor",
            "id": "Grafik garis Crypto Fear & Greed Index dari 1 Januari hingga 16 November 2026: periode panjang ketakutan ekstrem dari Februari hingga April dengan titik terendah 5, turun lagi ke 9 pada Juni, puncak 78 pada 22 September, lalu kembali ke 10 pada pertengahan November; garis putus-putus di 25 menandai zona ketakutan ekstrem",
            "ja": "2026年1月1日〜11月16日の暗号資産Fear & Greed指数の折れ線グラフ：2〜4月に最低5まで下がる「極度の恐怖」が長く続き、6月にも9まで低下、9月22日に78のピークを付けた後、11月中旬に再び10へ。破線（25）は「極度の恐怖」ゾーンの境目",
            "ko": "2026년 1월 1일~11월 16일 암호화폐 공포·탐욕 지수 선 차트: 2~4월 최저 5까지 떨어진 '극단적 공포' 구간이 길게 이어지고, 6월에도 9까지 하락, 9월 22일 78로 정점을 찍은 뒤 11월 중순 다시 10으로 하락. 25의 점선은 극단적 공포 구간을 표시",
         }),
         "caption": tr_map(CAPTION_CHART, src="Alternative.me Crypto Fear & Greed Index")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the Crypto Fear & Greed Index read 10 out of 100, extreme fear, on Nov. 15 and 16, 2026, its lowest reading since June 10; a week earlier it was 29 and a month earlier 55", {
            "es": "Tarjeta: el índice Crypto Fear & Greed marcó 10 de 100, miedo extremo, el 15 y el 16 de noviembre de 2026, su nivel más bajo desde el 10 de junio; una semana antes estaba en 29 y un mes antes en 55",
            "pt": "Cartão: o índice Crypto Fear & Greed marcou 10 de 100, medo extremo, em 15 e 16 de novembro de 2026, o nível mais baixo desde 10 de junho; uma semana antes estava em 29 e um mês antes em 55",
            "fr": "Encadré : l'indice Crypto Fear & Greed affichait 10 sur 100, peur extrême, les 15 et 16 novembre 2026, son plus bas niveau depuis le 10 juin ; une semaine plus tôt il était à 29, un mois plus tôt à 55",
            "de": "Faktenkarte: Der Crypto Fear & Greed Index stand am 15. und 16. November 2026 bei 10 von 100, extreme Angst, der tiefste Wert seit dem 10. Juni; eine Woche zuvor lag er bei 29, einen Monat zuvor bei 55",
            "ru": "Карточка: индекс Crypto Fear & Greed 15 и 16 ноября 2026 года показал 10 из 100, крайний страх, минимум с 10 июня; неделей ранее он был на уровне 29, месяцем ранее 55",
            "tr": "Kart: Crypto Fear & Greed Endeksi 15 ve 16 Kasım 2026'da 100 üzerinden 10 ile aşırı korku gösterdi, 10 Haziran'dan beri en düşük seviye; bir hafta önce 29, bir ay önce 55'ti",
            "id": "Kartu fakta: Crypto Fear & Greed Index berada di 10 dari 100, ketakutan ekstrem, pada 15 dan 16 November 2026, angka terendah sejak 10 Juni; sepekan sebelumnya 29 dan sebulan sebelumnya 55",
            "ja": "カード：暗号資産Fear & Greed指数は2026年11月15日と16日に100点中10の「極度の恐怖」。6月10日以来の低さで、1週間前は29、1カ月前は55",
            "ko": "카드: 암호화폐 공포·탐욕 지수는 2026년 11월 15일과 16일 100점 만점에 10으로 '극단적 공포', 6월 10일 이후 최저. 일주일 전 29, 한 달 전 55",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Alternative.me Crypto Fear & Greed Index, Nov. 16, 2026")},
    ]



def fetch_coingecko_range(coin: str, start_ts: int, end_ts: int):
    import urllib.request
    url = (f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart/range"
           f"?vs_currency=usd&from={start_ts}&to={end_ts}")
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    pts = data["prices"]
    return [p[0] / 1000 for p in pts], [p[1] for p in pts]


def build_chainflip_drain():
    slug = "chainflip-vault-drained-4-86-million-flip-falls-nov-2026"
    d = OUT / slug
    # CoinGecko FLIP/USD hourly prices, Nov 20 12:00 UTC to Nov 21 19:00 UTC: about $0.483 at 07:00 UTC Nov 21,
    # $0.4728 at 09:00, $0.3242 at 10:00, low $0.2886 at 11:00 UTC, about $0.353 at 19:00 UTC.
    xs, ys = fetch_coingecko_range("chainflip", 1795176000, 1795287600)
    chart = make_line_chart(
        d / "chart-flip-hourly-nov-20-21",
        xs, ys,
        title="Chainflip (FLIP) hourly price, Nov. 20-21, 2026 (CoinGecko, UTC)",
        hline=0.483,
        hlabel="Before the drain ≈ $0.48",
        date_fmt="%b %d %H:%M",
        yfmt=lambda x, _p: f"${x:.3f}",
    )
    tl = make_timeline_card(
        d / "timeline-chainflip-vault-drain",
        "Chainflip vault drain, Nov. 21 (U.S. Central time)",
        [
            ("1:10 a.m.", "One signed transaction moves 520.22 ETH, 3.25M USDC and 758,141 USDT out of the Ethereum vault", (248, 113, 113)),
            ("by 1:19 a.m.", "Stablecoins swapped to ETH; nearly all of it sent into Tornado Cash", (248, 113, 113)),
            ("3:14 a.m.", "Chainflip turns on full safe mode: deposits, withdrawals, swaps and quotes off", ORANGE),
            ("3-5 a.m.", "FLIP falls from about $0.48 to about $0.29 (CoinGecko hourly data)", (96, 165, 250)),
        ],
        footer="Ethereum block 26,461,896 · CoinDesk · The Block · Chainflip on X",
        margin=170, wrap_w=250,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of Chainflip's FLIP token hourly price from Nov. 20 to Nov. 21, 2026: steady near $0.48, then a sharp drop on the morning of Nov. 21 to about $0.29 and a partial rebound to about $0.35 by 19:00 UTC", {
            "es": "Gráfico de líneas del precio horario del token FLIP de Chainflip del 20 al 21 de noviembre de 2026: estable cerca de 0,48 dólares, luego una fuerte caída en la mañana del 21 de noviembre hasta unos 0,29 dólares y un rebote parcial hasta unos 0,35 a las 19:00 UTC",
            "pt": "Gráfico de linha do preço horário do token FLIP da Chainflip de 20 a 21 de novembro de 2026: estável perto de US$ 0,48, depois uma queda forte na manhã de 21 de novembro para cerca de US$ 0,29 e uma recuperação parcial para cerca de US$ 0,35 às 19h UTC",
            "fr": "Courbe du cours horaire du jeton FLIP de Chainflip du 20 au 21 novembre 2026 : stable vers 0,48 dollar, puis une forte chute le matin du 21 novembre jusqu'à environ 0,29 dollar et un rebond partiel vers 0,35 dollar à 19 h UTC",
            "de": "Liniendiagramm des stündlichen Kurses des Chainflip-Tokens FLIP vom 20. bis 21. November 2026: stabil bei rund 0,48 $, dann am Morgen des 21. November ein starker Rückgang auf rund 0,29 $ und eine teilweise Erholung auf rund 0,35 $ bis 19:00 UTC",
            "ru": "Линейный график почасовой цены токена FLIP проекта Chainflip 20 и 21 ноября 2026 года: около $0,48, затем утром 21 ноября резкое падение примерно до $0,29 и частичный отскок примерно до $0,35 к 19:00 UTC",
            "tr": "Chainflip'in FLIP tokeninin 20-21 Kasım 2026 saatlik fiyatının çizgi grafiği: 0,48 $ civarında yatay, ardından 21 Kasım sabahı yaklaşık 0,29 $'a sert düşüş ve 19.00 UTC'ye kadar yaklaşık 0,35 $'a kısmi toparlanma",
            "id": "Grafik garis harga token FLIP milik Chainflip per jam pada 20 hingga 21 November 2026: stabil di sekitar US$0,48, lalu turun tajam pada pagi 21 November ke sekitar US$0,29 dan pulih sebagian ke sekitar US$0,35 pada 19.00 UTC",
            "ja": "2026年11月20〜21日のChainflipのトークンFLIPの1時間足の折れ線グラフ：約0.48ドルで安定した後、11月21日朝に約0.29ドルまで急落し、UTC19時までに約0.35ドルまで一部回復",
            "ko": "2026년 11월 20~21일 체인플립 FLIP 토큰 시간별 가격 선 차트: 약 0.48달러에서 안정적이다가 11월 21일 오전 약 0.29달러까지 급락한 뒤 UTC 19시까지 약 0.35달러로 일부 반등",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinGecko FLIP/USD hourly prices")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline in U.S. Central time, Nov. 21: 1:10 a.m., one signed transaction moves 520.22 ETH, 3.25 million USDC and 758,141 USDT out of Chainflip's Ethereum vault; by 1:19 a.m., the stablecoins are swapped to ETH and nearly all of it is sent into Tornado Cash; 3:14 a.m., Chainflip turns on full safe mode; 3 to 5 a.m., FLIP falls from about $0.48 to about $0.29", {
            "es": "Cronología en hora central de EE. UU., 21 de noviembre: 1:10, una transacción firmada saca 520,22 ETH, 3,25 millones de USDC y 758.141 USDT de la bóveda de Ethereum de Chainflip; hacia la 1:19, las stablecoins se cambian por ETH y casi todo se envía a Tornado Cash; 3:14, Chainflip activa el modo seguro total; de 3 a 5, FLIP cae de unos 0,48 a unos 0,29 dólares",
            "pt": "Linha do tempo no horário central dos EUA, 21 de novembro: 1h10, uma transação assinada tira 520,22 ETH, 3,25 milhões de USDC e 758.141 USDT do cofre da Chainflip no Ethereum; até 1h19, as stablecoins são trocadas por ETH e quase tudo vai para o Tornado Cash; 3h14, a Chainflip ativa o modo de segurança total; das 3h às 5h, o FLIP cai de cerca de US$ 0,48 para cerca de US$ 0,29",
            "fr": "Chronologie (heure du Centre des États-Unis), 21 novembre : 1 h 10, une transaction signée sort 520,22 ETH, 3,25 millions d'USDC et 758 141 USDT du coffre Ethereum de Chainflip ; vers 1 h 19, les stablecoins sont convertis en ETH et presque tout part vers Tornado Cash ; 3 h 14, Chainflip active le mode de sécurité complet ; de 3 h à 5 h, le FLIP passe d'environ 0,48 à environ 0,29 dollar",
            "de": "Zeitleiste (US-Central-Zeit), 21. November: 1:10 Uhr, eine signierte Transaktion holt 520,22 ETH, 3,25 Mio. USDC und 758.141 USDT aus dem Ethereum-Tresor von Chainflip; bis 1:19 Uhr werden die Stablecoins in ETH getauscht und fast alles an Tornado Cash geschickt; 3:14 Uhr, Chainflip schaltet den vollen Sicherheitsmodus ein; 3 bis 5 Uhr, FLIP fällt von rund 0,48 $ auf rund 0,29 $",
            "ru": "Хронология по центральному времени США, 21 ноября: 1:10, одна подписанная транзакция выводит 520,22 ETH, 3,25 млн USDC и 758 141 USDT из хранилища Chainflip в сети Ethereum; к 1:19 стейблкоины обменяны на ETH, и почти всё отправлено в Tornado Cash; 3:14, Chainflip включает полный безопасный режим; с 3 до 5 утра FLIP падает примерно с $0,48 до около $0,29",
            "tr": "ABD Merkezi saatiyle zaman çizelgesi, 21 Kasım: 01.10'da tek bir imzalı işlem Chainflip'in Ethereum kasasından 520,22 ETH, 3,25 milyon USDC ve 758.141 USDT çıkarıyor; 01.19'a kadar stablecoin'ler ETH'ye çevrilip neredeyse tamamı Tornado Cash'e gönderiliyor; 03.14'te Chainflip tam güvenli modu açıyor; 03.00-05.00 arasında FLIP yaklaşık 0,48 $'dan yaklaşık 0,29 $'a düşüyor",
            "id": "Linimasa waktu Central AS, 21 November: 01.10, satu transaksi bertanda tangan memindahkan 520,22 ETH, 3,25 juta USDC, dan 758.141 USDT keluar dari brankas Ethereum Chainflip; sebelum 01.19, stablecoin ditukar ke ETH dan hampir semuanya dikirim ke Tornado Cash; 03.14, Chainflip menyalakan mode aman penuh; pukul 03.00 hingga 05.00, FLIP turun dari sekitar US$0,48 ke sekitar US$0,29",
            "ja": "時系列（米中部時間、11月21日）：午前1時10分、署名済みの1件の取引でChainflipのイーサリアム金庫から520.22 ETH、325万USDC、75万8141 USDTが流出。午前1時19分までにステーブルコインをETHに交換し、ほぼ全額をTornado Cashへ。午前3時14分、Chainflipが完全セーフモードを発動。午前3〜5時、FLIPは約0.48ドルから約0.29ドルに下落",
            "ko": "타임라인(미국 중부시간, 11월 21일): 오전 1시 10분 서명된 거래 한 건으로 체인플립 이더리움 금고에서 520.22 ETH, 325만 USDC, 75만 8,141 USDT 유출, 오전 1시 19분까지 스테이블코인을 ETH로 바꿔 거의 전부 토네이도 캐시로 전송, 오전 3시 14분 체인플립이 전체 안전 모드 가동, 오전 3~5시 FLIP이 약 0.48달러에서 약 0.29달러로 하락",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Ethereum blockchain data (Blockscout); CoinDesk; The Block; Chainflip on X; CoinGecko")},
    ]


def build_lighter_api_key():
    slug = "lighter-dex-10-4-million-leaked-api-key-nov-2026"
    d = OUT / slug
    # CoinGecko LIT/USD 5-minute prices, Nov 16 00:00-19:00 UTC: about $2.83 at 00:00, about $2.75 at 10:00, low about $2.49 at 10:45 UTC, about $2.70 at 19:00.
    xs, ys = fetch_coingecko_range("lighter", 1794787200, 1794855600)
    chart = make_line_chart(
        d / "chart-lit-price-nov-16",
        xs, ys,
        title="Lighter (LIT) price, Nov. 16, 2026 (CoinGecko, 5-minute data, UTC)",
        hline=min(ys),
        hlabel=f"Low ≈ ${min(ys):.2f} at 10:45 UTC (CoinGecko)",
        date_fmt="%H:%M",
        yfmt=lambda x, _p: f"${x:.2f}",
    )
    tl = make_timeline_card(
        d / "timeline-lighter-incident",
        "Lighter incident, Nov. 16 (U.S. Central time)",
        [
            ("4:11 a.m.", "About 10.39M USDC leaves Lighter and is swapped to ETH within minutes", (248, 113, 113)),
            ("5:02 a.m.", "Lighter suspends all withdrawals and pool creation", ORANGE),
            ("6:49 a.m.", "Lighter blames a trader's leaked API key; Guardian mode on", ORANGE),
            ("12:21 p.m.", "About 5M USDC returned to the trader; withdrawals back to normal", (74, 222, 128)),
        ],
        footer="Bitquery · Lighter on X",
        margin=170, wrap_w=250,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of Lighter's LIT token price on CoinGecko on Nov. 16, 2026 (UTC): about $2.83 at midnight, drifting to about $2.75 by 10:00, a sharp drop to a low of about $2.49 at 10:45 after the incident, and a recovery to about $2.70 by 19:00", {
            "es": "Gráfico de líneas del precio del token LIT de Lighter en CoinGecko el 16 de noviembre de 2026 (UTC): unos 2,83 dólares a medianoche, bajada hasta unos 2,75 a las 10:00, caída brusca hasta un mínimo de unos 2,49 a las 10:45 tras el incidente y recuperación hasta unos 2,70 a las 19:00",
            "pt": "Gráfico de linha do preço do token LIT da Lighter na CoinGecko em 16 de novembro de 2026 (UTC): cerca de US$ 2,83 à meia-noite, recuo para cerca de US$ 2,75 às 10h00, queda brusca até a mínima de cerca de US$ 2,49 às 10h45 após o incidente e recuperação para cerca de US$ 2,70 às 19h00",
            "fr": "Courbe du cours du jeton LIT de Lighter sur CoinGecko le 16 novembre 2026 (UTC) : environ 2,83 dollars à minuit, environ 2,75 à 10 h 00, une chute brutale jusqu'à un plus bas d'environ 2,49 à 10 h 45 après l'incident, puis une remontée vers 2,70 à 19 h 00",
            "de": "Liniendiagramm des Kurses des Lighter-Tokens LIT bei CoinGecko am 16. November 2026 (UTC): rund 2,83 $ um Mitternacht, rund 2,75 $ um 10:00 Uhr, nach dem Vorfall ein scharfer Einbruch auf ein Tief von rund 2,49 $ um 10:45 Uhr und eine Erholung auf rund 2,70 $ bis 19:00 Uhr",
            "ru": "Линейный график цены токена LIT биржи Lighter по данным CoinGecko 16 ноября 2026 года (UTC): около $2,83 в полночь, около $2,75 к 10:00, резкое падение до минимума около $2,49 в 10:45 после инцидента и восстановление примерно до $2,70 к 19:00",
            "tr": "Lighter'ın LIT tokeninin 16 Kasım 2026'da CoinGecko'daki fiyatının çizgi grafiği (UTC): gece yarısı yaklaşık 2,83 $, 10.00'da yaklaşık 2,75 $, olaydan sonra 10.45'te yaklaşık 2,49 $'lık dibe sert düşüş ve 19.00'a kadar yaklaşık 2,70 $'a toparlanma",
            "id": "Grafik garis harga token LIT milik Lighter di CoinGecko pada 16 November 2026 (UTC): sekitar US$2,83 pada tengah malam, sekitar US$2,75 pada pukul 10.00, anjlok tajam ke titik terendah sekitar US$2,49 pada pukul 10.45 setelah insiden, lalu pulih ke sekitar US$2,70 pada pukul 19.00",
            "ja": "2026年11月16日（UTC）のCoinGeckoにおけるLighterのLITトークン価格の折れ線グラフ：0時に約2.83ドル、10時に約2.75ドル、事件後の10時45分に約2.49ドルの安値まで急落し、19時までに約2.70ドルへ回復",
            "ko": "2026년 11월 16일(UTC) CoinGecko 기준 라이터 LIT 토큰 가격 선 차트: 자정 약 2.83달러, 10시 약 2.75달러, 사고 후 10시 45분 약 2.49달러 저점까지 급락한 뒤 19시까지 약 2.70달러로 회복",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinGecko LIT/USD 5-minute prices")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of the Lighter incident on Nov. 16, 2026, in U.S. Central time: 4:11 a.m., about 10.39 million USDC leaves Lighter and is swapped to ether within minutes; 5:02 a.m., Lighter suspends all withdrawals and pool creation; 6:49 a.m., Lighter blames a trader's leaked API key and turns on Guardian mode; 12:21 p.m., about 5 million USDC is returned to the trader and withdrawals are back to normal", {
            "es": "Cronología del incidente de Lighter el 16 de noviembre de 2026, en hora del centro de EE. UU.: 4:11, salen de Lighter unos 10,39 millones de USDC que se cambian por ether en minutos; 5:02, Lighter suspende todos los retiros y la creación de pools; 6:49, Lighter atribuye el caso a la clave API filtrada de un trader y activa el modo Guardian; 12:21, se devuelven unos 5 millones de USDC al trader y los retiros vuelven a la normalidad",
            "pt": "Linha do tempo do incidente da Lighter em 16 de novembro de 2026, no horário central dos EUA: 4h11, cerca de 10,39 milhões de USDC saem da Lighter e são trocados por ether em minutos; 5h02, a Lighter suspende todos os saques e a criação de pools; 6h49, a Lighter atribui o caso à chave de API vazada de um trader e ativa o modo Guardian; 12h21, cerca de 5 milhões de USDC são devolvidos ao trader e os saques voltam ao normal",
            "fr": "Chronologie de l'incident Lighter du 16 novembre 2026, heure du Centre des États-Unis : 4 h 11, environ 10,39 millions d'USDC quittent Lighter et sont échangés contre de l'ether en quelques minutes ; 5 h 02, Lighter suspend tous les retraits et la création de pools ; 6 h 49, Lighter met en cause la clé API divulguée d'un trader et active le mode Guardian ; 12 h 21, environ 5 millions d'USDC sont rendus au trader et les retraits reviennent à la normale",
            "de": "Zeitleiste des Lighter-Vorfalls am 16. November 2026, US-Central-Zeit: 4:11 Uhr, rund 10,39 Mio. USDC verlassen Lighter und werden binnen Minuten in Ether getauscht; 5:02 Uhr, Lighter stoppt alle Auszahlungen und das Anlegen von Pools; 6:49 Uhr, Lighter nennt den geleakten API-Schlüssel eines Traders als Ursache und aktiviert den Guardian-Modus; 12:21 Uhr, rund 5 Mio. USDC gehen an den Trader zurück, Auszahlungen laufen wieder normal",
            "ru": "Хронология инцидента с Lighter 16 ноября 2026 года по центральному времени США: 4:11, около 10,39 млн USDC выводят с Lighter и за несколько минут обменивают на эфир; 5:02, Lighter приостанавливает все выводы и создание пулов; 6:49, Lighter называет причиной утёкший API-ключ одного трейдера и включает режим Guardian; 12:21, трейдеру возвращают около 5 млн USDC, выводы работают в обычном режиме",
            "tr": "16 Kasım 2026'daki Lighter olayının ABD Merkez saatine göre zaman çizelgesi: 04.11, yaklaşık 10,39 milyon USDC Lighter'dan çıkıyor ve dakikalar içinde ether'e çevriliyor; 05.02, Lighter tüm çekimleri ve havuz oluşturmayı durduruyor; 06.49, Lighter olayı bir yatırımcının sızan API anahtarına bağlıyor ve Guardian modunu açıyor; 12.21, yaklaşık 5 milyon USDC yatırımcıya iade ediliyor ve çekimler normale dönüyor",
            "id": "Linimasa insiden Lighter pada 16 November 2026, waktu Central AS: 04.11, sekitar 10,39 juta USDC keluar dari Lighter dan ditukar ke ether dalam hitungan menit; 05.02, Lighter menangguhkan semua penarikan dan pembuatan pool; 06.49, Lighter menyebut penyebabnya kunci API seorang trader yang bocor dan menyalakan mode Guardian; 12.21, sekitar 5 juta USDC dikembalikan ke trader dan penarikan kembali normal",
            "ja": "2026年11月16日のLighter事件の時系列（米中部時間）：午前4時11分、約1039万USDCがLighterから流出し数分でイーサに交換、午前5時2分、Lighterが全出金とプール作成を停止、午前6時49分、Lighterがトレーダー1人のAPIキー流出が原因と発表しGuardianモードを有効化、午後0時21分、約500万USDCがトレーダーに返還され出金が通常に戻る",
            "ko": "2026년 11월 16일 라이터 사고 타임라인(미국 중부시간): 오전 4시 11분, 약 1,039만 USDC가 라이터에서 빠져나가 몇 분 만에 이더로 교환, 오전 5시 2분, 라이터가 모든 출금과 풀 생성 중단, 오전 6시 49분, 라이터가 트레이더 한 명의 API 키 유출을 원인으로 지목하고 가디언 모드 가동, 오후 12시 21분, 약 500만 USDC가 트레이더에게 반환되고 출금 정상화",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bitquery; Lighter on X")},
    ]


def build_custodia_scotus():
    slug = "supreme-court-rejects-custodia-fed-master-account-nov-2026"
    d = OUT / slug
    # Bitcoin Magazine, SCOTUSblog, Supreme Court order list (Nov 16, 2026).
    tl = make_timeline_card(
        d / "timeline-custodia-master-account",
        "Custodia vs. the Fed",
        [
            ("Oct. 2020", "Custodia applies to the Kansas City Fed", (96, 165, 250)),
            ("Jan. 2023", "Kansas City Fed denies the master account", RED),
            ("Oct. 2025", "10th Circuit sides with the Fed, 2-1", ORANGE),
            ("Nov. 16, 2026", "Supreme Court declines to hear the case", RED),
        ],
        footer="Supreme Court order list; SCOTUSblog; Bitcoin Magazine",
        margin=170, wrap_w=250,
    )
    card = make_fact_card(
        d / "fact-custodia-cert-denied",
        label="Custodia Bank v. Fed Board, No. 26-62",
        big="Certiorari denied",
        sub="The ruling left in place: regional Fed banks may refuse a master account even to a legally eligible bank.",
        footer="Supreme Court order list, Nov. 16, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: in October 2020, Custodia applies to the Kansas City Fed for a master account; in January 2023, the Kansas City Fed denies it; in October 2025, the 10th Circuit sides with the Fed by a 2-1 vote; on Nov. 16, 2026, the Supreme Court declines to hear the case", {
            "es": "Cronología: en octubre de 2020, Custodia solicita una cuenta maestra a la Fed de Kansas City; en enero de 2023, la Fed de Kansas City la rechaza; en octubre de 2025, el Décimo Circuito da la razón a la Fed por 2 votos a 1; el 16 de noviembre de 2026, el Tribunal Supremo se niega a revisar el caso",
            "pt": "Linha do tempo: em outubro de 2020, a Custodia pede uma conta master ao Fed de Kansas City; em janeiro de 2023, o Fed de Kansas City nega o pedido; em outubro de 2025, o 10º Circuito dá razão ao Fed por 2 votos a 1; em 16 de novembro de 2026, a Suprema Corte se recusa a julgar o caso",
            "fr": "Chronologie : en octobre 2020, Custodia demande un compte principal à la Fed de Kansas City ; en janvier 2023, la Fed de Kansas City refuse ; en octobre 2025, la cour d'appel du 10e circuit donne raison à la Fed par 2 voix contre 1 ; le 16 novembre 2026, la Cour suprême refuse d'examiner l'affaire",
            "de": "Zeitleiste: Im Oktober 2020 beantragt Custodia ein Master-Konto bei der Fed von Kansas City; im Januar 2023 lehnt die Fed von Kansas City ab; im Oktober 2025 gibt das Berufungsgericht des 10. Bezirks der Fed mit 2 zu 1 Stimmen recht; am 16. November 2026 lehnt der Supreme Court die Annahme des Falls ab",
            "ru": "Хронология: в октябре 2020 года Custodia подаёт заявку на мастер-счёт в ФРБ Канзас-Сити; в январе 2023 года ФРБ Канзас-Сити отказывает; в октябре 2025 года апелляционный суд 10-го округа поддерживает ФРС 2 голосами против 1; 16 ноября 2026 года Верховный суд отказывается рассматривать дело",
            "tr": "Zaman çizelgesi: Ekim 2020'de Custodia, Kansas City Fed'e ana hesap başvurusu yapıyor; Ocak 2023'te Kansas City Fed başvuruyu reddediyor; Ekim 2025'te 10. Daire Temyiz Mahkemesi 2'ye 1 oyla Fed'i haklı buluyor; 16 Kasım 2026'da Yüksek Mahkeme davayı görmeyi reddediyor",
            "id": "Linimasa: Oktober 2020, Custodia mengajukan master account ke Fed Kansas City; Januari 2023, Fed Kansas City menolaknya; Oktober 2025, Pengadilan Banding Sirkuit ke-10 memenangkan Fed dengan suara 2 lawan 1; 16 November 2026, Mahkamah Agung menolak memeriksa perkara itu",
            "ja": "時系列：2020年10月、Custodiaがカンザスシティ連銀にマスターアカウントを申請、2023年1月、カンザスシティ連銀が却下、2025年10月、第10巡回区控訴裁が2対1で連銀側を支持、2026年11月16日、最高裁が審理を拒否",
            "ko": "타임라인: 2020년 10월 커스토디아가 캔자스시티 연은에 마스터 계좌 신청, 2023년 1월 캔자스시티 연은이 거부, 2025년 10월 제10순회항소법원이 2대 1로 연준 손을 들어줌, 2026년 11월 16일 연방대법원이 사건 심리 거부",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Supreme Court of the United States; SCOTUSblog; Bitcoin Magazine")},
        {"id": "fact", "file": card.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Custodia Bank v. Federal Reserve Board, No. 26-62, certiorari denied on Nov. 16, 2026. The ruling left in place says regional Fed banks may refuse a master account even to a legally eligible bank", {
            "es": "Ficha: Custodia Bank contra la Junta de la Reserva Federal, n.º 26-62, certiorari denegado el 16 de noviembre de 2026. El fallo que queda en pie dice que los bancos regionales de la Fed pueden negar una cuenta maestra incluso a un banco legalmente elegible",
            "pt": "Destaque: Custodia Bank contra o Conselho do Federal Reserve, nº 26-62, certiorari negado em 16 de novembro de 2026. A decisão mantida diz que os bancos regionais do Fed podem negar uma conta master até a um banco legalmente elegível",
            "fr": "Fiche : Custodia Bank contre le conseil de la Réserve fédérale, n° 26-62, certiorari refusé le 16 novembre 2026. La décision maintenue dit que les banques régionales de la Fed peuvent refuser un compte principal même à une banque légalement éligible",
            "de": "Faktenkarte: Custodia Bank gegen Federal Reserve Board, Nr. 26-62, Certiorari am 16. November 2026 abgelehnt. Das bestehen bleibende Urteil besagt, dass regionale Fed-Banken ein Master-Konto selbst einer rechtlich berechtigten Bank verweigern dürfen",
            "ru": "Карточка: Custodia Bank против Совета управляющих ФРС, № 26-62, в истребовании дела отказано 16 ноября 2026 года. Оставленное в силе решение гласит, что региональные банки ФРС могут отказать в мастер-счёте даже банку, формально имеющему на него право",
            "tr": "Bilgi kartı: Custodia Bank - Fed Yönetim Kurulu davası, No. 26-62, 16 Kasım 2026'da certiorari reddedildi. Yürürlükte kalan karara göre bölgesel Fed bankaları, yasal olarak uygun bir bankaya bile ana hesap vermeyi reddedebilir",
            "id": "Kartu fakta: Custodia Bank melawan Dewan Federal Reserve, No. 26-62, certiorari ditolak pada 16 November 2026. Putusan yang tetap berlaku menyatakan bank Fed regional boleh menolak master account bahkan untuk bank yang secara hukum memenuhi syarat",
            "ja": "ファクトカード：Custodia Bank対FRB理事会（No. 26-62）、2026年11月16日に上告受理申立てを却下。維持された判決は、法的に適格な銀行に対しても地区連銀がマスターアカウントを拒否できるとする",
            "ko": "팩트 카드: 커스토디아 은행 대 연준 이사회(No. 26-62), 2026년 11월 16일 상고허가 신청 기각. 유지된 판결은 지역 연은이 법적으로 자격 있는 은행에도 마스터 계좌를 거부할 수 있다고 봄",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Supreme Court of the United States, order list, Nov. 16, 2026")},
    ]


def build_solana_1_0():
    slug = "solana-drops-mainnet-beta-solana-1-0-nov-2026"
    d = OUT / slug
    # Decrypt, The Block, CoinDesk (Nov 16, 2026).
    tl = make_timeline_card(
        d / "timeline-solana-1-0",
        "Solana: from beta to 1.0",
        [
            ("Mar. 16, 2020", "Solana launches as \"mainnet beta\"", (96, 165, 250)),
            ("Dec. 2025", "Firedancer, a second validator client, goes live", (52, 211, 153)),
            ("Oct. 21, 2026", "Alpenglow upgrade targets ~150 ms finality", (52, 211, 153)),
            ("Nov. 16, 2026", "Beta label retired; Solana 1.0", ORANGE),
        ],
        footer="Solana Foundation via Decrypt, The Block, CoinDesk",
        margin=170, wrap_w=250,
    )
    # CoinGecko SOL/USD hourly prices, Sep 17 - Nov 16, 2026 (UTC): high about $124.42 on Sep 27, low about $67.86 on Nov 15, about $71.69 at 23:00 UTC Nov 16.
    xs, ys = fetch_coingecko_range("solana", 1789603200, 1794870000)
    chart = make_line_chart(
        d / "chart-sol-price-60d",
        xs, ys,
        title="Solana (SOL) price, Sep. 17 - Nov. 16, 2026 (CoinGecko, hourly, USD)",
        hline=max(ys),
        hlabel=f"High ≈ ${max(ys):.0f} on Sep. 27 (CoinGecko)",
        yfmt=lambda x, _p: f"${x:,.0f}",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: on March 16, 2020, Solana launches as mainnet beta; in December 2025, Firedancer, a second validator client, goes live; on Oct. 21, 2026, the Alpenglow upgrade targets about 150 milliseconds finality; on Nov. 16, 2026, the beta label is retired and Solana 1.0 is introduced", {
            "es": "Cronología: el 16 de marzo de 2020, Solana se lanza como «mainnet beta»; en diciembre de 2025 entra en funcionamiento Firedancer, un segundo cliente de validadores; el 21 de octubre de 2026, la actualización Alpenglow busca una finalidad de unos 150 milisegundos; el 16 de noviembre de 2026 se retira la etiqueta beta y llega Solana 1.0",
            "pt": "Linha do tempo: em 16 de março de 2020, a Solana é lançada como \"mainnet beta\"; em dezembro de 2025, entra no ar o Firedancer, um segundo cliente de validadores; em 21 de outubro de 2026, a atualização Alpenglow mira uma finalidade de cerca de 150 milissegundos; em 16 de novembro de 2026, o rótulo beta é aposentado e surge a Solana 1.0",
            "fr": "Chronologie : le 16 mars 2020, Solana est lancé en « mainnet beta » ; en décembre 2025, Firedancer, un second client de validation, est mis en service ; le 21 octobre 2026, la mise à jour Alpenglow vise une finalité d'environ 150 millisecondes ; le 16 novembre 2026, l'étiquette bêta est retirée et Solana 1.0 est lancé",
            "de": "Zeitleiste: Am 16. März 2020 startet Solana als „Mainnet Beta“; im Dezember 2025 geht Firedancer als zweiter Validator-Client live; am 21. Oktober 2026 zielt das Alpenglow-Upgrade auf eine Finalität von rund 150 Millisekunden; am 16. November 2026 wird das Beta-Label abgelegt und Solana 1.0 eingeführt",
            "ru": "Хронология: 16 марта 2020 года Solana запускается как «mainnet beta»; в декабре 2025 года начинает работать Firedancer, второй клиент для валидаторов; 21 октября 2026 года обновление Alpenglow нацелено на финальность около 150 миллисекунд; 16 ноября 2026 года метка beta снята, представлена Solana 1.0",
            "tr": "Zaman çizelgesi: 16 Mart 2020'de Solana \"mainnet beta\" olarak başlıyor; Aralık 2025'te ikinci doğrulayıcı istemcisi Firedancer devreye giriyor; 21 Ekim 2026'da Alpenglow güncellemesi yaklaşık 150 milisaniyelik kesinlik hedefliyor; 16 Kasım 2026'da beta etiketi kaldırılıyor ve Solana 1.0 tanıtılıyor",
            "id": "Linimasa: 16 Maret 2020, Solana diluncurkan sebagai \"mainnet beta\"; Desember 2025, Firedancer, klien validator kedua, mulai aktif; 21 Oktober 2026, pembaruan Alpenglow menargetkan finalitas sekitar 150 milidetik; 16 November 2026, label beta dihapus dan Solana 1.0 diperkenalkan",
            "ja": "時系列：2020年3月16日、Solanaが「メインネットベータ」として稼働開始、2025年12月、2つ目のバリデータークライアントFiredancerが稼働、2026年10月21日、Alpenglowアップグレードが約150ミリ秒のファイナリティを目標に、2026年11月16日、ベータ表記を廃止しSolana 1.0を導入",
            "ko": "타임라인: 2020년 3월 16일 솔라나가 '메인넷 베타'로 출시, 2025년 12월 두 번째 검증자 클라이언트 파이어댄서 가동, 2026년 10월 21일 알펜글로 업그레이드로 약 150밀리초 완결성 목표, 2026년 11월 16일 베타 표기 폐지 및 솔라나 1.0 도입",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Solana Foundation via Decrypt, The Block and CoinDesk")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of Solana's SOL price on CoinGecko from Sep. 17 to Nov. 16, 2026: about $99 in mid-September, a high of about $124 on Sep. 27, then a steady slide to a low of about $68 on Nov. 15 and about $72 on Nov. 16", {
            "es": "Gráfico de líneas del precio de SOL de Solana en CoinGecko del 17 de septiembre al 16 de noviembre de 2026: unos 99 dólares a mediados de septiembre, un máximo de unos 124 el 27 de septiembre y después una caída constante hasta un mínimo de unos 68 el 15 de noviembre y unos 72 el 16 de noviembre",
            "pt": "Gráfico de linha do preço do SOL, da Solana, na CoinGecko de 17 de setembro a 16 de novembro de 2026: cerca de US$ 99 em meados de setembro, máxima de cerca de US$ 124 em 27 de setembro e depois queda contínua até a mínima de cerca de US$ 68 em 15 de novembro e cerca de US$ 72 em 16 de novembro",
            "fr": "Courbe du cours du SOL de Solana sur CoinGecko du 17 septembre au 16 novembre 2026 : environ 99 dollars mi-septembre, un plus haut d'environ 124 le 27 septembre, puis une baisse continue jusqu'à un plus bas d'environ 68 le 15 novembre et environ 72 le 16 novembre",
            "de": "Liniendiagramm des SOL-Kurses von Solana bei CoinGecko vom 17. September bis 16. November 2026: rund 99 $ Mitte September, ein Hoch von rund 124 $ am 27. September, danach ein stetiger Rückgang auf ein Tief von rund 68 $ am 15. November und rund 72 $ am 16. November",
            "ru": "Линейный график цены SOL сети Solana по данным CoinGecko с 17 сентября по 16 ноября 2026 года: около $99 в середине сентября, максимум около $124 27 сентября, затем плавное снижение до минимума около $68 15 ноября и около $72 16 ноября",
            "tr": "Solana'nın SOL fiyatının 17 Eylül - 16 Kasım 2026 arasında CoinGecko'daki çizgi grafiği: eylül ortasında yaklaşık 99 $, 27 Eylül'de yaklaşık 124 $ ile zirve, ardından 15 Kasım'da yaklaşık 68 $'lık dibe ve 16 Kasım'da yaklaşık 72 $'a istikrarlı düşüş",
            "id": "Grafik garis harga SOL milik Solana di CoinGecko dari 17 September hingga 16 November 2026: sekitar US$99 pada pertengahan September, puncak sekitar US$124 pada 27 September, lalu turun terus ke titik terendah sekitar US$68 pada 15 November dan sekitar US$72 pada 16 November",
            "ja": "2026年9月17日～11月16日のCoinGeckoにおけるSolanaのSOL価格の折れ線グラフ：9月中旬に約99ドル、9月27日に約124ドルの高値、その後じりじりと下落し11月15日に約68ドルの安値、11月16日は約72ドル",
            "ko": "2026년 9월 17일~11월 16일 CoinGecko 기준 솔라나 SOL 가격 선 차트: 9월 중순 약 99달러, 9월 27일 약 124달러 고점, 이후 꾸준히 하락해 11월 15일 약 68달러 저점, 11월 16일 약 72달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinGecko SOL/USD hourly prices")},
    ]


def build_optimizely_clipper():
    slug = "optimizely-hack-crypto-address-swap-178-sites-nov-2026"
    d = OUT / slug
    # Report URI (Scott Helme), "World's Largest Brands Infected With Malware Via Optimizely", Nov 16, 2026, timeline (UTC)
    # and Nov 17 update; converted to U.S. Central time (UTC-6). Earlier wave Nov 13 via other scripts (Report URI, Hudson Rock).
    tl = make_timeline_card(
        d / "timeline-optimizely-attack",
        "Optimizely attack (U.S. Central time)",
        [
            ("Nov. 13", "Earlier wave hits sites through three other web scripts", (96, 165, 250)),
            ("Nov. 15", "10:21 p.m.: first Optimizely snippet injection seen (BBC)", (248, 113, 113)),
            ("Nov. 16", "2:28 a.m.: crypto address-swapping script first seen on bbc.com", (248, 113, 113)),
            ("Nov. 16 ", "5:11 p.m.: all infected Optimizely files cleaned", (74, 222, 128)),
        ],
        footer="Report URI (Scott Helme)",
        margin=170, wrap_w=250,
    )
    # Report URI: organizations with infected Optimizely snippets by sector (178 total), Nov 16, 2026.
    labels = ["Banking &\nfinance", "Tech &\nSaaS", "Retail &\nfashion", "Streaming", "News &\nmedia", "Airlines &\ntravel", "Healthcare", "Crypto &\ntrading"]
    vals = [32, 23, 20, 12, 10, 9, 8, 6]
    cols = ["#f7931a"] * 7 + ["#f87171"]
    chart = make_bar_chart(
        d / "chart-infected-orgs-by-sector",
        labels, vals,
        title="Organizations served the malicious Optimizely code, by sector (Report URI, Nov. 16, 2026)",
        colors=cols,
        value_fmt=lambda v: f"{v:.0f}",
        axis_fmt=lambda x, _p: f"{x:.0f}",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of the Optimizely attack in U.S. Central time: Nov. 13, an earlier wave hits sites through three other web scripts; Nov. 15 at 10:21 p.m., the first Optimizely snippet injection is seen on the BBC; Nov. 16 at 2:28 a.m., the crypto address-swapping script is first seen on bbc.com; Nov. 16 at 5:11 p.m., all infected Optimizely files are cleaned", {
            "es": "Cronología del ataque a Optimizely en hora del centro de EE. UU.: 13 de noviembre, una oleada anterior llega a sitios a través de otros tres scripts web; 15 de noviembre a las 22:21, se detecta la primera inyección en un fragmento de Optimizely, en la BBC; 16 de noviembre a las 2:28, aparece por primera vez en bbc.com el script que cambia direcciones de criptomonedas; 16 de noviembre a las 17:11, todos los archivos infectados de Optimizely quedan limpios",
            "pt": "Linha do tempo do ataque à Optimizely no horário central dos EUA: 13 de novembro, uma onda anterior atinge sites por meio de outros três scripts web; 15 de novembro às 22h21, é vista a primeira injeção em um snippet da Optimizely, na BBC; 16 de novembro às 2h28, o script que troca endereços de cripto aparece pela primeira vez no bbc.com; 16 de novembro às 17h11, todos os arquivos infectados da Optimizely são limpos",
            "fr": "Chronologie de l'attaque Optimizely, heure du Centre des États-Unis : 13 novembre, une première vague touche des sites via trois autres scripts web ; 15 novembre à 22 h 21, première injection repérée dans un snippet Optimizely, sur la BBC ; 16 novembre à 2 h 28, le script qui remplace les adresses crypto apparaît pour la première fois sur bbc.com ; 16 novembre à 17 h 11, tous les fichiers Optimizely infectés sont nettoyés",
            "de": "Zeitleiste des Optimizely-Angriffs in US-Central-Zeit: 13. November, eine frühere Welle trifft Websites über drei andere Web-Skripte; 15. November, 22:21 Uhr, erste Injektion in ein Optimizely-Snippet entdeckt (BBC); 16. November, 2:28 Uhr, das Skript zum Austausch von Krypto-Adressen taucht erstmals auf bbc.com auf; 16. November, 17:11 Uhr, alle infizierten Optimizely-Dateien sind bereinigt",
            "ru": "Хронология атаки через Optimizely по центральному времени США: 13 ноября, более ранняя волна заражает сайты через три других веб-скрипта; 15 ноября в 22:21, замечено первое внедрение в сниппет Optimizely (BBC); 16 ноября в 2:28, скрипт подмены криптоадресов впервые появляется на bbc.com; 16 ноября в 17:11, все заражённые файлы Optimizely очищены",
            "tr": "ABD Merkez saatine göre Optimizely saldırısının zaman çizelgesi: 13 Kasım, daha önceki bir dalga siteleri üç farklı web betiği üzerinden vuruyor; 15 Kasım 22.21, ilk Optimizely kod parçası enjeksiyonu BBC'de görülüyor; 16 Kasım 02.28, kripto adreslerini değiştiren betik ilk kez bbc.com'da görülüyor; 16 Kasım 17.11, enfekte tüm Optimizely dosyaları temizleniyor",
            "id": "Linimasa serangan Optimizely dalam waktu Central AS: 13 November, gelombang sebelumnya mengenai situs melalui tiga skrip web lain; 15 November pukul 22.21, injeksi pertama pada snippet Optimizely terlihat di BBC; 16 November pukul 02.28, skrip penukar alamat kripto pertama kali terlihat di bbc.com; 16 November pukul 17.11, semua file Optimizely yang terinfeksi sudah dibersihkan",
            "ja": "Optimizely攻撃の時系列（米中部時間）：11月13日、別の3つのウェブスクリプト経由で先行する攻撃の波、11月15日午後10時21分、BBCのOptimizelyスニペットで最初の改ざんを確認、11月16日午前2時28分、暗号資産アドレスをすり替えるスクリプトがbbc.comで初めて確認、11月16日午後5時11分、感染したOptimizelyのファイルがすべて除去",
            "ko": "미국 중부시간 기준 옵티마이즐리 공격 타임라인: 11월 13일, 다른 웹 스크립트 3개를 통한 앞선 공격, 11월 15일 오후 10시 21분, BBC의 옵티마이즐리 스니펫에서 첫 악성 코드 삽입 확인, 11월 16일 오전 2시 28분, 암호화폐 주소 바꿔치기 스크립트가 bbc.com에서 처음 확인, 11월 16일 오후 5시 11분, 감염된 옵티마이즐리 파일 모두 정리",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Report URI (Scott Helme)")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of organizations served the malicious Optimizely code on Nov. 16, 2026, by sector, according to Report URI: banking and finance 32, technology and SaaS 23, retail and fashion 20, streaming 12, news and media 10, airlines and travel 9, healthcare 8, crypto and trading 6", {
            "es": "Gráfico de barras de las organizaciones que sirvieron el código malicioso de Optimizely el 16 de noviembre de 2026, por sector, según Report URI: banca y finanzas 32, tecnología y SaaS 23, comercio y moda 20, streaming 12, noticias y medios 10, aerolíneas y viajes 9, salud 8, cripto y trading 6",
            "pt": "Gráfico de barras das organizações que serviram o código malicioso da Optimizely em 16 de novembro de 2026, por setor, segundo a Report URI: bancos e finanças 32, tecnologia e SaaS 23, varejo e moda 20, streaming 12, notícias e mídia 10, aéreas e viagens 9, saúde 8, cripto e trading 6",
            "fr": "Diagramme en barres des organisations ayant diffusé le code malveillant d'Optimizely le 16 novembre 2026, par secteur, selon Report URI : banque et finance 32, technologie et SaaS 23, commerce et mode 20, streaming 12, presse et médias 10, aérien et voyage 9, santé 8, crypto et trading 6",
            "de": "Balkendiagramm der Organisationen, deren Websites am 16. November 2026 den bösartigen Optimizely-Code auslieferten, nach Branche laut Report URI: Banken und Finanzen 32, Technologie und SaaS 23, Handel und Mode 20, Streaming 12, Nachrichten und Medien 10, Airlines und Reisen 9, Gesundheit 8, Krypto und Trading 6",
            "ru": "Столбчатая диаграмма организаций, чьи сайты 16 ноября 2026 года раздавали вредоносный код через Optimizely, по отраслям, по данным Report URI: банки и финансы 32, технологии и SaaS 23, ритейл и мода 20, стриминг 12, новости и СМИ 10, авиакомпании и путешествия 9, здравоохранение 8, криптовалюты и трейдинг 6",
            "tr": "Report URI'ye göre 16 Kasım 2026'da kötü amaçlı Optimizely kodunu sunan kuruluşların sektörlere göre çubuk grafiği: bankacılık ve finans 32, teknoloji ve SaaS 23, perakende ve moda 20, yayın platformları 12, haber ve medya 10, havayolu ve seyahat 9, sağlık 8, kripto ve alım satım 6",
            "id": "Grafik batang organisasi yang menyajikan kode berbahaya Optimizely pada 16 November 2026, menurut sektor, berdasarkan Report URI: perbankan dan keuangan 32, teknologi dan SaaS 23, ritel dan fesyen 20, streaming 12, berita dan media 10, maskapai dan perjalanan 9, kesehatan 8, kripto dan trading 6",
            "ja": "Report URIによる、2026年11月16日に悪意あるOptimizelyのコードを配信していた組織の業種別棒グラフ：銀行・金融32、テクノロジー・SaaS 23、小売・ファッション20、動画配信12、ニュース・メディア10、航空・旅行9、ヘルスケア8、暗号資産・トレーディング6",
            "ko": "Report URI 기준 2026년 11월 16일 악성 옵티마이즐리 코드를 내보낸 조직의 업종별 막대 차트: 은행·금융 32, 기술·SaaS 23, 소매·패션 20, 스트리밍 12, 뉴스·미디어 10, 항공·여행 9, 헬스케어 8, 암호화폐·트레이딩 6",
         }),
         "caption": tr_map(CAPTION_CHART, src="Report URI, infected Optimizely snippets by sector")},
    ]


def build_coingecko_solana():
    slug = "solana-foundation-coingecko-majority-stake-nov-2026"
    d = OUT / slug
    # Solana Foundation announcement via CoinDesk and Solana Compass (Nov 17, 2026): 18M registered users,
    # 50M+ monthly sessions, API powers 180,000 crypto apps and businesses.
    fact = make_fact_card(
        d / "fact-coingecko-18-million-users",
        "CoinGecko's reach",
        "18 million users",
        "registered on CoinGecko, whose API feeds about 180,000 crypto apps and businesses (Solana Foundation)",
        footer="Solana Foundation via CoinDesk and Solana Compass",
    )
    # CoinGecko SOL/USD hourly, Nov 10 00:00 - Nov 17 13:00 UTC: about $86.60 at the start, low about $67.86 on Nov 15 02:00 UTC, about $73.61 at the end.
    xs, ys = fetch_coingecko_range("solana", 1794268800, 1794920400)
    chart = make_line_chart(
        d / "chart-sol-price-week",
        xs, ys,
        title="Solana (SOL) price, Nov. 10 - Nov. 17, 2026 (CoinGecko, hourly, UTC)",
        hline=min(ys),
        hlabel=f"Low ≈ ${min(ys):.2f} on Nov. 15 (CoinGecko)",
        yfmt=lambda x, _p: f"${x:,.0f}",
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: CoinGecko has 18 million registered users, and its API feeds about 180,000 crypto apps and businesses, according to the Solana Foundation", {
            "es": "Tarjeta de datos: CoinGecko tiene 18 millones de usuarios registrados y su API alimenta a unas 180.000 aplicaciones y empresas cripto, según la Solana Foundation",
            "pt": "Cartão de dados: a CoinGecko tem 18 milhões de usuários registrados, e sua API abastece cerca de 180.000 aplicativos e empresas de cripto, segundo a Solana Foundation",
            "fr": "Fiche chiffrée : CoinGecko compte 18 millions d'utilisateurs inscrits et son API alimente environ 180 000 applications et entreprises crypto, selon la Solana Foundation",
            "de": "Faktenkarte: CoinGecko hat 18 Millionen registrierte Nutzer, und seine API beliefert rund 180.000 Krypto-Apps und Unternehmen, so die Solana Foundation",
            "ru": "Карточка с фактом: у CoinGecko 18 млн зарегистрированных пользователей, а его API снабжает данными около 180 000 криптоприложений и компаний, по данным Solana Foundation",
            "tr": "Bilgi kartı: Solana Foundation'a göre CoinGecko'nun 18 milyon kayıtlı kullanıcısı var ve API'si yaklaşık 180.000 kripto uygulamasına ve şirkete veri sağlıyor",
            "id": "Kartu fakta: CoinGecko memiliki 18 juta pengguna terdaftar, dan API-nya memasok sekitar 180.000 aplikasi dan perusahaan kripto, menurut Solana Foundation",
            "ja": "ファクトカード：Solana Foundationによると、CoinGeckoの登録ユーザーは1800万人で、そのAPIは約18万の暗号資産アプリや企業にデータを提供",
            "ko": "팩트 카드: 솔라나 재단에 따르면 코인게코의 등록 사용자는 1,800만 명이며, API는 약 18만 개의 암호화폐 앱과 기업에 데이터를 제공",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Solana Foundation via CoinDesk and Solana Compass")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of Solana's SOL price on CoinGecko from Nov. 10 to Nov. 17, 2026: about $86.60 on Nov. 10, a slide to a low of about $67.86 on Nov. 15, then a rebound to about $73.60 on the morning of Nov. 17", {
            "es": "Gráfico de líneas del precio de SOL de Solana en CoinGecko del 10 al 17 de noviembre de 2026: unos 86,60 dólares el 10 de noviembre, caída hasta un mínimo de unos 67,86 el 15 de noviembre y rebote hasta unos 73,60 la mañana del 17 de noviembre",
            "pt": "Gráfico de linha do preço do SOL, da Solana, na CoinGecko de 10 a 17 de novembro de 2026: cerca de US$ 86,60 em 10 de novembro, queda até a mínima de cerca de US$ 67,86 em 15 de novembro e recuperação para cerca de US$ 73,60 na manhã de 17 de novembro",
            "fr": "Courbe du cours du SOL de Solana sur CoinGecko du 10 au 17 novembre 2026 : environ 86,60 dollars le 10 novembre, une baisse jusqu'à un plus bas d'environ 67,86 le 15 novembre, puis un rebond vers 73,60 le matin du 17 novembre",
            "de": "Liniendiagramm des SOL-Kurses von Solana bei CoinGecko vom 10. bis 17. November 2026: rund 86,60 $ am 10. November, ein Rückgang auf ein Tief von rund 67,86 $ am 15. November, danach eine Erholung auf rund 73,60 $ am Morgen des 17. November",
            "ru": "Линейный график цены SOL сети Solana по данным CoinGecko с 10 по 17 ноября 2026 года: около $86,60 10 ноября, снижение до минимума около $67,86 15 ноября, затем отскок примерно до $73,60 утром 17 ноября",
            "tr": "Solana'nın SOL fiyatının 10-17 Kasım 2026 arasında CoinGecko'daki çizgi grafiği: 10 Kasım'da yaklaşık 86,60 $, 15 Kasım'da yaklaşık 67,86 $'lık dibe düşüş, ardından 17 Kasım sabahı yaklaşık 73,60 $'a toparlanma",
            "id": "Grafik garis harga SOL milik Solana di CoinGecko dari 10 hingga 17 November 2026: sekitar US$86,60 pada 10 November, turun ke titik terendah sekitar US$67,86 pada 15 November, lalu pulih ke sekitar US$73,60 pada pagi 17 November",
            "ja": "2026年11月10日～17日のCoinGeckoにおけるSolanaのSOL価格の折れ線グラフ：11月10日に約86.60ドル、11月15日に約67.86ドルの安値まで下落し、11月17日朝には約73.60ドルへ反発",
            "ko": "2026년 11월 10일~17일 CoinGecko 기준 솔라나 SOL 가격 선 차트: 11월 10일 약 86.60달러, 11월 15일 약 67.86달러 저점까지 하락한 뒤 11월 17일 오전 약 73.60달러로 반등",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinGecko SOL/USD hourly prices")},
    ]


def build_trezor_skladon():
    slug = "trezor-skladon-shipping-breach-27000-orders-nov-2026"
    d = OUT / slug
    # Trezor blog, "Data breach at Trezor shipping partner, Skladon", Nov 16, 2026.
    tl = make_timeline_card(
        d / "timeline-trezor-skladon-breach",
        "Skladon breach timeline (Trezor)",
        [
            ("Aug. 9", "Start of the order window: orders from this date are in the exported data", (96, 165, 250)),
            ("Nov. 7", "Attacker breaks into shipping partner Skladon's systems", (248, 113, 113)),
            ("Nov. 15", "Skladon notifies Trezor of the unauthorized access", (251, 191, 36)),
            ("Nov. 16", "Trezor discloses the breach and emails affected customers", (74, 222, 128)),
        ],
        footer="Trezor blog, Nov. 16, 2026",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-trezor-27000-orders",
        "Exposed in the Skladon breach",
        "~27,000 orders",
        "Names, phone numbers, email and delivery addresses, products and prices. No wallet backups, PINs or passphrases (Trezor)",
        footer="Trezor blog, Nov. 16, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of the Skladon breach according to Trezor: Aug. 9, start of the window of orders in the exported data; Nov. 7, the attacker breaks into shipping partner Skladon's systems; Nov. 15, Skladon notifies Trezor; Nov. 16, Trezor discloses the breach and emails affected customers", {
            "es": "Cronología de la filtración en Skladon según Trezor: 9 de agosto, inicio del periodo de pedidos incluidos en los datos exportados; 7 de noviembre, el atacante entra en los sistemas de Skladon, socio de envíos; 15 de noviembre, Skladon avisa a Trezor; 16 de noviembre, Trezor revela la filtración y escribe a los clientes afectados",
            "pt": "Linha do tempo do vazamento na Skladon segundo a Trezor: 9 de agosto, início do período de pedidos incluídos nos dados exportados; 7 de novembro, o invasor entra nos sistemas da Skladon, parceira de entregas; 15 de novembro, a Skladon avisa a Trezor; 16 de novembro, a Trezor divulga o vazamento e envia e-mail aos clientes afetados",
            "fr": "Chronologie de la fuite chez Skladon selon Trezor : 9 août, début de la période des commandes contenues dans les données exportées ; 7 novembre, l'attaquant pénètre dans les systèmes de Skladon, partenaire de livraison ; 15 novembre, Skladon prévient Trezor ; 16 novembre, Trezor rend la fuite publique et écrit aux clients concernés",
            "de": "Zeitleiste des Skladon-Datenlecks laut Trezor: 9. August, Beginn des Bestellzeitraums in den exportierten Daten; 7. November, der Angreifer dringt in die Systeme des Versandpartners Skladon ein; 15. November, Skladon informiert Trezor; 16. November, Trezor macht das Leck öffentlich und schreibt betroffene Kunden an",
            "ru": "Хронология утечки у Skladon по данным Trezor: 9 августа, начало периода заказов, попавших в выгруженные данные; 7 ноября, злоумышленник проникает в системы службы доставки Skladon; 15 ноября, Skladon уведомляет Trezor; 16 ноября, Trezor сообщает об утечке и пишет пострадавшим клиентам",
            "tr": "Trezor'a göre Skladon sızıntısının zaman çizelgesi: 9 Ağustos, dışa aktarılan verideki sipariş döneminin başlangıcı; 7 Kasım, saldırgan kargo ortağı Skladon'un sistemlerine giriyor; 15 Kasım, Skladon Trezor'u bilgilendiriyor; 16 Kasım, Trezor sızıntıyı duyuruyor ve etkilenen müşterilere e-posta gönderiyor",
            "id": "Linimasa kebocoran di Skladon menurut Trezor: 9 Agustus, awal periode pesanan yang ada di data yang diekspor; 7 November, penyerang membobol sistem mitra pengiriman Skladon; 15 November, Skladon memberi tahu Trezor; 16 November, Trezor mengumumkan kebocoran dan mengirim email ke pelanggan yang terdampak",
            "ja": "Trezorによる配送パートナーSkladonの情報流出の時系列：8月9日、流出データに含まれる注文期間の開始、11月7日、攻撃者がSkladonのシステムに侵入、11月15日、SkladonがTrezorに通知、11月16日、Trezorが流出を公表し影響を受けた顧客にメールで連絡",
            "ko": "트레저가 밝힌 배송 협력사 스클라돈 유출 타임라인: 8월 9일, 유출된 데이터에 포함된 주문 기간 시작, 11월 7일, 공격자가 스클라돈 시스템에 침입, 11월 15일, 스클라돈이 트레저에 통보, 11월 16일, 트레저가 유출 사실을 공개하고 피해 고객에게 이메일 발송",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Trezor")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about 27,000 Trezor orders exposed in the Skladon breach, including names, phone numbers, email and delivery addresses, products and prices; no wallet backups, PINs or passphrases, according to Trezor", {
            "es": "Tarjeta de datos: unos 27.000 pedidos de Trezor expuestos en la filtración de Skladon, con nombres, teléfonos, correos y direcciones de entrega, productos y precios; sin copias de seguridad de carteras, PIN ni frases de contraseña, según Trezor",
            "pt": "Cartão de dados: cerca de 27.000 pedidos da Trezor expostos no vazamento da Skladon, com nomes, telefones, e-mails e endereços de entrega, produtos e preços; sem backups de carteiras, PINs ou frases-senha, segundo a Trezor",
            "fr": "Fiche chiffrée : environ 27 000 commandes Trezor exposées dans la fuite chez Skladon, avec noms, numéros de téléphone, adresses e-mail et de livraison, produits et prix ; aucune sauvegarde de portefeuille, aucun code PIN ni phrase secrète, selon Trezor",
            "de": "Faktenkarte: rund 27.000 Trezor-Bestellungen im Skladon-Leck offengelegt, mit Namen, Telefonnummern, E-Mail- und Lieferadressen, Produkten und Preisen; keine Wallet-Backups, PINs oder Passphrasen, so Trezor",
            "ru": "Карточка: около 27 000 заказов Trezor раскрыты при утечке у Skladon, включая имена, телефоны, электронные и почтовые адреса доставки, товары и цены; резервные копии кошельков, PIN-коды и парольные фразы не затронуты, по данным Trezor",
            "tr": "Bilgi kartı: Skladon sızıntısında yaklaşık 27.000 Trezor siparişi açığa çıktı; adlar, telefon numaraları, e-posta ve teslimat adresleri, ürünler ve fiyatlar dahil; Trezor'a göre cüzdan yedekleri, PIN'ler ve parolalar etkilenmedi",
            "id": "Kartu fakta: sekitar 27.000 pesanan Trezor terekspos dalam kebocoran Skladon, termasuk nama, nomor telepon, alamat email dan pengiriman, produk, dan harga; tanpa cadangan dompet, PIN, atau passphrase, menurut Trezor",
            "ja": "ファクトカード：Skladonの情報流出で約2万7000件のTrezor注文が流出、氏名、電話番号、メールアドレスと配送先住所、購入製品と価格を含む。Trezorによるとウォレットのバックアップ、PIN、パスフレーズは含まれない",
            "ko": "팩트 카드: 스클라돈 유출로 트레저 주문 약 2만 7000건 노출, 이름, 전화번호, 이메일과 배송 주소, 구매 제품과 가격 포함. 트레저에 따르면 지갑 백업, PIN, 패스프레이즈는 포함되지 않음",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Trezor")},
    ]


def build_coinbase_borrow_ny():
    slug = "coinbase-borrow-new-york-all-50-states-nov-2026"
    d = OUT / slug
    # Coinbase Help (crypto-backed loans intro), Coinbase blog update Nov 16, 2026, The Block Nov 17, 2026.
    cmp_ = make_compare_card(
        d / "compare-coinbase-borrow-new-york",
        "Coinbase Borrow: New York vs. other states",
        "New York", "Other states",
        [
            ("Collateral", "BTC, ETH, SOL", "BTC, ETH, SOL plus XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG, staked tokens"),
            ("Loan rates", "Variable only", "Variable or fixed"),
            ("Max loan", "$5M BTC, $1M ETH, $100K SOL", "Up to $5M against BTC"),
        ],
        footer="Coinbase Help Center, The Block",
    )
    fact = make_fact_card(
        d / "fact-coinbase-borrow-3-4-billion",
        "Coinbase Borrow since January 2025",
        "$3.4B+ in loans",
        "originated through Coinbase and Morpho on Base; more than $1.6B still outstanding (Morpho)",
        footer="Morpho blog, Nov. 17, 2026",
    )
    return [
        {"id": "compare", "file": cmp_.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Comparison of Coinbase Borrow in New York and other states: New York collateral is BTC, ETH and SOL, other states also allow XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG and staked tokens; New York has variable rates only, other states variable or fixed; New York limits are $5 million against BTC, $1 million against ETH and $100,000 against SOL", {
            "es": "Comparación de Coinbase Borrow en Nueva York y en otros estados: en Nueva York la garantía es BTC, ETH y SOL, en otros estados también XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG y tokens en staking; Nueva York solo tiene tipos variables, otros estados variables o fijos; los límites en Nueva York son 5 millones de dólares con BTC, 1 millón con ETH y 100.000 con SOL",
            "pt": "Comparação do Coinbase Borrow em Nova York e em outros estados: em Nova York a garantia é BTC, ETH e SOL, em outros estados também XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG e tokens em staking; Nova York só tem taxas variáveis, outros estados variáveis ou fixas; os limites em Nova York são US$ 5 milhões com BTC, US$ 1 milhão com ETH e US$ 100 mil com SOL",
            "fr": "Comparaison de Coinbase Borrow à New York et dans les autres États : à New York, la garantie se limite à BTC, ETH et SOL, ailleurs s'ajoutent XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG et des jetons stakés ; New York n'a que des taux variables, les autres États des taux variables ou fixes ; à New York, les plafonds sont de 5 millions de dollars contre du BTC, 1 million contre de l'ETH et 100 000 contre du SOL",
            "de": "Vergleich von Coinbase Borrow in New York und anderen Bundesstaaten: In New York sind BTC, ETH und SOL als Sicherheit zugelassen, anderswo zusätzlich XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG und gestakte Token; New York nur variable Zinsen, andere Staaten variabel oder fest; Obergrenzen in New York: 5 Mio. $ gegen BTC, 1 Mio. $ gegen ETH und 100.000 $ gegen SOL",
            "ru": "Сравнение Coinbase Borrow в Нью-Йорке и других штатах: в Нью-Йорке залогом могут быть только BTC, ETH и SOL, в других штатах также XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG и токены в стейкинге; в Нью-Йорке только плавающая ставка, в других штатах плавающая или фиксированная; лимиты в Нью-Йорке: $5 млн под BTC, $1 млн под ETH и $100 000 под SOL",
            "tr": "New York ile diğer eyaletlerde Coinbase Borrow karşılaştırması: New York'ta teminat BTC, ETH ve SOL; diğer eyaletlerde ayrıca XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG ve stake edilmiş tokenler; New York'ta yalnızca değişken faiz, diğer eyaletlerde değişken veya sabit; New York'taki limitler BTC karşılığı 5 milyon $, ETH karşılığı 1 milyon $ ve SOL karşılığı 100.000 $",
            "id": "Perbandingan Coinbase Borrow di New York dan negara bagian lain: di New York jaminannya BTC, ETH, dan SOL, di negara bagian lain juga XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG, dan token staking; New York hanya bunga mengambang, negara bagian lain mengambang atau tetap; batas di New York US$5 juta dengan BTC, US$1 juta dengan ETH, dan US$100.000 dengan SOL",
            "ja": "ニューヨーク州と他の州のCoinbase Borrowの比較：ニューヨーク州の担保はBTC、ETH、SOLのみ、他の州ではXRP、DOGE、ADA、LTC、ZEC、HYPE、PAXG、ステーキングトークンも利用可能。ニューヨーク州は変動金利のみ、他の州は変動または固定。ニューヨーク州の上限はBTC担保で500万ドル、ETHで100万ドル、SOLで10万ドル",
            "ko": "뉴욕주와 다른 주의 코인베이스 Borrow 비교: 뉴욕주 담보는 BTC, ETH, SOL뿐이고 다른 주에서는 XRP, DOGE, ADA, LTC, ZEC, HYPE, PAXG, 스테이킹 토큰도 가능. 뉴욕주는 변동금리만, 다른 주는 변동 또는 고정금리. 뉴욕주 한도는 BTC 담보 500만 달러, ETH 100만 달러, SOL 10만 달러",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Coinbase Help Center, The Block")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: more than $3.4 billion in loans originated through Coinbase Borrow since January 2025, with more than $1.6 billion still outstanding, according to Morpho", {
            "es": "Tarjeta de datos: más de 3.400 millones de dólares en préstamos concedidos a través de Coinbase Borrow desde enero de 2025, con más de 1.600 millones aún pendientes, según Morpho",
            "pt": "Cartão de dados: mais de US$ 3,4 bilhões em empréstimos concedidos pelo Coinbase Borrow desde janeiro de 2025, com mais de US$ 1,6 bilhão ainda em aberto, segundo a Morpho",
            "fr": "Fiche chiffrée : plus de 3,4 milliards de dollars de prêts accordés via Coinbase Borrow depuis janvier 2025, dont plus de 1,6 milliard encore en cours, selon Morpho",
            "de": "Faktenkarte: mehr als 3,4 Mrd. $ an Krediten über Coinbase Borrow seit Januar 2025 vergeben, davon mehr als 1,6 Mrd. $ noch ausstehend, laut Morpho",
            "ru": "Карточка: более $3,4 млрд займов выдано через Coinbase Borrow с января 2025 года, из них более $1,6 млрд ещё не погашены, по данным Morpho",
            "tr": "Bilgi kartı: Morpho'ya göre Ocak 2025'ten bu yana Coinbase Borrow üzerinden 3,4 milyar $'ın üzerinde kredi verildi, bunun 1,6 milyar $'ı aşkın kısmı hâlâ ödenmedi",
            "id": "Kartu fakta: lebih dari US$3,4 miliar pinjaman disalurkan lewat Coinbase Borrow sejak Januari 2025, dengan lebih dari US$1,6 miliar masih beredar, menurut Morpho",
            "ja": "ファクトカード：Morphoによると、2025年1月以降Coinbase Borrowを通じて34億ドル超の融資が実行され、うち16億ドル超が現在も残高として残る",
            "ko": "팩트 카드: 모포에 따르면 2025년 1월 이후 코인베이스 Borrow를 통해 34억 달러 이상의 대출이 실행됐고 이 중 16억 달러 이상이 아직 상환되지 않음",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Morpho")},
    ]


def build_russia_retail_crypto():
    slug = "russia-retail-investors-bitcoin-ether-usdt-300000-ruble-cap-nov-2026"
    d = OUT / slug
    # Bank of Russia press release Nov 6, 2026; Cointelegraph Nov 6, 2026; Bitcoin Magazine Nov 17, 2026.
    tl = make_timeline_card(
        d / "timeline-russia-crypto-rules",
        "Russia's crypto rollout (2026-2027)",
        [
            ("Sept. 1", "Crypto market law takes effect", (96, 165, 250)),
            ("Nov. 17", "Retail buyers may buy BTC, ETH, USDT", (247, 147, 26)),
            ("Nov. 22", "Exchanges may open organized trading", (96, 165, 250)),
            ("Dec. 1", "Moscow Exchange pilot planned", (96, 165, 250)),
            ("July 1, 2027", "Peer-to-peer crypto trading banned", (248, 113, 113)),
        ],
        footer="Bank of Russia, Cointelegraph, Bitcoin Magazine",
        margin=150, wrap_w=200,
    )
    fact = make_fact_card(
        d / "fact-300000-ruble-cap",
        "Bank of Russia rule, in force Nov. 17",
        "\u20bd300,000 a year",
        "Purchase cap per intermediary for ordinary investors. Only bitcoin, ether and USDT; a knowledge test is required first",
        footer="Bank of Russia, Nov. 6, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of Russia's crypto rollout: Sept. 1, 2026, the crypto market law takes effect; Nov. 17, ordinary investors may buy bitcoin, ether and USDT; Nov. 22, exchanges may open organized trading; Dec. 1, Moscow Exchange plans a pilot; July 1, 2027, peer-to-peer crypto trading is banned", {
            "es": "Cronología del despliegue cripto en Rusia: 1 de septiembre de 2026, entra en vigor la ley del mercado cripto; 17 de noviembre, los inversores minoristas pueden comprar bitcoin, ether y USDT; 22 de noviembre, las bolsas pueden abrir la negociación organizada; 1 de diciembre, la Bolsa de Moscú prevé un piloto; 1 de julio de 2027, se prohíbe el comercio cripto entre particulares",
            "pt": "Linha do tempo da abertura cripto na Rússia: 1º de setembro de 2026, entra em vigor a lei do mercado cripto; 17 de novembro, investidores comuns podem comprar bitcoin, ether e USDT; 22 de novembro, bolsas podem abrir negociação organizada; 1º de dezembro, a Bolsa de Moscou planeja um piloto; 1º de julho de 2027, o comércio cripto P2P é proibido",
            "fr": "Chronologie de l'ouverture crypto en Russie : 1er septembre 2026, entrée en vigueur de la loi sur le marché crypto ; 17 novembre, les particuliers peuvent acheter du bitcoin, de l'ether et de l'USDT ; 22 novembre, les bourses peuvent ouvrir des échanges organisés ; 1er décembre, pilote prévu à la Bourse de Moscou ; 1er juillet 2027, interdiction des échanges crypto entre particuliers",
            "de": "Zeitleiste der Krypto-Öffnung in Russland: 1. September 2026, das Kryptomarktgesetz tritt in Kraft; 17. November, Privatanleger dürfen Bitcoin, Ether und USDT kaufen; 22. November, Börsen dürfen den organisierten Handel öffnen; 1. Dezember, Pilotstart an der Moskauer Börse geplant; 1. Juli 2027, Peer-to-Peer-Kryptohandel wird verboten",
            "ru": "Хронология криптореформы в России: 1 сентября 2026 года вступает в силу закон о криптовалютном рынке; 17 ноября неквалифицированные инвесторы могут покупать биткоин, эфир и USDT; 22 ноября биржи могут открыть организованные торги; 1 декабря Мосбиржа планирует пилотный запуск; 1 июля 2027 года запрещается P2P-торговля криптовалютой",
            "tr": "Rusya'da kripto açılımının zaman çizelgesi: 1 Eylül 2026, kripto piyasası yasası yürürlüğe girer; 17 Kasım, bireysel yatırımcılar bitcoin, ether ve USDT alabilir; 22 Kasım, borsalar organize işlemleri açabilir; 1 Aralık, Moskova Borsası pilot planlıyor; 1 Temmuz 2027, eşler arası kripto ticareti yasaklanıyor",
            "id": "Linimasa pembukaan kripto di Rusia: 1 September 2026, undang-undang pasar kripto berlaku; 17 November, investor ritel boleh membeli bitcoin, ether, dan USDT; 22 November, bursa boleh membuka perdagangan terorganisasi; 1 Desember, Bursa Moskow merencanakan uji coba; 1 Juli 2027, perdagangan kripto peer-to-peer dilarang",
            "ja": "ロシアの暗号資産解禁の時系列：2026年9月1日、暗号資産市場法が施行、11月17日、一般投資家がビットコイン、イーサ、USDTを購入可能に、11月22日、取引所が組織的な取引を開始可能に、12月1日、モスクワ取引所が試験運用を予定、2027年7月1日、個人間（P2P）の暗号資産取引を禁止",
            "ko": "러시아 암호화폐 개방 타임라인: 2026년 9월 1일 암호화폐 시장법 시행, 11월 17일 일반 투자자의 비트코인·이더·USDT 매수 허용, 11월 22일 거래소의 조직화된 거래 개시 허용, 12월 1일 모스크바 거래소 시범 운영 예정, 2027년 7월 1일 개인 간(P2P) 암호화폐 거래 금지",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bank of Russia, Cointelegraph, Bitcoin Magazine")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: under the Bank of Russia rule in force since Nov. 17, ordinary investors can buy up to 300,000 rubles a year through each intermediary, only bitcoin, ether and USDT, after passing a knowledge test", {
            "es": "Tarjeta de datos: según la norma del Banco de Rusia vigente desde el 17 de noviembre, los inversores minoristas pueden comprar hasta 300.000 rublos al año por intermediario, solo bitcoin, ether y USDT, tras aprobar un test de conocimientos",
            "pt": "Cartão de dados: pela regra do Banco da Rússia em vigor desde 17 de novembro, investidores comuns podem comprar até 300.000 rublos por ano em cada intermediário, apenas bitcoin, ether e USDT, após passar em um teste de conhecimento",
            "fr": "Fiche chiffrée : selon la règle de la Banque de Russie en vigueur depuis le 17 novembre, les particuliers peuvent acheter jusqu'à 300 000 roubles par an et par intermédiaire, uniquement du bitcoin, de l'ether et de l'USDT, après un test de connaissances",
            "de": "Faktenkarte: Nach der seit 17. November geltenden Regel der Bank von Russland dürfen Privatanleger pro Vermittler bis zu 300.000 Rubel im Jahr kaufen, nur Bitcoin, Ether und USDT, nach einem Wissenstest",
            "ru": "Карточка: по указанию Банка России, действующему с 17 ноября, неквалифицированные инвесторы могут покупать через одного посредника не более чем на 300 000 рублей в год, только биткоин, эфир и USDT, после прохождения теста",
            "tr": "Bilgi kartı: Rusya Merkez Bankası'nın 17 Kasım'dan beri yürürlükte olan kuralına göre bireysel yatırımcılar, bilgi testini geçtikten sonra aracı kurum başına yılda en fazla 300.000 ruble değerinde yalnızca bitcoin, ether ve USDT alabilir",
            "id": "Kartu fakta: menurut aturan Bank Rusia yang berlaku sejak 17 November, investor ritel boleh membeli hingga 300.000 rubel per tahun melalui setiap perantara, hanya bitcoin, ether, dan USDT, setelah lulus tes pengetahuan",
            "ja": "ファクトカード：11月17日施行のロシア中央銀行の規則では、一般投資家は知識テストに合格した後、仲介業者1社あたり年30万ルーブルまで、ビットコイン、イーサ、USDTのみを購入できる",
            "ko": "팩트 카드: 11월 17일 시행된 러시아 중앙은행 규정에 따라 일반 투자자는 지식 테스트를 통과한 뒤 중개업체 한 곳당 연 30만 루블까지 비트코인, 이더, USDT만 살 수 있다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bank of Russia")},
    ]


def build_mev_acquittal():
    slug = "mev-brothers-acquitted-25-million-ethereum-bots-nov-2026"
    d = OUT / slug
    # Williams & Connolly Nov 2026; CoinDesk Nov 18, 2026; The Block Nov 16, 2026.
    tl = make_timeline_card(
        d / "timeline-peraire-bueno-case",
        "U.S. v. Peraire-Bueno (2023-2026)",
        [
            ("Apr. 2023", "About $25M taken from trading bots in 12 seconds", (248, 113, 113)),
            ("May 2024", "Brothers charged with wire fraud, money laundering conspiracy", (96, 165, 250)),
            ("Nov. 2025", "Jury deadlocks; mistrial", (96, 165, 250)),
            ("Nov. 16, 2026", "Judge enters acquittal on all charges", (74, 222, 128)),
        ],
        footer="Court opinion via CoinDesk, Williams & Connolly, The Block",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-no-terms-of-use",
        "Judge Jessica Clarke on Ethereum, Nov. 16",
        "\u201cNo terms of use\u201d",
        "\u201cIt is a trustless, highly adversarial environment with no terms of use.\u201d",
        footer="U.S. District Court, S.D.N.Y., via CoinDesk",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of the Peraire-Bueno case: April 2023, about $25 million taken from trading bots in 12 seconds; May 2024, the brothers are charged with wire fraud and money laundering conspiracy; November 2025, the jury deadlocks and a mistrial is declared; Nov. 16, 2026, the judge enters an acquittal on all charges", {
            "es": "Cronología del caso Peraire-Bueno: abril de 2023, unos 25 millones de dólares obtenidos de bots de trading en 12 segundos; mayo de 2024, los hermanos son acusados de fraude electrónico y conspiración para blanquear dinero; noviembre de 2025, el jurado no llega a un veredicto y se declara juicio nulo; 16 de noviembre de 2026, la jueza dicta la absolución de todos los cargos",
            "pt": "Linha do tempo do caso Peraire-Bueno: abril de 2023, cerca de US$ 25 milhões tirados de robôs de negociação em 12 segundos; maio de 2024, os irmãos são acusados de fraude eletrônica e conspiração para lavagem de dinheiro; novembro de 2025, o júri não chega a um veredito e o julgamento é anulado; 16 de novembro de 2026, a juíza absolve os dois de todas as acusações",
            "fr": "Chronologie de l'affaire Peraire-Bueno : avril 2023, environ 25 millions de dollars pris à des robots de trading en 12 secondes ; mai 2024, les frères sont inculpés de fraude électronique et d'association en vue de blanchiment ; novembre 2025, le jury ne parvient pas à un verdict et le procès est annulé ; 16 novembre 2026, la juge prononce l'acquittement sur tous les chefs",
            "de": "Zeitleiste des Falls Peraire-Bueno: April 2023, rund 25 Mio. $ von Trading-Bots in 12 Sekunden erbeutet; Mai 2024, Anklage wegen Überweisungsbetrugs und Verschwörung zur Geldwäsche; November 2025, die Jury kann sich nicht einigen, der Prozess platzt; 16. November 2026, die Richterin spricht die Brüder in allen Punkten frei",
            "ru": "Хронология дела Перайре-Буэно: апрель 2023 года, около 25 млн долларов получено у торговых ботов за 12 секунд; май 2024 года, братьям предъявлены обвинения в мошенничестве с использованием электронных средств связи и сговоре с целью отмывания денег; ноябрь 2025 года, присяжные не пришли к решению, процесс признан несостоявшимся; 16 ноября 2026 года судья оправдала братьев по всем пунктам",
            "tr": "Peraire-Bueno davasının zaman çizelgesi: Nisan 2023, 12 saniyede alım satım botlarından yaklaşık 25 milyon $ alındı; Mayıs 2024, kardeşler elektronik dolandırıcılık ve kara para aklama komplosuyla suçlandı; Kasım 2025, jüri karara varamadı ve dava geçersiz sayıldı; 16 Kasım 2026, hâkim tüm suçlamalardan beraat kararı verdi",
            "id": "Linimasa kasus Peraire-Bueno: April 2023, sekitar US$25 juta diambil dari bot trading dalam 12 detik; Mei 2024, kakak beradik itu didakwa penipuan elektronik dan konspirasi pencucian uang; November 2025, juri buntu dan sidang dinyatakan batal; 16 November 2026, hakim membebaskan keduanya dari semua dakwaan",
            "ja": "ペライレ＝ブエノ事件の時系列：2023年4月、12秒で取引ボットから約2500万ドルを取得、2024年5月、兄弟が通信詐欺とマネーロンダリング共謀の罪で起訴、2025年11月、陪審の評決がまとまらず審理無効、2026年11月16日、判事が全ての罪状で無罪判決",
            "ko": "페라이레-부에노 사건 타임라인: 2023년 4월 12초 만에 트레이딩 봇에서 약 2,500만 달러 획득, 2024년 5월 형제가 전신 사기 및 자금세탁 공모 혐의로 기소, 2025년 11월 배심원 평결 불일치로 심리 무효, 2026년 11월 16일 판사가 모든 혐의에 무죄 판결",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinDesk, Williams & Connolly, The Block")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Quote card: Judge Jessica Clarke wrote of Ethereum, it is a trustless, highly adversarial environment with no terms of use", {
            "es": "Tarjeta con cita: la jueza Jessica Clarke escribió sobre Ethereum que es un entorno sin confianza, muy hostil y sin condiciones de uso",
            "pt": "Cartão com citação: a juíza Jessica Clarke escreveu sobre o Ethereum que é um ambiente sem confiança, altamente adversarial e sem termos de uso",
            "fr": "Citation : la juge Jessica Clarke a écrit à propos d'Ethereum qu'il s'agit d'un environnement sans tiers de confiance, très conflictuel et sans conditions d'utilisation",
            "de": "Zitatkarte: Richterin Jessica Clarke schrieb über Ethereum, es sei eine vertrauenslose, äußerst konfrontative Umgebung ohne Nutzungsbedingungen",
            "ru": "Карточка с цитатой: судья Джессика Кларк написала об Ethereum, что это среда без доверия, крайне враждебная и без условий использования",
            "tr": "Alıntı kartı: Hâkim Jessica Clarke, Ethereum için güven gerektirmeyen, son derece çekişmeli ve kullanım koşulları olmayan bir ortam olduğunu yazdı",
            "id": "Kartu kutipan: Hakim Jessica Clarke menulis bahwa Ethereum adalah lingkungan tanpa kepercayaan, sangat penuh persaingan, dan tanpa syarat penggunaan",
            "ja": "引用カード：ジェシカ・クラーク判事はイーサリアムについて、信頼を前提としない、極めて敵対的で利用規約のない環境だと記した",
            "ko": "인용 카드: 제시카 클라크 판사는 이더리움에 대해 신뢰가 필요 없고 매우 적대적이며 이용 약관이 없는 환경이라고 썼다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="U.S. District Court for the Southern District of New York, via CoinDesk")},
    ]


def build_cftc_backpack():
    slug = "cftc-approves-backpack-blockchain-derivatives-exchange-nov-2026"
    d = OUT / slug
    # CFTC: Selig statement Nov 16, 2026; TLD Clearing DCO order Nov 13, 2026. tZERO press release Nov 11, 2026.
    tl = make_timeline_card(
        d / "timeline-cftc-backpack-tzero",
        "CFTC approvals (Oct. to Nov. 2026)",
        [
            ("Oct. 16", "tZERO clearinghouse registered (DCO)", (96, 165, 250)),
            ("Nov. 10", "tZERO exchange designated (DCM)", (96, 165, 250)),
            ("Nov. 13", "Backpack Clearing registered (DCO)", (247, 147, 26)),
            ("Nov. 16", "Backpack Exchange designated (DCM)", (74, 222, 128)),
        ],
        footer="CFTC, tZERO, Backpack, Nov. 2026",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-selig-milestone",
        "CFTC Chairman Michael Selig, Nov. 16",
        "\u201cAn important milestone\u201d",
        "Blockchain-based firms must meet the same standards as traditional exchanges: anti-money laundering, customer protection, surveillance, risk management",
        footer="CFTC statement, Nov. 16, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of CFTC approvals: Oct. 16, tZERO's clearinghouse is registered as a DCO; Nov. 10, tZERO's exchange is designated as a DCM; Nov. 13, Backpack Clearing is registered as a DCO; Nov. 16, Backpack Exchange is designated as a DCM", {
            "es": "Cronología de las aprobaciones de la CFTC: 16 de octubre, la cámara de compensación de tZERO se registra como DCO; 10 de noviembre, la bolsa de tZERO recibe la designación DCM; 13 de noviembre, Backpack Clearing se registra como DCO; 16 de noviembre, Backpack Exchange recibe la designación DCM",
            "pt": "Linha do tempo das aprovações da CFTC: 16 de outubro, a câmara de compensação da tZERO é registrada como DCO; 10 de novembro, a bolsa da tZERO recebe a designação DCM; 13 de novembro, a Backpack Clearing é registrada como DCO; 16 de novembro, a Backpack Exchange recebe a designação DCM",
            "fr": "Chronologie des feux verts de la CFTC : 16 octobre, la chambre de compensation de tZERO est enregistrée comme DCO ; 10 novembre, la plateforme de tZERO est désignée DCM ; 13 novembre, Backpack Clearing est enregistrée comme DCO ; 16 novembre, Backpack Exchange est désignée DCM",
            "de": "Zeitleiste der CFTC-Zulassungen: 16. Oktober, die Clearingstelle von tZERO wird als DCO registriert; 10. November, die Börse von tZERO wird als DCM zugelassen; 13. November, Backpack Clearing wird als DCO registriert; 16. November, Backpack Exchange wird als DCM zugelassen",
            "ru": "Хронология одобрений CFTC: 16 октября клиринговая палата tZERO зарегистрирована как DCO; 10 ноября биржа tZERO получила статус DCM; 13 ноября Backpack Clearing зарегистрирована как DCO; 16 ноября Backpack Exchange получила статус DCM",
            "tr": "CFTC onaylarının zaman çizelgesi: 16 Ekim, tZERO'nun takas kuruluşu DCO olarak kaydedildi; 10 Kasım, tZERO'nun borsası DCM olarak belirlendi; 13 Kasım, Backpack Clearing DCO olarak kaydedildi; 16 Kasım, Backpack Exchange DCM olarak belirlendi",
            "id": "Linimasa persetujuan CFTC: 16 Oktober, lembaga kliring tZERO terdaftar sebagai DCO; 10 November, bursa tZERO ditetapkan sebagai DCM; 13 November, Backpack Clearing terdaftar sebagai DCO; 16 November, Backpack Exchange ditetapkan sebagai DCM",
            "ja": "CFTCの承認の時系列：10月16日、tZEROの清算機関がDCOとして登録、11月10日、tZEROの取引所がDCMに指定、11月13日、Backpack ClearingがDCOとして登録、11月16日、Backpack ExchangeがDCMに指定",
            "ko": "CFTC 승인 타임라인: 10월 16일 tZERO 청산소 DCO 등록, 11월 10일 tZERO 거래소 DCM 지정, 11월 13일 Backpack Clearing DCO 등록, 11월 16일 Backpack Exchange DCM 지정",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CFTC, tZERO, Backpack")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: CFTC Chairman Michael Selig called the approvals an important milestone and said blockchain-based firms must meet the same standards as traditional exchanges, including anti-money laundering, customer protection, surveillance and risk management", {
            "es": "Tarjeta de datos: el presidente de la CFTC, Michael Selig, calificó las aprobaciones de hito importante y dijo que las firmas basadas en blockchain deben cumplir los mismos estándares que las bolsas tradicionales, incluidos prevención del blanqueo, protección del cliente, vigilancia y gestión de riesgos",
            "pt": "Cartão de dados: o presidente da CFTC, Michael Selig, chamou as aprovações de marco importante e disse que empresas baseadas em blockchain precisam cumprir os mesmos padrões das bolsas tradicionais, incluindo prevenção à lavagem de dinheiro, proteção ao cliente, vigilância e gestão de riscos",
            "fr": "Fiche chiffre : le président de la CFTC, Michael Selig, a qualifié ces feux verts d'étape importante et rappelé que les acteurs fondés sur la blockchain doivent respecter les mêmes règles que les places traditionnelles : lutte contre le blanchiment, protection des clients, surveillance et gestion des risques",
            "de": "Faktenkarte: CFTC-Chef Michael Selig nannte die Zulassungen einen wichtigen Meilenstein und sagte, Blockchain-Firmen müssten dieselben Standards erfüllen wie klassische Börsen, darunter Geldwäscheprävention, Kundenschutz, Marktüberwachung und Risikomanagement",
            "ru": "Карточка: председатель CFTC Майкл Селиг назвал одобрения важной вехой и подчеркнул, что компании на блокчейне должны соответствовать тем же стандартам, что и традиционные биржи, включая противодействие отмыванию денег, защиту клиентов, надзор за рынком и управление рисками",
            "tr": "Bilgi kartı: CFTC Başkanı Michael Selig onayları önemli bir dönüm noktası olarak nitelendirdi ve blokzincir tabanlı firmaların kara para aklamayla mücadele, müşteri koruma, piyasa gözetimi ve risk yönetimi dahil geleneksel borsalarla aynı standartları karşılaması gerektiğini söyledi",
            "id": "Kartu fakta: Ketua CFTC Michael Selig menyebut persetujuan ini tonggak penting dan mengatakan perusahaan berbasis blockchain harus memenuhi standar yang sama dengan bursa tradisional, termasuk anti pencucian uang, perlindungan nasabah, pengawasan pasar, dan manajemen risiko",
            "ja": "ファクトカード：CFTCのマイケル・セリグ委員長は今回の承認を重要な節目と呼び、ブロックチェーンを使う企業もマネーロンダリング対策、顧客保護、市場監視、リスク管理など従来の取引所と同じ基準を満たす必要があると述べた",
            "ko": "팩트 카드: 마이클 셀리그 CFTC 위원장은 이번 승인을 중요한 이정표라고 부르며, 블록체인 기반 기업도 자금세탁 방지, 고객 보호, 시장 감시, 리스크 관리 등 기존 거래소와 같은 기준을 충족해야 한다고 밝혔다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CFTC")},
    ]


def build_banks_btc_etf_13f():
    slug = "goldman-wells-fargo-double-bitcoin-etf-holdings-13f-nov-2026"
    d = OUT / slug
    # 13F figures as reported by Bitcoin Magazine (Goldman, five spot bitcoin funds, long) and CoinDesk (Wells Fargo, IBIT), Nov 17, 2026.
    chart = make_bar_chart(
        d / "chart-banks-13f-bitcoin-etf",
        ["Goldman Sachs\nJune 30", "Goldman Sachs\nSept. 30", "Wells Fargo (IBIT)\nJune 30", "Wells Fargo (IBIT)\nSept. 30"],
        [580, 1283, 812, 2350],
        "Reported spot bitcoin ETF holdings in 13F filings (US$ millions)",
        colors=["#64748b", "#f7931a", "#64748b", "#f7931a"],
    )
    # Farside Investors, U.S. spot bitcoin ETF daily net flows (US$m), read Nov 17, 2026.
    days = ["Oct 30", "Nov 2", "Nov 3", "Nov 4", "Nov 5", "Nov 6", "Nov 9", "Nov 10", "Nov 11", "Nov 12", "Nov 13", "Nov 16"]
    flows = [-643.2, -398.6, -115.6, 74.6, -430.2, -411.9, -201.0, -95.0, -299.8, -284.1, -185.4, 7.9]
    flows_img = make_bar_chart(
        d / "chart-btc-etf-flows-oct30-nov16",
        days, flows,
        "U.S. spot bitcoin ETF daily net flows (US$ millions)",
        colors=["#34d399" if v > 0 else "#f87171" for v in flows],
        value_fmt=lambda v: f"{v:+,.1f}",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of reported spot bitcoin ETF holdings in 13F filings: Goldman Sachs about $580 million on June 30 and $1.283 billion on Sept. 30, 2026; Wells Fargo's BlackRock IBIT stake about $812 million on June 30 and $2.35 billion on Sept. 30", {
            "es": "Gráfico de barras de las participaciones en ETF de bitcoin al contado declaradas en los formularios 13F: Goldman Sachs, unos 580 millones de dólares el 30 de junio y 1.283 millones el 30 de septiembre de 2026; la posición de Wells Fargo en el IBIT de BlackRock, unos 812 millones el 30 de junio y 2.350 millones el 30 de septiembre",
            "pt": "Gráfico de barras das posições em ETFs de bitcoin à vista declaradas nos formulários 13F: Goldman Sachs, cerca de US$ 580 milhões em 30 de junho e US$ 1,283 bilhão em 30 de setembro de 2026; a posição do Wells Fargo no IBIT da BlackRock, cerca de US$ 812 milhões em 30 de junho e US$ 2,35 bilhões em 30 de setembro",
            "fr": "Diagramme en barres des positions en ETF bitcoin au comptant déclarées dans les formulaires 13F : Goldman Sachs, environ 580 millions de dollars au 30 juin et 1,283 milliard au 30 septembre 2026 ; la position de Wells Fargo dans l'IBIT de BlackRock, environ 812 millions au 30 juin et 2,35 milliards au 30 septembre",
            "de": "Balkendiagramm der in 13F-Meldungen ausgewiesenen Spot-Bitcoin-ETF-Bestände: Goldman Sachs rund 580 Mio. $ am 30. Juni und 1,283 Mrd. $ am 30. September 2026; die Position von Wells Fargo im IBIT von BlackRock rund 812 Mio. $ am 30. Juni und 2,35 Mrd. $ am 30. September",
            "ru": "Столбчатая диаграмма вложений в спотовые биткоин-ETF по отчетам 13F: Goldman Sachs, около $580 млн на 30 июня и $1,283 млрд на 30 сентября 2026 года; позиция Wells Fargo в IBIT от BlackRock, около $812 млн на 30 июня и $2,35 млрд на 30 сентября",
            "tr": "13F bildirimlerinde yer alan spot bitcoin ETF varlıklarının çubuk grafiği: Goldman Sachs 30 Haziran'da yaklaşık 580 milyon $, 30 Eylül 2026'da 1,283 milyar $; Wells Fargo'nun BlackRock IBIT pozisyonu 30 Haziran'da yaklaşık 812 milyon $, 30 Eylül'de 2,35 milyar $",
            "id": "Grafik batang kepemilikan ETF bitcoin spot yang dilaporkan dalam formulir 13F: Goldman Sachs sekitar US$580 juta pada 30 Juni dan US$1,283 miliar pada 30 September 2026; posisi Wells Fargo di IBIT milik BlackRock sekitar US$812 juta pada 30 Juni dan US$2,35 miliar pada 30 September",
            "ja": "13F報告書に記載された現物ビットコインETF保有額の棒グラフ：ゴールドマン・サックスは6月30日時点で約5億8000万ドル、2026年9月30日時点で12億8300万ドル、ウェルズ・ファーゴのブラックロックIBIT保有は6月30日時点で約8億1200万ドル、9月30日時点で23億5000万ドル",
            "ko": "13F 보고서에 기재된 현물 비트코인 ETF 보유액 막대 차트: 골드만삭스 6월 30일 약 5억8000만 달러, 2026년 9월 30일 12억8300만 달러, 웰스파고의 블랙록 IBIT 보유액 6월 30일 약 8억1200만 달러, 9월 30일 23억5000만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="13F filings via Bitcoin Magazine, CoinDesk")},
        {"id": "flows", "file": flows_img.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of U.S. spot bitcoin ETF daily net flows from Oct. 30 to Nov. 16, 2026, per Farside Investors: outflows on 10 of 12 trading days, the largest $643.2 million on Oct. 30, small inflows of $74.6 million on Nov. 4 and $7.9 million on Nov. 16", {
            "es": "Gráfico de barras de los flujos netos diarios de los ETF de bitcoin al contado de EE. UU. del 30 de octubre al 16 de noviembre de 2026, según Farside Investors: salidas en 10 de 12 sesiones, la mayor de 643,2 millones de dólares el 30 de octubre, y pequeñas entradas de 74,6 millones el 4 de noviembre y 7,9 millones el 16 de noviembre",
            "pt": "Gráfico de barras dos fluxos líquidos diários dos ETFs de bitcoin à vista dos EUA de 30 de outubro a 16 de novembro de 2026, segundo a Farside Investors: saídas em 10 de 12 pregões, a maior de US$ 643,2 milhões em 30 de outubro, e pequenas entradas de US$ 74,6 milhões em 4 de novembro e US$ 7,9 milhões em 16 de novembro",
            "fr": "Diagramme en barres des flux nets quotidiens des ETF bitcoin au comptant américains du 30 octobre au 16 novembre 2026, selon Farside Investors : sorties sur 10 séances sur 12, la plus forte de 643,2 millions de dollars le 30 octobre, petites entrées de 74,6 millions le 4 novembre et de 7,9 millions le 16 novembre",
            "de": "Balkendiagramm der täglichen Nettozuflüsse der US-Spot-Bitcoin-ETFs vom 30. Oktober bis 16. November 2026 laut Farside Investors: Abflüsse an 10 von 12 Handelstagen, der größte mit 643,2 Mio. $ am 30. Oktober, kleine Zuflüsse von 74,6 Mio. $ am 4. November und 7,9 Mio. $ am 16. November",
            "ru": "Столбчатая диаграмма ежедневных чистых потоков американских спотовых биткоин-ETF с 30 октября по 16 ноября 2026 года по данным Farside Investors: оттоки в 10 из 12 торговых дней, крупнейший $643,2 млн 30 октября, небольшие притоки $74,6 млн 4 ноября и $7,9 млн 16 ноября",
            "tr": "Farside Investors verilerine göre 30 Ekim-16 Kasım 2026 arasında ABD spot bitcoin ETF'lerinin günlük net akışlarının çubuk grafiği: 12 işlem gününün 10'unda çıkış, en büyüğü 30 Ekim'de 643,2 milyon $, 4 Kasım'da 74,6 milyon $ ve 16 Kasım'da 7,9 milyon $ küçük girişler",
            "id": "Grafik batang arus bersih harian ETF bitcoin spot AS dari 30 Oktober hingga 16 November 2026 menurut Farside Investors: arus keluar pada 10 dari 12 hari perdagangan, terbesar US$643,2 juta pada 30 Oktober, arus masuk kecil US$74,6 juta pada 4 November dan US$7,9 juta pada 16 November",
            "ja": "Farside Investorsによる2026年10月30日～11月16日の米国現物ビットコインETFの日次純流出入の棒グラフ：12営業日中10日で流出、最大は10月30日の6億4320万ドル、11月4日に7460万ドル、11月16日に790万ドルの小幅流入",
            "ko": "Farside Investors 기준 2026년 10월 30일~11월 16일 미국 현물 비트코인 ETF 일별 순유출입 막대 차트: 12거래일 중 10일 순유출, 최대는 10월 30일 6억4320만 달러, 11월 4일 7460만 달러와 11월 16일 790만 달러 소폭 순유입",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
    ]


def build_fed_minutes_btc_63k():
    slug = "fed-minutes-more-rate-hikes-bitcoin-below-63000-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 16 00:00 UTC to Nov 18 19:00 UTC (1 p.m. CST, minutes release). Nov 18 low $62,212.70 (16:00 UTC hour).
    xs, ys = fetch_kraken_hourly(1794787200, 1795028400, pair="XBTUSD")
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-16-18",
        xs, ys,
        title="Bitcoin hourly price, Nov. 16-18, 2026 (Kraken, UTC)",
        hline=62212.7,
        hlabel="Nov. 18 low ≈ $62,213 (Kraken)",
    )
    # Minutes of the FOMC meeting of Oct. 27-28, 2026, released Nov. 18, 2026.
    fact = make_fact_card(
        d / "fact-almost-all-participants",
        "Fed minutes, Oct. 27-28 meeting",
        "\u201cAlmost all\u201d",
        "participants judged that further action to raise the federal funds rate would likely be appropriate.",
        footer="Federal Reserve, FOMC minutes released Nov. 18, 2026",
    )
    # Farside Investors, U.S. spot bitcoin ETF daily net flows (US$m), read Nov 18, 2026.
    days = ["Oct 30", "Nov 2", "Nov 3", "Nov 4", "Nov 5", "Nov 6", "Nov 9", "Nov 10", "Nov 11", "Nov 12", "Nov 13", "Nov 16", "Nov 17"]
    flows = [-643.2, -398.6, -115.6, 74.6, -430.2, -411.9, -201.0, -95.0, -299.8, -284.1, -185.4, 7.9, -239.9]
    flows_img = make_bar_chart(
        d / "chart-btc-etf-flows-oct30-nov17",
        days, flows,
        "U.S. spot bitcoin ETF daily net flows (US$ millions)",
        colors=["#34d399" if v > 0 else "#f87171" for v in flows],
        value_fmt=lambda v: f"{v:+,.1f}",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 16 to Nov. 18, 2026, sliding from about $65,000 to below $63,000, with a dashed line at the Nov. 18 low of about $62,213", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 16 al 18 de noviembre de 2026: baja de unos 65.000 dólares a menos de 63.000, con una línea discontinua en el mínimo del 18 de noviembre, de unos 62.213 dólares",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 16 a 18 de novembro de 2026: cai de cerca de US$ 65.000 para menos de US$ 63.000, com uma linha tracejada na mínima de 18 de novembro, de cerca de US$ 62.213",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 16 au 18 novembre 2026 : il glisse d'environ 65 000 dollars à moins de 63 000 dollars, avec une ligne pointillée au plus bas du 18 novembre, environ 62 213 dollars",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 16. bis 18. November 2026: Rückgang von rund 65.000 $ auf unter 63.000 $; gestrichelte Linie beim Tief vom 18. November von rund 62.213 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 16 по 18 ноября 2026 года: снижение примерно с $65 000 до уровня ниже $63 000; пунктирная линия показывает минимум 18 ноября, около $62 213",
            "tr": "Bitcoin'in 16-18 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 65.000 $'dan 63.000 $'ın altına geriliyor; kesikli çizgi 18 Kasım'daki yaklaşık 62.213 $'lık dibi gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 16 hingga 18 November 2026: turun dari sekitar US$65.000 ke bawah US$63.000, dengan garis putus-putus di level terendah 18 November sekitar US$62.213",
            "ja": "2026年11月16〜18日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約6万5000ドルから6万3000ドル割れへ下落。破線は11月18日の安値（約6万2213ドル）",
            "ko": "2026년 11월 16~18일 크라켄 비트코인 시간별 가격 선 차트: 약 6만 5,000달러에서 6만 3,000달러 아래로 하락, 점선은 11월 18일 저점 약 6만 2,213달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card quoting the Fed minutes from the Oct. 27-28, 2026 meeting: almost all participants judged that further action to raise the federal funds rate would likely be appropriate", {
            "es": "Tarjeta con una cita de las actas de la Fed de la reunión del 27 y 28 de octubre de 2026: casi todos los participantes consideraron que probablemente sería apropiado volver a subir la tasa de fondos federales",
            "pt": "Cartão com trecho da ata do Fed da reunião de 27 e 28 de outubro de 2026: quase todos os participantes avaliaram que novas altas da taxa básica provavelmente seriam apropriadas",
            "fr": "Carte citant le compte rendu de la Fed sur la réunion des 27 et 28 octobre 2026 : presque tous les participants ont jugé que de nouvelles hausses du taux directeur seraient probablement appropriées",
            "de": "Faktenkarte mit einem Zitat aus dem Fed-Protokoll der Sitzung vom 27. und 28. Oktober 2026: Fast alle Teilnehmer hielten weitere Anhebungen des Leitzinses für wahrscheinlich angemessen",
            "ru": "Карточка с цитатой из протокола заседания ФРС 27–28 октября 2026 года: почти все участники сочли, что дальнейшее повышение ставки по федеральным фондам, вероятно, будет уместным",
            "tr": "Fed'in 27-28 Ekim 2026 toplantı tutanaklarından alıntı içeren kart: katılımcıların neredeyse tamamı federal fon faizinin yeniden artırılmasının muhtemelen uygun olacağı görüşündeydi",
            "id": "Kartu kutipan risalah rapat Fed 27-28 Oktober 2026: hampir semua peserta menilai kenaikan suku bunga acuan lebih lanjut kemungkinan akan tepat",
            "ja": "2026年10月27〜28日のFOMC議事要旨を引用したカード：ほぼすべての参加者が、追加の利上げがおそらく適切になると判断した",
            "ko": "2026년 10월 27~28일 FOMC 의사록 인용 카드: 거의 모든 참석자가 추가 기준금리 인상이 적절할 가능성이 높다고 판단했다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Federal Reserve, FOMC minutes (Oct. 27-28, 2026)")},
        {"id": "flows", "file": flows_img.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of U.S. spot bitcoin ETF daily net flows from Oct. 30 to Nov. 17, 2026, per Farside Investors: outflows on 11 of 13 trading days, the largest $643.2 million on Oct. 30, and $239.9 million out on Nov. 17", {
            "es": "Gráfico de barras de los flujos netos diarios de los ETF de bitcoin al contado de EE. UU. del 30 de octubre al 17 de noviembre de 2026, según Farside Investors: salidas en 11 de 13 sesiones, la mayor de 643,2 millones de dólares el 30 de octubre, y 239,9 millones de salidas el 17 de noviembre",
            "pt": "Gráfico de barras dos fluxos líquidos diários dos ETFs de bitcoin à vista dos EUA de 30 de outubro a 17 de novembro de 2026, segundo a Farside Investors: saídas em 11 de 13 pregões, a maior de US$ 643,2 milhões em 30 de outubro, e saídas de US$ 239,9 milhões em 17 de novembro",
            "fr": "Diagramme en barres des flux nets quotidiens des ETF bitcoin au comptant américains du 30 octobre au 17 novembre 2026, selon Farside Investors : sorties sur 11 séances sur 13, la plus forte de 643,2 millions de dollars le 30 octobre, et 239,9 millions de sorties le 17 novembre",
            "de": "Balkendiagramm der täglichen Nettozuflüsse der US-Spot-Bitcoin-ETFs vom 30. Oktober bis 17. November 2026 laut Farside Investors: Abflüsse an 11 von 13 Handelstagen, der größte mit 643,2 Mio. $ am 30. Oktober, und 239,9 Mio. $ Abfluss am 17. November",
            "ru": "Столбчатая диаграмма ежедневных чистых потоков американских спотовых биткоин-ETF с 30 октября по 17 ноября 2026 года по данным Farside Investors: оттоки в 11 из 13 торговых дней, крупнейший $643,2 млн 30 октября, отток $239,9 млн 17 ноября",
            "tr": "Farside Investors verilerine göre 30 Ekim-17 Kasım 2026 arasında ABD spot bitcoin ETF'lerinin günlük net akışlarının çubuk grafiği: 13 işlem gününün 11'inde çıkış, en büyüğü 30 Ekim'de 643,2 milyon $, 17 Kasım'da 239,9 milyon $ çıkış",
            "id": "Grafik batang arus bersih harian ETF bitcoin spot AS dari 30 Oktober hingga 17 November 2026 menurut Farside Investors: arus keluar pada 11 dari 13 hari perdagangan, terbesar US$643,2 juta pada 30 Oktober, dan arus keluar US$239,9 juta pada 17 November",
            "ja": "Farside Investorsによる2026年10月30日～11月17日の米国現物ビットコインETFの日次純流出入の棒グラフ：13営業日中11日で流出、最大は10月30日の6億4320万ドル、11月17日は2億3990万ドルの流出",
            "ko": "Farside Investors 기준 2026년 10월 30일~11월 17일 미국 현물 비트코인 ETF 일별 순유출입 막대 차트: 13거래일 중 11일 순유출, 최대는 10월 30일 6억4320만 달러, 11월 17일 2억3990만 달러 순유출",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
    ]


def build_binance_adgm_order():
    slug = "binance-abu-dhabi-court-order-frozen-hack-funds-nov-2026"
    d = OUT / slug
    # Binance incident report figures via Bitcoin Magazine (Nov 18, 2026): $6.34B affected, ~$2.85B frozen/intercepted;
    # Tether froze >$1.5B USDT, Circle ~ $1.1B USDC (as reported by Bitcoin Magazine).
    chart = make_bar_chart(
        d / "chart-binance-hack-frozen",
        ["Assets affected\n(Binance)", "Frozen or intercepted\n(Binance)", "USDT frozen\n(Tether)", "USDC frozen\n(Circle)"],
        [6.34, 2.85, 1.5, 1.1],
        "Binance hack: stolen vs. frozen (US$ billions)",
        colors=["#f87171", "#34d399", "#64748b", "#64748b"],
        value_fmt=lambda v: {6.34: "$6.34B", 2.85: "~$2.85B", 1.5: "$1.5B+", 1.1: "~$1.1B"}[v],
        axis_fmt=lambda x, _p: f"${x:,.0f}B",
    )
    tl = make_timeline_card(
        d / "timeline-binance-hack-recovery",
        "Binance hack: the fight over the money",
        [
            ("Oct. 29", "Hackers drain about $6.3 billion from Binance hot wallets", (248, 113, 113)),
            ("Nov. 12", "DOJ gets court authority to seize or restrain more than $1.2 billion", (96, 165, 250)),
            ("Nov. 17", "Hack-linked wallets move 74,880 ETH, about $136.8 million", (248, 113, 113)),
            ("Nov. 18", "Binance says it has an Abu Dhabi court order to recover frozen funds", GREEN),
        ],
        footer="Reuters · U.S. Justice Department · Decrypt (Arkham data)",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-74880-eth-moved",
        "Hack-linked wallets on Nov. 17",
        "74,880 ETH",
        "About $136.8 million moved in roughly three hours; some was swapped for bitcoin through THORChain.",
        footer="Arkham data via Decrypt · Nov. 17, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of the Binance hack: $6.34 billion in assets affected and about $2.85 billion frozen or intercepted, according to Binance; Tether froze more than $1.5 billion in USDT and Circle about $1.1 billion in USDC", {
            "es": "Gráfico de barras del hackeo de Binance: 6.340 millones de dólares en activos afectados y unos 2.850 millones congelados o interceptados, según Binance; Tether congeló más de 1.500 millones en USDT y Circle unos 1.100 millones en USDC",
            "pt": "Gráfico de barras do ataque à Binance: US$ 6,34 bilhões em ativos afetados e cerca de US$ 2,85 bilhões congelados ou interceptados, segundo a Binance; a Tether congelou mais de US$ 1,5 bilhão em USDT e a Circle cerca de US$ 1,1 bilhão em USDC",
            "fr": "Diagramme en barres du piratage de Binance : 6,34 milliards de dollars d'actifs touchés et environ 2,85 milliards gelés ou interceptés, selon Binance ; Tether a gelé plus de 1,5 milliard en USDT et Circle environ 1,1 milliard en USDC",
            "de": "Balkendiagramm zum Binance-Hack: 6,34 Mrd. $ betroffene Vermögenswerte und rund 2,85 Mrd. $ eingefroren oder abgefangen, laut Binance; Tether fror mehr als 1,5 Mrd. $ in USDT ein, Circle rund 1,1 Mrd. $ in USDC",
            "ru": "Столбчатая диаграмма по взлому Binance: затронуто активов на $6,34 млрд, около $2,85 млрд заморожено или перехвачено, по данным Binance; Tether заморозила более $1,5 млрд в USDT, Circle — около $1,1 млрд в USDC",
            "tr": "Binance saldırısının çubuk grafiği: Binance'e göre 6,34 milyar $ varlık etkilendi, yaklaşık 2,85 milyar $ donduruldu ya da yolda durduruldu; Tether 1,5 milyar $'ın üzerinde USDT, Circle yaklaşık 1,1 milyar $ USDC dondurdu",
            "id": "Grafik batang peretasan Binance: aset terdampak US$6,34 miliar dan sekitar US$2,85 miliar dibekukan atau dicegat, menurut Binance; Tether membekukan lebih dari US$1,5 miliar USDT dan Circle sekitar US$1,1 miliar USDC",
            "ja": "バイナンスのハッキングに関する棒グラフ：バイナンスによると影響を受けた資産は63億4000万ドル、凍結または差し止められたのは約28億5000万ドル。テザーは15億ドル超のUSDT、サークルは約11億ドルのUSDCを凍結",
            "ko": "바이낸스 해킹 막대 차트: 바이낸스에 따르면 피해 자산 63억4000만 달러, 동결 또는 차단 약 28억5000만 달러; 테더는 15억 달러 이상의 USDT, 서클은 약 11억 달러의 USDC를 동결",
         }),
         "caption": tr_map(CAPTION_CHART, src="Binance incident report via Bitcoin Magazine")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Oct. 29, hackers drain about $6.3 billion from Binance hot wallets; Nov. 12, the U.S. Justice Department gets court authority to seize or restrain more than $1.2 billion; Nov. 17, hack-linked wallets move 74,880 ETH, about $136.8 million; Nov. 18, Binance says it has an Abu Dhabi court order to recover frozen funds", {
            "es": "Cronología: 29 de oct., los hackers vacían unos 6.300 millones de dólares de las billeteras calientes de Binance; 12 de nov., el Departamento de Justicia de EE. UU. obtiene autorización judicial para incautar o bloquear más de 1.200 millones; 17 de nov., billeteras vinculadas al hackeo mueven 74.880 ETH, unos 136,8 millones; 18 de nov., Binance dice tener una orden judicial de Abu Dabi para recuperar fondos congelados",
            "pt": "Linha do tempo: 29 de out., hackers esvaziam cerca de US$ 6,3 bilhões das carteiras quentes da Binance; 12 de nov., o Departamento de Justiça dos EUA obtém autorização judicial para apreender ou bloquear mais de US$ 1,2 bilhão; 17 de nov., carteiras ligadas ao ataque movem 74.880 ETH, cerca de US$ 136,8 milhões; 18 de nov., a Binance diz ter uma ordem judicial de Abu Dhabi para recuperar fundos congelados",
            "fr": "Chronologie : 29 oct., des pirates vident environ 6,3 milliards de dollars des portefeuilles chauds de Binance ; 12 nov., le ministère américain de la Justice obtient l'autorisation de saisir ou bloquer plus de 1,2 milliard ; 17 nov., des portefeuilles liés au piratage déplacent 74 880 ETH, environ 136,8 millions ; 18 nov., Binance dit disposer d'une ordonnance d'un tribunal d'Abou Dhabi pour récupérer des fonds gelés",
            "de": "Zeitleiste: 29. Okt., Hacker räumen rund 6,3 Mrd. $ aus Binances Hot Wallets ab; 12. Nov., das US-Justizministerium erhält die gerichtliche Befugnis, mehr als 1,2 Mrd. $ zu beschlagnahmen oder zu sperren; 17. Nov., mit dem Hack verknüpfte Wallets bewegen 74.880 ETH, rund 136,8 Mio. $; 18. Nov., Binance meldet einen Gerichtsbeschluss aus Abu Dhabi zur Rückholung eingefrorener Gelder",
            "ru": "Хронология: 29 октября хакеры выводят около $6,3 млрд из горячих кошельков Binance; 12 ноября Минюст США получает судебное разрешение изъять или заблокировать более $1,2 млрд; 17 ноября связанные со взломом кошельки перемещают 74 880 ETH, около $136,8 млн; 18 ноября Binance сообщает о судебном приказе в Абу-Даби для возврата замороженных средств",
            "tr": "Zaman çizelgesi: 29 Ekim, bilgisayar korsanları Binance'in sıcak cüzdanlarından yaklaşık 6,3 milyar $ çekiyor; 12 Kasım, ABD Adalet Bakanlığı 1,2 milyar $'ın üzerinde varlığa el koyma ya da dondurma yetkisi alıyor; 17 Kasım, saldırıyla bağlantılı cüzdanlar 74.880 ETH, yaklaşık 136,8 milyon $ taşıyor; 18 Kasım, Binance dondurulan fonları geri almak için Abu Dabi'den mahkeme kararı aldığını söylüyor",
            "id": "Linimasa: 29 Okt., peretas menguras sekitar US$6,3 miliar dari dompet panas Binance; 12 Nov., Departemen Kehakiman AS mendapat izin pengadilan untuk menyita atau membekukan lebih dari US$1,2 miliar; 17 Nov., dompet terkait peretasan memindahkan 74.880 ETH, sekitar US$136,8 juta; 18 Nov., Binance mengaku mendapat perintah pengadilan Abu Dhabi untuk memulihkan dana yang dibekukan",
            "ja": "時系列：10月29日、ハッカーがバイナンスのホットウォレットから約63億ドルを流出させる。11月12日、米司法省が12億ドル超の押収・凍結について裁判所の許可を得る。11月17日、ハッキング関連のウォレットが7万4880ETH（約1億3680万ドル）を移動。11月18日、バイナンスが凍結資金の回収に向けアブダビの裁判所命令を得たと発表",
            "ko": "타임라인: 10월 29일 해커가 바이낸스 핫월렛에서 약 63억 달러 탈취; 11월 12일 미 법무부가 12억 달러 이상 압수·동결에 대한 법원 승인 확보; 11월 17일 해킹 연루 지갑이 7만4880 ETH(약 1억3680만 달러) 이동; 11월 18일 바이낸스가 동결 자금 회수를 위한 아부다비 법원 명령을 받았다고 발표",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Reuters, U.S. Justice Department, Decrypt")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: on Nov. 17, 2026, wallets linked to the Binance hack moved 74,880 ETH, about $136.8 million, in roughly three hours, and some was swapped for bitcoin through THORChain", {
            "es": "Tarjeta: el 17 de noviembre de 2026, billeteras vinculadas al hackeo de Binance movieron 74.880 ETH, unos 136,8 millones de dólares, en unas tres horas, y parte se cambió por bitcoin a través de THORChain",
            "pt": "Cartão: em 17 de novembro de 2026, carteiras ligadas ao ataque à Binance movimentaram 74.880 ETH, cerca de US$ 136,8 milhões, em umas três horas, e parte foi trocada por bitcoin via THORChain",
            "fr": "Carte : le 17 novembre 2026, des portefeuilles liés au piratage de Binance ont déplacé 74 880 ETH, environ 136,8 millions de dollars, en trois heures environ, et une partie a été échangée contre du bitcoin via THORChain",
            "de": "Faktenkarte: Am 17. November 2026 bewegten mit dem Binance-Hack verknüpfte Wallets binnen rund drei Stunden 74.880 ETH, etwa 136,8 Mio. $; ein Teil wurde über THORChain in Bitcoin getauscht",
            "ru": "Карточка: 17 ноября 2026 года связанные со взломом Binance кошельки примерно за три часа переместили 74 880 ETH, около $136,8 млн, часть обменяли на биткоин через THORChain",
            "tr": "Kart: 17 Kasım 2026'da Binance saldırısıyla bağlantılı cüzdanlar yaklaşık üç saatte 74.880 ETH, yani yaklaşık 136,8 milyon $ taşıdı; bir kısmı THORChain üzerinden bitcoine çevrildi",
            "id": "Kartu: pada 17 November 2026, dompet terkait peretasan Binance memindahkan 74.880 ETH, sekitar US$136,8 juta, dalam kira-kira tiga jam, dan sebagian ditukar ke bitcoin lewat THORChain",
            "ja": "カード：2026年11月17日、バイナンスのハッキングに関連するウォレットが約3時間で7万4880ETH（約1億3680万ドル）を移動し、一部はTHORChainを通じてビットコインに交換された",
            "ko": "카드: 2026년 11월 17일 바이낸스 해킹 연루 지갑이 약 3시간 동안 7만4880 ETH(약 1억3680만 달러)를 옮겼고, 일부는 THORChain을 통해 비트코인으로 교환됐다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Arkham data via Decrypt")},
    ]


def build_ledger_berlin_dubai():
    slug = "ledger-tampered-wallets-berlin-dubai-nov-2026"
    d = OUT / slug
    # Ledger blog Oct 15, 2026; Ledger Implant OSINT reports (Nov 16-18, 2026); Ledger support update Nov 18, 2026 via Decrypt/CyberSIXT.
    tl = make_timeline_card(
        d / "timeline-ledger-implant-cases",
        "Ledger implant attack: how it spread",
        [
            ("Oct. 15", "Ledger discloses tampered devices sold via Southeast Asian resellers", (96, 165, 250)),
            ("Nov. 14", "Owner reports 507,000 USDT drained from a Ledger Stax bought in Dubai", (248, 113, 113)),
            ("Nov. 16", "Photos show an implant in a Ledger Flex bought in Dubai, per tracker", (248, 113, 113)),
            ("Nov. 18", "Ledger confirms tampered units in Berlin, probes two in Dubai", GREEN),
        ],
        footer="Ledger · Ledger Implant OSINT · Decrypt",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-ledger-same-incident",
        "Ledger update, Nov. 18, 2026",
        "\u201cIt is the same incident\u201d",
        "Tampered devices now found outside Southeast Asia, built to capture the recovery phrase during setup.",
        footer="Ledger support update via Decrypt and CyberSIXT",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: Oct. 15, Ledger discloses tampered devices sold via Southeast Asian resellers; Nov. 14, an owner reports 507,000 USDT drained from a Ledger Stax bought in Dubai; Nov. 16, photos show an implant in a Ledger Flex bought in Dubai, according to an open-source tracker; Nov. 18, Ledger confirms tampered units in Berlin and investigates two in Dubai", {
            "es": "Cronología: 15 de octubre, Ledger revela dispositivos manipulados vendidos por revendedores del Sudeste Asiático; 14 de noviembre, un usuario denuncia el robo de 507.000 USDT de una Ledger Stax comprada en Dubái; 16 de noviembre, unas fotos muestran un implante en una Ledger Flex comprada en Dubái, según un rastreador de código abierto; 18 de noviembre, Ledger confirma unidades manipuladas en Berlín e investiga dos en Dubái",
            "pt": "Linha do tempo: 15 de outubro, a Ledger revela dispositivos adulterados vendidos por revendedores do Sudeste Asiático; 14 de novembro, um dono relata o roubo de 507.000 USDT de uma Ledger Stax comprada em Dubai; 16 de novembro, fotos mostram um implante em uma Ledger Flex comprada em Dubai, segundo um rastreador de código aberto; 18 de novembro, a Ledger confirma unidades adulteradas em Berlim e investiga duas em Dubai",
            "fr": "Chronologie : 15 octobre, Ledger révèle des appareils piégés vendus par des revendeurs d'Asie du Sud-Est ; 14 novembre, un propriétaire signale le vol de 507 000 USDT sur un Ledger Stax acheté à Dubaï ; 16 novembre, des photos montrent un implant dans un Ledger Flex acheté à Dubaï, selon un outil de suivi open source ; 18 novembre, Ledger confirme des appareils piégés à Berlin et enquête sur deux à Dubaï",
            "de": "Zeitleiste: 15. Oktober, Ledger macht manipulierte Geräte von Händlern in Südostasien öffentlich; 14. November, ein Besitzer meldet den Diebstahl von 507.000 USDT von einem in Dubai gekauften Ledger Stax; 16. November, Fotos zeigen laut einem Open-Source-Tracker ein Implantat in einem in Dubai gekauften Ledger Flex; 18. November, Ledger bestätigt manipulierte Geräte in Berlin und prüft zwei in Dubai",
            "ru": "Хронология: 15 октября Ledger сообщает о вскрытых устройствах, проданных реселлерами в Юго-Восточной Азии; 14 ноября владелец сообщает о краже 507 000 USDT с Ledger Stax, купленного в Дубае; 16 ноября фото показывают имплант в Ledger Flex, купленном в Дубае, по данным открытого трекера; 18 ноября Ledger подтверждает вскрытые устройства в Берлине и проверяет два в Дубае",
            "tr": "Zaman çizelgesi: 15 Ekim, Ledger Güneydoğu Asya'daki bayiler üzerinden satılan kurcalanmış cihazları açıklıyor; 14 Kasım, bir kullanıcı Dubai'den alınan Ledger Stax'tan 507.000 USDT çalındığını bildiriyor; 16 Kasım, açık kaynaklı bir takipçiye göre fotoğraflar Dubai'den alınan bir Ledger Flex'te implant olduğunu gösteriyor; 18 Kasım, Ledger Berlin'de kurcalanmış cihazları doğruluyor ve Dubai'deki iki cihazı inceliyor",
            "id": "Lini masa: 15 Oktober, Ledger mengungkap perangkat yang dimodifikasi dan dijual lewat pengecer di Asia Tenggara; 14 November, seorang pemilik melaporkan 507.000 USDT dikuras dari Ledger Stax yang dibeli di Dubai; 16 November, foto menunjukkan implan di Ledger Flex yang dibeli di Dubai, menurut pelacak sumber terbuka; 18 November, Ledger memastikan unit yang dimodifikasi di Berlin dan menyelidiki dua unit di Dubai",
            "ja": "時系列：10月15日、Ledgerが東南アジアの販売店経由で売られた改ざん端末を公表。11月14日、ドバイで買ったLedger Staxから50万7000USDTが盗まれたと所有者が報告。11月16日、オープンソースの追跡サイトによると、ドバイで買ったLedger Flexの写真にインプラントが写る。11月18日、Ledgerがベルリンでの改ざん端末を確認し、ドバイの2台を調査",
            "ko": "타임라인: 10월 15일 렛저, 동남아 리셀러를 통해 팔린 조작 기기 공개; 11월 14일 두바이에서 산 렛저 스택스에서 50만7000 USDT가 빠져나갔다고 소유자 보고; 11월 16일 오픈소스 추적 사이트에 따르면 두바이에서 산 렛저 플렉스 사진에서 임플란트 확인; 11월 18일 렛저, 베를린의 조작 기기 확인 및 두바이 2대 조사",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Ledger, Ledger Implant OSINT, Decrypt")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Ledger's Nov. 18, 2026 update says \"It is the same incident\": tampered devices are now found outside Southeast Asia, built to capture the recovery phrase during setup", {
            "es": "Tarjeta de datos: la actualización de Ledger del 18 de noviembre de 2026 dice «Es el mismo incidente»: ahora hay dispositivos manipulados fuera del Sudeste Asiático, preparados para capturar la frase de recuperación durante la configuración",
            "pt": "Cartão de dados: a atualização da Ledger de 18 de novembro de 2026 diz \"É o mesmo incidente\": agora há dispositivos adulterados fora do Sudeste Asiático, feitos para capturar a frase de recuperação durante a configuração",
            "fr": "Fiche : la mise à jour de Ledger du 18 novembre 2026 indique « C'est le même incident » : des appareils piégés apparaissent hors d'Asie du Sud-Est, conçus pour capturer la phrase de récupération lors de la configuration",
            "de": "Faktenkarte: Ledgers Update vom 18. November 2026 sagt „Es ist derselbe Vorfall“: Manipulierte Geräte tauchen jetzt außerhalb Südostasiens auf und sollen bei der Einrichtung die Wiederherstellungsphrase abgreifen",
            "ru": "Карточка: в обновлении Ledger от 18 ноября 2026 года сказано «Это тот же инцидент»: вскрытые устройства теперь найдены за пределами Юго-Восточной Азии, они перехватывают сид-фразу при настройке",
            "tr": "Bilgi kartı: Ledger'ın 18 Kasım 2026 güncellemesi \"Aynı olay\" diyor: kurcalanmış cihazlar artık Güneydoğu Asya dışında da bulunuyor ve kurulum sırasında kurtarma ifadesini ele geçirmek için tasarlanmış",
            "id": "Kartu fakta: pembaruan Ledger 18 November 2026 menyebut \"Ini insiden yang sama\": perangkat yang dimodifikasi kini ditemukan di luar Asia Tenggara, dibuat untuk menangkap frasa pemulihan saat pengaturan",
            "ja": "ファクトカード：Ledgerの2026年11月18日の更新は「同じ事件だ」としている。改ざん端末は東南アジア以外でも見つかり、設定時にリカバリーフレーズを盗むよう作られている",
            "ko": "팩트 카드: 렛저의 2026년 11월 18일 업데이트는 \"같은 사건\"이라고 밝힘. 조작 기기가 동남아 밖에서도 발견됐으며 설정 중 복구 문구를 가로채도록 만들어짐",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Ledger via Decrypt, CyberSIXT")},
    ]


def build_genius_state_safe_harbor():
    slug = "senators-genius-act-state-stablecoin-safe-harbor-nov-2026"
    d = OUT / slug
    # Sen. Lummis press release Nov 18, 2026; The Block Nov 18, 2026; OCC Bulletin 2026-50 (Oct 21, 2026).
    cmp_ = make_compare_card(
        d / "compare-genius-federal-vs-state",
        "GENIUS Act start: federal vs. state issuers",
        "Federal path", "State-licensed",
        [
            ("Who", "Issuers with pending federal applications", "Issuers with $10B or less under state rules"),
            ("Safe harbor", "Yes, in Treasury's draft rule (with a waiver)", "No; six senators ask Treasury to add one"),
            ("Start date", "Jan. 18, 2027", "Jan. 18, 2027; state certifications reviewed in 2027"),
        ],
        footer="Sen. Lummis press release, The Block, OCC",
    )
    tl = make_timeline_card(
        d / "timeline-genius-act",
        "GENIUS Act: key dates",
        [
            ("Jul 2025", "GENIUS Act signed into law (July 18)", (96, 165, 250)),
            ("Jun 2026", "Senators ask Treasury for clear state rules (June 16)", (148, 163, 184)),
            ("Oct 2026", "OCC issues its final GENIUS rule (Oct. 21)", (96, 165, 250)),
            ("Nov 2026", "Six senators ask for a state safe harbor (Nov. 18)", GREEN),
            ("Jan 2027", "GENIUS Act takes effect (Jan. 18)", ORANGE),
        ],
        footer="OCC · Sen. Lummis · The Block",
        margin=150, wrap_w=200,
    )
    return [
        {"id": "compare", "file": cmp_.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Comparison card: issuers with pending federal applications get a safe harbor in Treasury's draft GENIUS Act rule if their regulator grants a waiver; state-licensed issuers with $10 billion or less do not, and six senators ask Treasury to add one; both face the Jan. 18, 2027 start date, with state certifications reviewed in 2027", {
            "es": "Tarjeta comparativa: los emisores con solicitudes federales pendientes reciben un puerto seguro en el borrador de Tesorería para la Ley GENIUS si su regulador concede una exención; los emisores con licencia estatal y 10.000 millones de dólares o menos no, y seis senadores piden a Tesorería que lo añada; ambos afrontan el inicio del 18 de enero de 2027, con certificaciones estatales revisadas en 2027",
            "pt": "Cartão comparativo: emissores com pedidos federais pendentes recebem um porto seguro na minuta do Tesouro para a Lei GENIUS se o regulador conceder uma dispensa; emissores com licença estadual e até US$ 10 bilhões não, e seis senadores pedem que o Tesouro inclua um; ambos enfrentam o início em 18 de janeiro de 2027, com certificações estaduais analisadas em 2027",
            "fr": "Fiche comparative : les émetteurs ayant une demande fédérale en cours bénéficient d'une protection transitoire dans le projet de règle du Trésor sur le GENIUS Act si leur régulateur accorde une dérogation ; les émetteurs agréés par un État jusqu'à 10 milliards de dollars n'en ont pas, et six sénateurs demandent au Trésor d'en ajouter une ; tous font face au 18 janvier 2027, les certifications des États étant examinées en 2027",
            "de": "Vergleichskarte: Emittenten mit laufendem Bundesantrag erhalten im Entwurf des Finanzministeriums zum GENIUS Act einen Schutz, wenn ihre Aufsicht eine Ausnahme gewährt; bundesstaatlich lizenzierte Emittenten mit höchstens 10 Mrd. $ nicht, und sechs Senatoren fordern einen; für beide gilt der Start am 18. Januar 2027, die Zertifizierungen der Bundesstaaten werden 2027 geprüft",
            "ru": "Сравнение: эмитенты с поданными федеральными заявками получают «безопасную гавань» в проекте правил Минфина по закону GENIUS, если регулятор даст освобождение; эмитенты с лицензией штата и объёмом до $10 млрд — нет, и шесть сенаторов просят Минфин это исправить; для всех старт 18 января 2027 года, сертификаты штатов будут проверять в 2027 году",
            "tr": "Karşılaştırma kartı: federal başvurusu bekleyen ihraççılar, düzenleyicileri muafiyet verirse Hazine'nin GENIUS Yasası taslağında güvenli liman alıyor; 10 milyar $ veya altındaki eyalet lisanslı ihraççılar almıyor ve altı senatör Hazine'den bunu eklemesini istiyor; her ikisi için başlangıç 18 Ocak 2027, eyalet sertifikaları 2027'de incelenecek",
            "id": "Kartu perbandingan: penerbit dengan permohonan federal yang tertunda mendapat safe harbor dalam rancangan aturan Departemen Keuangan untuk UU GENIUS jika regulatornya memberi pengecualian; penerbit berizin negara bagian dengan US$10 miliar atau kurang tidak, dan enam senator meminta Departemen Keuangan menambahkannya; keduanya menghadapi tanggal mulai 18 Januari 2027, dengan sertifikasi negara bagian ditinjau pada 2027",
            "ja": "比較カード：連邦の申請中の発行体は、規制当局が適用除外を認めれば財務省のGENIUS法規則案でセーフハーバーを得る。100億ドル以下の州ライセンスの発行体は対象外で、上院議員6人が追加を求める。どちらも2027年1月18日に施行を迎え、州の認証は2027年に審査される",
            "ko": "비교 카드: 연방 신청이 계류 중인 발행사는 규제기관이 면제를 주면 재무부 GENIUS법 규칙안에서 세이프하버를 받음; 100억 달러 이하 주 라이선스 발행사는 받지 못하며 상원의원 6명이 추가를 요청; 둘 다 2027년 1월 18일 시행을 맞고 주 인증은 2027년에 심사됨",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Sen. Lummis press release, The Block, OCC")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: July 18, 2025, GENIUS Act signed into law; June 16, 2026, senators ask Treasury for clear rules on state certification; Oct. 21, 2026, the OCC issues its final GENIUS Act rule; Nov. 18, 2026, six senators ask Treasury for a state safe harbor; Jan. 18, 2027, the GENIUS Act takes effect", {
            "es": "Cronología: 18 de julio de 2025, se firma la Ley GENIUS; 16 de junio de 2026, varios senadores piden a Tesorería reglas claras para la certificación estatal; 21 de octubre de 2026, la OCC publica su norma final; 18 de noviembre de 2026, seis senadores piden un puerto seguro para los estados; 18 de enero de 2027, entra en vigor la Ley GENIUS",
            "pt": "Linha do tempo: 18 de julho de 2025, a Lei GENIUS é sancionada; 16 de junho de 2026, senadores pedem ao Tesouro regras claras para a certificação estadual; 21 de outubro de 2026, o OCC publica sua regra final; 18 de novembro de 2026, seis senadores pedem um porto seguro para os estados; 18 de janeiro de 2027, a Lei GENIUS entra em vigor",
            "fr": "Chronologie : 18 juillet 2025, promulgation du GENIUS Act ; 16 juin 2026, des sénateurs demandent au Trésor des règles claires pour la certification des États ; 21 octobre 2026, l'OCC publie sa règle finale ; 18 novembre 2026, six sénateurs demandent une protection pour les émetteurs des États ; 18 janvier 2027, entrée en vigueur du GENIUS Act",
            "de": "Zeitleiste: 18. Juli 2025, GENIUS Act unterzeichnet; 16. Juni 2026, Senatoren fordern vom Finanzministerium klare Regeln zur Zertifizierung der Bundesstaaten; 21. Oktober 2026, die OCC erlässt ihre endgültige Regel; 18. November 2026, sechs Senatoren fordern einen Schutz für Emittenten der Bundesstaaten; 18. Januar 2027, der GENIUS Act tritt in Kraft",
            "ru": "Хронология: 18 июля 2025 года подписан закон GENIUS; 16 июня 2026 года сенаторы просят Минфин о ясных правилах сертификации штатов; 21 октября 2026 года OCC выпускает окончательные правила; 18 ноября 2026 года шесть сенаторов просят «безопасную гавань» для эмитентов штатов; 18 января 2027 года закон GENIUS вступает в силу",
            "tr": "Zaman çizelgesi: 18 Temmuz 2025, GENIUS Yasası imzalandı; 16 Haziran 2026, senatörler Hazine'den eyalet sertifikası için net kurallar istedi; 21 Ekim 2026, OCC nihai kuralını yayımladı; 18 Kasım 2026, altı senatör eyaletler için güvenli liman istedi; 18 Ocak 2027, GENIUS Yasası yürürlüğe giriyor",
            "id": "Lini masa: 18 Juli 2025, UU GENIUS ditandatangani; 16 Juni 2026, para senator meminta Departemen Keuangan membuat aturan jelas soal sertifikasi negara bagian; 21 Oktober 2026, OCC menerbitkan aturan finalnya; 18 November 2026, enam senator meminta safe harbor bagi penerbit negara bagian; 18 Januari 2027, UU GENIUS berlaku",
            "ja": "時系列：2025年7月18日、GENIUS法が成立。2026年6月16日、上院議員が財務省に州の認証について明確なルールを要請。2026年10月21日、OCCが最終規則を公表。2026年11月18日、上院議員6人が州の発行体へのセーフハーバーを要請。2027年1月18日、GENIUS法が施行",
            "ko": "타임라인: 2025년 7월 18일 GENIUS법 서명; 2026년 6월 16일 상원의원들이 재무부에 주 인증 규칙 명확화 요청; 2026년 10월 21일 OCC 최종 규칙 발표; 2026년 11월 18일 상원의원 6명이 주 발행사 세이프하버 요청; 2027년 1월 18일 GENIUS법 시행",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="OCC, Sen. Lummis press release, The Block")},
    ]


def build_threat_disruption_center():
    slug = "threat-disruption-center-crypto-scams-trm-labs-nov-2026"
    d = OUT / slug
    # FBI IC3 2025 Internet Crime Report: losses by year 2021 $6.9B, 2022 $10.3B, 2023 $12.5B, 2024 $16.6B, 2025 $20.877B;
    # crypto-nexus complaints 2025: $11.366B (+22%); crypto investment fraud $7.228B.
    chart = make_bar_chart(
        d / "chart-ic3-losses-by-year",
        ["2021", "2022", "2023", "2024", "2025"],
        [6.9, 10.3, 12.5, 16.6, 20.877],
        "Cybercrime losses reported to the FBI (US$ billions)",
        colors=["#64748b", "#64748b", "#64748b", "#64748b", "#f7931a"],
        value_fmt=lambda v: f"${v:,.1f}B" if v != 20.877 else "$20.9B",
        axis_fmt=lambda x, _p: f"${x:,.0f}B",
    )
    fact = make_fact_card(
        d / "fact-ic3-crypto-losses-2025",
        "FBI IC3, 2025",
        "$11.366 billion",
        "Reported losses in complaints involving crypto, up 22% from 2024. Crypto investment fraud alone: $7.228 billion.",
        footer="FBI 2025 Internet Crime Report",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of cybercrime losses reported to the FBI's IC3: $6.9 billion in 2021, $10.3 billion in 2022, $12.5 billion in 2023, $16.6 billion in 2024 and $20.9 billion in 2025", {
            "es": "Gráfico de barras de las pérdidas por ciberdelitos denunciadas al IC3 del FBI: 6.900 millones de dólares en 2021, 10.300 millones en 2022, 12.500 millones en 2023, 16.600 millones en 2024 y 20.900 millones en 2025",
            "pt": "Gráfico de barras das perdas com crimes cibernéticos relatadas ao IC3 do FBI: US$ 6,9 bilhões em 2021, US$ 10,3 bilhões em 2022, US$ 12,5 bilhões em 2023, US$ 16,6 bilhões em 2024 e US$ 20,9 bilhões em 2025",
            "fr": "Graphique en barres des pertes liées à la cybercriminalité signalées à l'IC3 du FBI : 6,9 milliards de dollars en 2021, 10,3 milliards en 2022, 12,5 milliards en 2023, 16,6 milliards en 2024 et 20,9 milliards en 2025",
            "de": "Balkendiagramm der dem IC3 des FBI gemeldeten Schäden durch Cyberkriminalität: 6,9 Mrd. $ 2021, 10,3 Mrd. $ 2022, 12,5 Mrd. $ 2023, 16,6 Mrd. $ 2024 und 20,9 Mrd. $ 2025",
            "ru": "Столбчатая диаграмма потерь от киберпреступлений, о которых сообщили в IC3 ФБР: $6,9 млрд в 2021 году, $10,3 млрд в 2022-м, $12,5 млрд в 2023-м, $16,6 млрд в 2024-м и $20,9 млрд в 2025-м",
            "tr": "FBI'ın IC3 birimine bildirilen siber suç kayıplarının çubuk grafiği: 2021'de 6,9 milyar $, 2022'de 10,3 milyar $, 2023'te 12,5 milyar $, 2024'te 16,6 milyar $ ve 2025'te 20,9 milyar $",
            "id": "Grafik batang kerugian kejahatan siber yang dilaporkan ke IC3 FBI: US$6,9 miliar pada 2021, US$10,3 miliar pada 2022, US$12,5 miliar pada 2023, US$16,6 miliar pada 2024, dan US$20,9 miliar pada 2025",
            "ja": "FBIのIC3に報告されたサイバー犯罪の被害額の棒グラフ：2021年69億ドル、2022年103億ドル、2023年125億ドル、2024年166億ドル、2025年209億ドル",
            "ko": "FBI IC3에 신고된 사이버 범죄 피해액 막대 차트: 2021년 69억 달러, 2022년 103억 달러, 2023년 125억 달러, 2024년 166억 달러, 2025년 209억 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="FBI 2025 Internet Crime Report")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: in 2025, complaints to the FBI's IC3 that involved cryptocurrency reported $11.366 billion in losses, up 22% from 2024; crypto investment fraud alone accounted for $7.228 billion", {
            "es": "Tarjeta de datos: en 2025, las denuncias al IC3 del FBI relacionadas con criptomonedas sumaron pérdidas de 11.366 millones de dólares, un 22% más que en 2024; solo el fraude de inversión cripto representó 7.228 millones",
            "pt": "Cartão de dados: em 2025, as queixas ao IC3 do FBI envolvendo criptomoedas somaram perdas de US$ 11,366 bilhões, alta de 22% sobre 2024; só a fraude de investimento em cripto respondeu por US$ 7,228 bilhões",
            "fr": "Fiche : en 2025, les plaintes déposées auprès de l'IC3 du FBI impliquant des cryptomonnaies ont fait état de 11,366 milliards de dollars de pertes, en hausse de 22 % sur 2024 ; la fraude à l'investissement crypto représente à elle seule 7,228 milliards",
            "de": "Faktenkarte: 2025 meldeten Beschwerden beim IC3 des FBI mit Kryptobezug Schäden von 11,366 Mrd. $, 22 % mehr als 2024; allein auf Krypto-Anlagebetrug entfielen 7,228 Mrd. $",
            "ru": "Карточка: в 2025 году жалобы в IC3 ФБР, связанные с криптовалютой, показали потери на $11,366 млрд, на 22% больше, чем в 2024-м; только на мошенничество с криптоинвестициями пришлось $7,228 млрд",
            "tr": "Bilgi kartı: 2025'te FBI'ın IC3 birimine yapılan kriptoyla ilgili şikâyetlerde bildirilen kayıp 11,366 milyar $ oldu, 2024'e göre %22 artış; yalnızca kripto yatırım dolandırıcılığı 7,228 milyar $",
            "id": "Kartu fakta: pada 2025, pengaduan ke IC3 FBI yang melibatkan kripto mencatat kerugian US$11,366 miliar, naik 22% dari 2024; penipuan investasi kripto saja mencapai US$7,228 miliar",
            "ja": "ファクトカード：2025年、FBIのIC3に寄せられた暗号資産関連の苦情による被害額は113億6600万ドルで、2024年比22%増。暗号資産投資詐欺だけで72億2800万ドル",
            "ko": "팩트 카드: 2025년 FBI IC3에 접수된 암호화폐 관련 신고 피해액은 113억6600만 달러로 2024년보다 22% 증가; 암호화폐 투자 사기만 72억2800만 달러",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="FBI 2025 Internet Crime Report")},
    ]


def build_sky_psm_illicit():
    slug = "sky-stablecoin-psm-north-korea-518-million-inca-nov-2026"
    d = OUT / slug
    # Inca Digital report via CoinDesk (Nov 19, 2026): $518M total across 422 wallets; $101.9M North Korea-linked;
    # $91.5M Bybit-funded wallets in 10 days after Feb 2025 hack; Infini exploiter $49.5M; FTX Accounts Drainer $26.1M.
    # PSM holds ~$2.7B USDC in a single Ethereum wallet set up via Coinbase Prime.
    chart = make_bar_chart(
        d / "chart-sky-psm-illicit-flows",
        ["All flagged\nwallets (422)", "Linked to\nNorth Korea", "Bybit-hack\nwallets (10 days)", "Infini\nexploiter", "FTX Accounts\nDrainer"],
        [518, 101.9, 91.5, 49.5, 26.1],
        "Flagged flows through Sky's PSM (US$ millions)",
        colors=["#f87171", "#f7931a", "#f7931a", "#64748b", "#64748b"],
        value_fmt=lambda v: f"${v:,.1f}M" if v != 518 else "$518M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    fact = make_fact_card(
        d / "fact-sky-psm-2-7-billion-usdc",
        "Sky's PSM reserve",
        "$2.7 billion USDC",
        "Held in one Ethereum wallet. Circle cannot freeze part of an address, so a freeze would lock all of it.",
        footer="Inca Digital via CoinDesk",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of flagged flows through Sky's Peg Stability Module found by Inca Digital: $518 million across 422 illicit-linked wallets, $101.9 million linked to North Korea, $91.5 million from Bybit-hack wallets in 10 days, $49.5 million from the Infini exploiter and $26.1 million from the FTX Accounts Drainer", {
            "es": "Gráfico de barras de los flujos señalados por Inca Digital en el Peg Stability Module de Sky: 518 millones de dólares en 422 billeteras vinculadas a actividades ilícitas, 101,9 millones ligados a Corea del Norte, 91,5 millones de billeteras del hackeo a Bybit en 10 días, 49,5 millones del atacante de Infini y 26,1 millones del FTX Accounts Drainer",
            "pt": "Gráfico de barras dos fluxos apontados pela Inca Digital no Peg Stability Module da Sky: US$ 518 milhões em 422 carteiras ligadas a atividades ilícitas, US$ 101,9 milhões ligados à Coreia do Norte, US$ 91,5 milhões de carteiras do ataque à Bybit em 10 dias, US$ 49,5 milhões do invasor da Infini e US$ 26,1 milhões do FTX Accounts Drainer",
            "fr": "Graphique en barres des flux signalés par Inca Digital dans le Peg Stability Module de Sky : 518 millions de dollars via 422 portefeuilles liés à des activités illicites, 101,9 millions liés à la Corée du Nord, 91,5 millions venant de portefeuilles du piratage de Bybit en 10 jours, 49,5 millions de l'attaquant d'Infini et 26,1 millions du FTX Accounts Drainer",
            "de": "Balkendiagramm der von Inca Digital markierten Flüsse durch Skys Peg Stability Module: 518 Mio. $ über 422 mit illegalen Akteuren verknüpfte Wallets, 101,9 Mio. $ mit Bezug zu Nordkorea, 91,5 Mio. $ aus Bybit-Hack-Wallets binnen 10 Tagen, 49,5 Mio. $ vom Infini-Angreifer und 26,1 Mio. $ vom FTX Accounts Drainer",
            "ru": "Столбчатая диаграмма подозрительных потоков через Peg Stability Module протокола Sky по данным Inca Digital: $518 млн через 422 кошелька, связанных с незаконной деятельностью, $101,9 млн связаны с КНДР, $91,5 млн из кошельков взлома Bybit за 10 дней, $49,5 млн от атакующего Infini и $26,1 млн от FTX Accounts Drainer",
            "tr": "Inca Digital'in Sky'ın Peg Stability Module'ünde işaretlediği akışların çubuk grafiği: yasa dışı faaliyetlerle bağlantılı 422 cüzdandan 518 milyon $, Kuzey Kore ile bağlantılı 101,9 milyon $, Bybit saldırısı cüzdanlarından 10 günde 91,5 milyon $, Infini saldırganından 49,5 milyon $ ve FTX Accounts Drainer'dan 26,1 milyon $",
            "id": "Grafik batang aliran yang ditandai Inca Digital di Peg Stability Module milik Sky: US$518 juta dari 422 dompet terkait aktivitas ilegal, US$101,9 juta terkait Korea Utara, US$91,5 juta dari dompet peretasan Bybit dalam 10 hari, US$49,5 juta dari penyerang Infini, dan US$26,1 juta dari FTX Accounts Drainer",
            "ja": "Inca DigitalがSkyのペグ安定化モジュール（PSM）で指摘した資金の流れの棒グラフ：不正関連の422ウォレットで計5億1800万ドル、北朝鮮関連1億190万ドル、Bybitハッキングのウォレットから10日間で9150万ドル、Infiniの攻撃者4950万ドル、FTX Accounts Drainer 2610万ドル",
            "ko": "Inca Digital이 Sky의 페그 안정 모듈(PSM)에서 지목한 자금 흐름 막대 차트: 불법 연루 지갑 422개 합계 5억1800만 달러, 북한 연루 1억190만 달러, 바이비트 해킹 지갑에서 10일간 9150만 달러, Infini 공격자 4950만 달러, FTX Accounts Drainer 2610만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Inca Digital via CoinDesk")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Sky's Peg Stability Module holds about $2.7 billion in USDC in one Ethereum wallet; Circle cannot freeze part of an address, so a freeze would lock all of it", {
            "es": "Tarjeta de datos: el Peg Stability Module de Sky guarda unos 2.700 millones de dólares en USDC en una sola billetera de Ethereum; Circle no puede congelar solo una parte de una dirección, así que un congelamiento bloquearía todo",
            "pt": "Cartão de dados: o Peg Stability Module da Sky guarda cerca de US$ 2,7 bilhões em USDC em uma única carteira de Ethereum; a Circle não consegue congelar só parte de um endereço, então um congelamento travaria tudo",
            "fr": "Fiche : le Peg Stability Module de Sky détient environ 2,7 milliards de dollars en USDC dans un seul portefeuille Ethereum ; Circle ne peut pas geler une partie d'une adresse, un gel bloquerait donc la totalité",
            "de": "Faktenkarte: Skys Peg Stability Module hält rund 2,7 Mrd. $ in USDC in einer einzigen Ethereum-Wallet; Circle kann nicht nur einen Teil einer Adresse sperren, eine Sperre würde also alles einfrieren",
            "ru": "Карточка: Peg Stability Module протокола Sky держит около $2,7 млрд в USDC на одном кошельке Ethereum; Circle не может заморозить часть адреса, поэтому заморозка заблокирует всю сумму",
            "tr": "Bilgi kartı: Sky'ın Peg Stability Module'ü tek bir Ethereum cüzdanında yaklaşık 2,7 milyar $ USDC tutuyor; Circle bir adresin yalnızca bir kısmını donduramıyor, bu yüzden dondurma tamamını kilitler",
            "id": "Kartu fakta: Peg Stability Module milik Sky menyimpan sekitar US$2,7 miliar USDC di satu dompet Ethereum; Circle tidak bisa membekukan sebagian alamat, jadi pembekuan akan mengunci semuanya",
            "ja": "ファクトカード：SkyのPSMは約27億ドルのUSDCを1つのイーサリアムウォレットで保有。Circleはアドレスの一部だけを凍結できないため、凍結されれば全額がロックされる",
            "ko": "팩트 카드: Sky의 PSM은 약 27억 달러의 USDC를 이더리움 지갑 하나에 보관; 서클은 주소의 일부만 동결할 수 없어 동결 시 전액이 묶임",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Inca Digital via CoinDesk")},
    ]


def build_btc_below_62k_july():
    slug = "bitcoin-below-62000-lowest-since-july-etf-outflows-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 17 00:00 UTC to Nov 20 01:00 UTC (7 p.m. CST Nov 19). Nov 19 low $61,353.20 (21:00 UTC hour).
    xs, ys = fetch_kraken_hourly(1794873600, 1795136400, pair="XBTUSD")
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-17-19",
        xs, ys,
        title="Bitcoin hourly price, Nov. 17-19, 2026 (Kraken, UTC)",
        hline=61353.2,
        hlabel="Nov. 19 low ≈ $61,353 (Kraken)",
    )
    # Farside Investors daily net flows, Nov 2-18, 2026 (13 sessions) summed by PlainBTC: -$2,885.5M.
    fact = make_fact_card(
        d / "fact-2-89-billion-november-outflows",
        "U.S. spot bitcoin ETFs, November 2026",
        "-$2.89 billion",
        "Net outflows from Nov. 2 to Nov. 18, with withdrawals on 11 of 13 trading days.",
        footer="Farside Investors daily flows, summed by PlainBTC",
    )
    days = ["Oct 30", "Nov 2", "Nov 3", "Nov 4", "Nov 5", "Nov 6", "Nov 9", "Nov 10", "Nov 11", "Nov 12", "Nov 13", "Nov 16", "Nov 17", "Nov 18"]
    flows = [-643.2, -398.6, -115.6, 74.6, -430.2, -411.9, -201.0, -95.0, -299.8, -284.1, -185.4, 7.9, -239.9, -306.5]
    flows_img = make_bar_chart(
        d / "chart-btc-etf-flows-oct30-nov18",
        days, flows,
        "U.S. spot bitcoin ETF daily net flows (US$ millions)",
        colors=["#34d399" if v > 0 else "#f87171" for v in flows],
        value_fmt=lambda v: f"{v:+,.1f}",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 17 to Nov. 19, 2026, falling from about $65,000 to near $62,000, with a dashed line at the Nov. 19 low of about $61,353", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 17 al 19 de noviembre de 2026: cae de unos 65.000 dólares a cerca de 62.000, con una línea discontinua en el mínimo del 19 de noviembre, de unos 61.353 dólares",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 17 a 19 de novembro de 2026: cai de cerca de US$ 65.000 para perto de US$ 62.000, com uma linha tracejada na mínima de 19 de novembro, de cerca de US$ 61.353",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 17 au 19 novembre 2026 : il recule d'environ 65 000 dollars à près de 62 000 dollars, avec une ligne pointillée au plus bas du 19 novembre, environ 61 353 dollars",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 17. bis 19. November 2026: Rückgang von rund 65.000 $ auf knapp 62.000 $; gestrichelte Linie beim Tief vom 19. November von rund 61.353 $",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 17 по 19 ноября 2026 года: снижение примерно с $65 000 почти до $62 000; пунктирная линия показывает минимум 19 ноября, около $61 353",
            "tr": "Bitcoin'in 17-19 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 65.000 $'dan 62.000 $ civarına düşüyor; kesikli çizgi 19 Kasım'daki yaklaşık 61.353 $'lık dibi gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 17 hingga 19 November 2026: turun dari sekitar US$65.000 ke dekat US$62.000, dengan garis putus-putus di level terendah 19 November sekitar US$61.353",
            "ja": "2026年11月17〜19日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約6万5000ドルから6万2000ドル近辺へ下落。破線は11月19日の安値（約6万1353ドル）",
            "ko": "2026년 11월 17~19일 크라켄 비트코인 시간별 가격 선 차트: 약 6만5000달러에서 6만2000달러 부근으로 하락, 점선은 11월 19일 저점 약 6만1353달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: U.S. spot bitcoin ETFs had about $2.89 billion in net outflows from Nov. 2 to Nov. 18, 2026, with withdrawals on 11 of 13 trading days, based on Farside Investors data", {
            "es": "Tarjeta: los ETF de bitcoin al contado de EE. UU. registraron salidas netas de unos 2.890 millones de dólares del 2 al 18 de noviembre de 2026, con retiros en 11 de 13 sesiones, según datos de Farside Investors",
            "pt": "Cartão: os ETFs de bitcoin à vista dos EUA tiveram saídas líquidas de cerca de US$ 2,89 bilhões de 2 a 18 de novembro de 2026, com resgates em 11 de 13 pregões, segundo dados da Farside Investors",
            "fr": "Carte : les ETF bitcoin au comptant américains ont enregistré environ 2,89 milliards de dollars de sorties nettes du 2 au 18 novembre 2026, avec des retraits sur 11 séances sur 13, selon les données de Farside Investors",
            "de": "Faktenkarte: US-Spot-Bitcoin-ETFs verzeichneten vom 2. bis 18. November 2026 Nettoabflüsse von rund 2,89 Mrd. $, mit Abflüssen an 11 von 13 Handelstagen, laut Daten von Farside Investors",
            "ru": "Карточка: со 2 по 18 ноября 2026 года чистый отток из американских спотовых биткоин-ETF составил около $2,89 млрд, оттоки были в 11 из 13 торговых дней, по данным Farside Investors",
            "tr": "Kart: Farside Investors verilerine göre ABD spot bitcoin ETF'lerinden 2-18 Kasım 2026 arasında yaklaşık 2,89 milyar $ net çıkış oldu; 13 işlem gününün 11'inde çıkış yaşandı",
            "id": "Kartu: ETF bitcoin spot AS mencatat arus keluar bersih sekitar US$2,89 miliar pada 2 hingga 18 November 2026, dengan penarikan pada 11 dari 13 hari perdagangan, menurut data Farside Investors",
            "ja": "カード：Farside Investorsのデータによると、米国の現物ビットコインETFは2026年11月2〜18日に約28億9000万ドルの純流出となり、13営業日中11日で流出した",
            "ko": "카드: Farside Investors 자료 기준 미국 현물 비트코인 ETF는 2026년 11월 2~18일 약 28억9000만 달러 순유출을 기록했으며, 13거래일 중 11일 동안 자금이 빠져나갔다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Farside Investors (sum by PlainBTC)")},
        {"id": "flows", "file": flows_img.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of U.S. spot bitcoin ETF daily net flows from Oct. 30 to Nov. 18, 2026, per Farside Investors: outflows on 12 of 14 trading days, the largest $643.2 million on Oct. 30, and $306.5 million out on Nov. 18", {
            "es": "Gráfico de barras de los flujos netos diarios de los ETF de bitcoin al contado de EE. UU. del 30 de octubre al 18 de noviembre de 2026, según Farside Investors: salidas en 12 de 14 sesiones, la mayor de 643,2 millones de dólares el 30 de octubre, y 306,5 millones de salidas el 18 de noviembre",
            "pt": "Gráfico de barras dos fluxos líquidos diários dos ETFs de bitcoin à vista dos EUA de 30 de outubro a 18 de novembro de 2026, segundo a Farside Investors: saídas em 12 de 14 pregões, a maior de US$ 643,2 milhões em 30 de outubro, e saídas de US$ 306,5 milhões em 18 de novembro",
            "fr": "Diagramme en barres des flux nets quotidiens des ETF bitcoin au comptant américains du 30 octobre au 18 novembre 2026, selon Farside Investors : sorties sur 12 séances sur 14, la plus forte de 643,2 millions de dollars le 30 octobre, et 306,5 millions de sorties le 18 novembre",
            "de": "Balkendiagramm der täglichen Nettozuflüsse der US-Spot-Bitcoin-ETFs vom 30. Oktober bis 18. November 2026 laut Farside Investors: Abflüsse an 12 von 14 Handelstagen, der größte mit 643,2 Mio. $ am 30. Oktober, und 306,5 Mio. $ Abfluss am 18. November",
            "ru": "Столбчатая диаграмма ежедневных чистых потоков американских спотовых биткоин-ETF с 30 октября по 18 ноября 2026 года по данным Farside Investors: оттоки в 12 из 14 торговых дней, крупнейший $643,2 млн 30 октября, отток $306,5 млн 18 ноября",
            "tr": "Farside Investors verilerine göre 30 Ekim-18 Kasım 2026 arasında ABD spot bitcoin ETF'lerinin günlük net akışlarının çubuk grafiği: 14 işlem gününün 12'sinde çıkış, en büyüğü 30 Ekim'de 643,2 milyon $, 18 Kasım'da 306,5 milyon $ çıkış",
            "id": "Grafik batang arus bersih harian ETF bitcoin spot AS dari 30 Oktober hingga 18 November 2026 menurut Farside Investors: arus keluar pada 12 dari 14 hari perdagangan, terbesar US$643,2 juta pada 30 Oktober, dan arus keluar US$306,5 juta pada 18 November",
            "ja": "Farside Investorsによる2026年10月30日～11月18日の米国現物ビットコインETFの日次純流出入の棒グラフ：14営業日中12日で流出、最大は10月30日の6億4320万ドル、11月18日は3億650万ドルの流出",
            "ko": "Farside Investors 기준 2026년 10월 30일~11월 18일 미국 현물 비트코인 ETF 일별 순유출입 막대 차트: 14거래일 중 12일 순유출, 최대는 10월 30일 6억4320만 달러, 11월 18일 3억650만 달러 순유출",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
    ]


def build_coinbase_options_intl():
    slug = "coinbase-crypto-options-non-us-users-deribit-nov-2026"
    d = OUT / slug
    # Coinbase X posts Nov 19, 2026; crypto.news Nov 19, 2026 (six assets, USDC settlement).
    fact = make_fact_card(
        d / "fact-six-assets-usdc-settled",
        "Coinbase options, outside the U.S.",
        "BTC · ETH · SOL · AVAX · HYPE · XRP",
        "Six assets at launch on Nov. 19, 2026, settled in USDC and powered by Deribit. Not available to U.S. retail users yet.",
        footer="Coinbase on X · crypto.news, Nov. 19, 2026",
    )
    # Coinbase blog Oct 7, 2026; crypto.news (Deribit close Aug 14, 2025); Coinbase/Armstrong X posts Nov 19, 2026.
    tl = make_timeline_card(
        d / "timeline-coinbase-deribit-options",
        "From Deribit deal to Coinbase options",
        [
            ("Aug. 2025", "Coinbase completes its $2.9 billion Deribit purchase", (96, 165, 250)),
            ("Oct. 2026", "Coinbase says the Deribit integration is done", (96, 165, 250)),
            ("Nov. 19", "Options go live for eligible users outside the U.S.", GREEN),
            ("Next", "U.S. access \"soon\" via Coinbase Pro, no date given", ORANGE),
        ],
        footer="Coinbase · crypto.news · Brian Armstrong on X",
        margin=190, wrap_w=240,
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Coinbase options launched Nov. 19, 2026 outside the U.S. on six assets, BTC, ETH, SOL, AVAX, HYPE and XRP, settled in USDC and powered by Deribit; not yet available to U.S. retail users", {
            "es": "Tarjeta: las opciones de Coinbase se lanzaron el 19 de noviembre de 2026 fuera de EE. UU. sobre seis activos, BTC, ETH, SOL, AVAX, HYPE y XRP, liquidadas en USDC y con la liquidez de Deribit; aún no disponibles para usuarios minoristas de EE. UU.",
            "pt": "Cartão: as opções da Coinbase foram lançadas em 19 de novembro de 2026 fora dos EUA sobre seis ativos, BTC, ETH, SOL, AVAX, HYPE e XRP, liquidadas em USDC e com a liquidez da Deribit; ainda indisponíveis para usuários de varejo dos EUA",
            "fr": "Carte : les options de Coinbase ont été lancées le 19 novembre 2026 hors des États-Unis sur six actifs, BTC, ETH, SOL, AVAX, HYPE et XRP, réglées en USDC et adossées à Deribit ; pas encore accessibles aux particuliers américains",
            "de": "Faktenkarte: Coinbase-Optionen starteten am 19. November 2026 außerhalb der USA auf sechs Assets, BTC, ETH, SOL, AVAX, HYPE und XRP, mit Abrechnung in USDC und Liquidität von Deribit; für US-Privatkunden noch nicht verfügbar",
            "ru": "Карточка: опционы Coinbase запущены 19 ноября 2026 года за пределами США на шесть активов (BTC, ETH, SOL, AVAX, HYPE и XRP), расчеты в USDC, ликвидность Deribit; розничным клиентам в США пока недоступны",
            "tr": "Kart: Coinbase opsiyonları 19 Kasım 2026'da ABD dışında altı varlık için başladı: BTC, ETH, SOL, AVAX, HYPE ve XRP; USDC ile uzlaşılıyor ve Deribit likiditesini kullanıyor; ABD'li bireysel kullanıcılara henüz açık değil",
            "id": "Kartu: opsi Coinbase diluncurkan 19 November 2026 di luar AS untuk enam aset, BTC, ETH, SOL, AVAX, HYPE, dan XRP, diselesaikan dalam USDC dan didukung Deribit; belum tersedia bagi pengguna ritel AS",
            "ja": "カード：コインベースのオプションは2026年11月19日に米国外で開始。対象はBTC、ETH、SOL、AVAX、HYPE、XRPの6資産で、USDCで決済され、Deribitの流動性を利用。米国の個人ユーザーはまだ利用できない",
            "ko": "카드: 코인베이스 옵션은 2026년 11월 19일 미국 밖에서 BTC, ETH, SOL, AVAX, HYPE, XRP 6개 자산으로 출시됐으며, USDC로 정산되고 Deribit 유동성을 쓴다. 미국 개인 이용자는 아직 이용할 수 없다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Coinbase on X, crypto.news")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "timeline",
         "alt": alts("Timeline: Coinbase completed its $2.9 billion Deribit purchase on Aug. 14, 2025, said the integration was complete on Oct. 7, 2026, and launched options for eligible non-U.S. users on Nov. 19, 2026; U.S. access is promised soon via Coinbase Pro with no date", {
            "es": "Cronología: Coinbase completó la compra de Deribit por 2.900 millones de dólares el 14 de agosto de 2025, dio por terminada la integración el 7 de octubre de 2026 y lanzó opciones para usuarios elegibles fuera de EE. UU. el 19 de noviembre de 2026; el acceso en EE. UU. llegará pronto vía Coinbase Pro, sin fecha",
            "pt": "Linha do tempo: a Coinbase concluiu a compra da Deribit por US$ 2,9 bilhões em 14 de agosto de 2025, anunciou a integração concluída em 7 de outubro de 2026 e lançou opções para usuários elegíveis fora dos EUA em 19 de novembro de 2026; o acesso nos EUA virá em breve via Coinbase Pro, sem data",
            "fr": "Chronologie : Coinbase a finalisé le rachat de Deribit pour 2,9 milliards de dollars le 14 août 2025, a annoncé la fin de l'intégration le 7 octobre 2026 et a lancé les options pour les utilisateurs éligibles hors des États-Unis le 19 novembre 2026 ; l'accès américain est promis bientôt via Coinbase Pro, sans date",
            "de": "Zeitleiste: Coinbase schloss den Kauf von Deribit für 2,9 Mrd. $ am 14. August 2025 ab, meldete die Integration am 7. Oktober 2026 als abgeschlossen und startete Optionen für berechtigte Nutzer außerhalb der USA am 19. November 2026; US-Zugang soll bald über Coinbase Pro kommen, ohne Datum",
            "ru": "Хронология: Coinbase закрыла покупку Deribit за $2,9 млрд 14 августа 2025 года, 7 октября 2026 года объявила о завершении интеграции и 19 ноября 2026 года запустила опционы для подходящих пользователей за пределами США; доступ в США обещан скоро через Coinbase Pro, без даты",
            "tr": "Zaman çizelgesi: Coinbase, Deribit'i 2,9 milyar $'a satın alma işlemini 14 Ağustos 2025'te tamamladı, entegrasyonun bittiğini 7 Ekim 2026'da açıkladı ve 19 Kasım 2026'da ABD dışındaki uygun kullanıcılar için opsiyonları başlattı; ABD erişimi tarih verilmeden yakında Coinbase Pro ile vaat ediliyor",
            "id": "Linimasa: Coinbase menuntaskan pembelian Deribit senilai US$2,9 miliar pada 14 Agustus 2025, menyatakan integrasi selesai pada 7 Oktober 2026, dan meluncurkan opsi bagi pengguna yang memenuhi syarat di luar AS pada 19 November 2026; akses AS dijanjikan segera lewat Coinbase Pro tanpa tanggal",
            "ja": "年表：コインベースは2025年8月14日に29億ドルのDeribit買収を完了、2026年10月7日に統合完了を発表し、2026年11月19日に米国外の対象ユーザー向けにオプションを開始。米国ではCoinbase Proで「近く」提供予定だが日付は未定",
            "ko": "연표: 코인베이스는 2025년 8월 14일 29억 달러 규모의 Deribit 인수를 마무리했고, 2026년 10월 7일 통합 완료를 발표했으며, 2026년 11월 19일 미국 외 적격 이용자에게 옵션을 출시했다. 미국 출시는 날짜 없이 Coinbase Pro를 통해 '곧' 이뤄질 예정이다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Coinbase, crypto.news, Brian Armstrong on X")},
    ]


def build_ibit_record_outflow():
    slug = "blackrock-ibit-record-541-million-outflow-nov-2026"
    d = OUT / slug
    # Farside Investors, all-data table read Nov 20, 2026 ~8 a.m. CST: IBIT's five largest daily net outflows since Jan 2024.
    labels = ["Nov 14, 2025", "Nov 18, 2025", "May 27, 2026", "Jan 30, 2026", "Nov 19, 2026"]
    vals = [463.1, 523.2, 527.8, 528.3, 541.1]
    chart = make_bar_chart(
        d / "chart-ibit-largest-daily-outflows",
        labels, vals,
        "IBIT's five largest one-day net outflows (US$ millions)",
        colors=["#64748b"] * 4 + ["#f7931a"],
        value_fmt=lambda v: f"-${v:,.1f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    # Farside daily totals Nov 2-19, 2026 (14 sessions) summed by PlainBTC: -$3,467.8M; IBIT -$2,940.7M; inflows only Nov 4 and Nov 16.
    fact = make_fact_card(
        d / "fact-3-47-billion-november-outflows",
        "U.S. spot bitcoin ETFs, November 2026",
        "-$3.47 billion",
        "Net outflows from Nov. 2 to Nov. 19, with withdrawals on 12 of 14 trading days. BlackRock's IBIT alone: -$2.94 billion.",
        footer="Farside Investors daily flows, summed by PlainBTC",
    )
    funds = ["IBIT", "FBTC", "ARKB", "GBTC", "BTCW", "MSBT"]
    fv = [-541.1, -45.9, -31.3, -13.9, 0.3, 49.6]
    funds_img = make_bar_chart(
        d / "chart-btc-etf-flows-by-fund-nov-19",
        funds, fv,
        "Spot bitcoin ETF net flows by fund, Nov. 19, 2026 (US$ millions)",
        colors=["#34d399" if v > 0 else "#f87171" for v in fv],
        value_fmt=lambda v: f"{v:+,.1f}",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of the five largest one-day net outflows from BlackRock's iShares Bitcoin Trust (IBIT): $463.1 million on Nov. 14, 2025, $523.2 million on Nov. 18, 2025, $527.8 million on May 27, 2026, $528.3 million on Jan. 30, 2026, and a record $541.1 million on Nov. 19, 2026", {
            "es": "Gráfico de barras de las cinco mayores salidas netas en un día del iShares Bitcoin Trust (IBIT) de BlackRock: 463,1 millones de dólares el 14 de noviembre de 2025, 523,2 millones el 18 de noviembre de 2025, 527,8 millones el 27 de mayo de 2026, 528,3 millones el 30 de enero de 2026 y un récord de 541,1 millones el 19 de noviembre de 2026",
            "pt": "Gráfico de barras dos cinco maiores resgates líquidos em um dia do iShares Bitcoin Trust (IBIT), da BlackRock: US$ 463,1 milhões em 14 de novembro de 2025, US$ 523,2 milhões em 18 de novembro de 2025, US$ 527,8 milhões em 27 de maio de 2026, US$ 528,3 milhões em 30 de janeiro de 2026 e um recorde de US$ 541,1 milhões em 19 de novembro de 2026",
            "fr": "Graphique en barres des cinq plus fortes sorties nettes en une journée de l'iShares Bitcoin Trust (IBIT) de BlackRock : 463,1 millions de dollars le 14 novembre 2025, 523,2 millions le 18 novembre 2025, 527,8 millions le 27 mai 2026, 528,3 millions le 30 janvier 2026 et un record de 541,1 millions le 19 novembre 2026",
            "de": "Balkendiagramm der fünf größten Tagesabflüsse aus BlackRocks iShares Bitcoin Trust (IBIT): 463,1 Mio. $ am 14. November 2025, 523,2 Mio. $ am 18. November 2025, 527,8 Mio. $ am 27. Mai 2026, 528,3 Mio. $ am 30. Januar 2026 und ein Rekord von 541,1 Mio. $ am 19. November 2026",
            "ru": "Столбчатая диаграмма пяти крупнейших дневных чистых оттоков из фонда BlackRock iShares Bitcoin Trust (IBIT): $463,1 млн 14 ноября 2025 года, $523,2 млн 18 ноября 2025 года, $527,8 млн 27 мая 2026 года, $528,3 млн 30 января 2026 года и рекордные $541,1 млн 19 ноября 2026 года",
            "tr": "BlackRock'ın iShares Bitcoin Trust (IBIT) fonundan yaşanan en büyük beş günlük net çıkışın çubuk grafiği: 14 Kasım 2025'te 463,1 milyon $, 18 Kasım 2025'te 523,2 milyon $, 27 Mayıs 2026'da 527,8 milyon $, 30 Ocak 2026'da 528,3 milyon $ ve 19 Kasım 2026'da rekor 541,1 milyon $",
            "id": "Grafik batang lima arus keluar bersih harian terbesar dari iShares Bitcoin Trust (IBIT) milik BlackRock: US$463,1 juta pada 14 November 2025, US$523,2 juta pada 18 November 2025, US$527,8 juta pada 27 Mei 2026, US$528,3 juta pada 30 Januari 2026, dan rekor US$541,1 juta pada 19 November 2026",
            "ja": "ブラックロックのiShares Bitcoin Trust（IBIT）の1日あたり純流出額の上位5日を示す棒グラフ：2025年11月14日に4億6310万ドル、2025年11月18日に5億2320万ドル、2026年5月27日に5億2780万ドル、2026年1月30日に5億2830万ドル、2026年11月19日に過去最大の5億4110万ドル",
            "ko": "블랙록 iShares Bitcoin Trust(IBIT)의 하루 순유출 상위 5일 막대 차트: 2025년 11월 14일 4억6310만 달러, 2025년 11월 18일 5억2320만 달러, 2026년 5월 27일 5억2780만 달러, 2026년 1월 30일 5억2830만 달러, 2026년 11월 19일 사상 최대 5억4110만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: U.S. spot bitcoin ETFs had about $3.47 billion in net outflows from Nov. 2 to Nov. 19, 2026, with withdrawals on 12 of 14 trading days; BlackRock's IBIT alone lost about $2.94 billion, based on Farside Investors data", {
            "es": "Tarjeta: los ETF de bitcoin al contado de EE. UU. registraron salidas netas de unos 3.470 millones de dólares del 2 al 19 de noviembre de 2026, con retiros en 12 de 14 sesiones; solo el IBIT de BlackRock perdió unos 2.940 millones, según datos de Farside Investors",
            "pt": "Cartão: os ETFs de bitcoin à vista dos EUA tiveram saídas líquidas de cerca de US$ 3,47 bilhões de 2 a 19 de novembro de 2026, com resgates em 12 de 14 pregões; só o IBIT, da BlackRock, perdeu cerca de US$ 2,94 bilhões, segundo dados da Farside Investors",
            "fr": "Carte : les ETF bitcoin au comptant américains ont enregistré environ 3,47 milliards de dollars de sorties nettes du 2 au 19 novembre 2026, avec des retraits sur 12 séances sur 14 ; l'IBIT de BlackRock a perdu à lui seul environ 2,94 milliards, selon les données de Farside Investors",
            "de": "Faktenkarte: US-Spot-Bitcoin-ETFs verzeichneten vom 2. bis 19. November 2026 Nettoabflüsse von rund 3,47 Mrd. $, mit Abflüssen an 12 von 14 Handelstagen; allein BlackRocks IBIT verlor rund 2,94 Mrd. $, laut Daten von Farside Investors",
            "ru": "Карточка: чистый отток из американских спотовых биткоин-ETF со 2 по 19 ноября 2026 года составил около $3,47 млрд, деньги уходили в 12 из 14 торговых дней; только из IBIT от BlackRock ушло около $2,94 млрд, по данным Farside Investors",
            "tr": "Bilgi kartı: ABD spot bitcoin ETF'lerinden 2-19 Kasım 2026 arasında yaklaşık 3,47 milyar $ net çıkış oldu, 14 işlem gününün 12'sinde para çekildi; yalnızca BlackRock'ın IBIT fonu yaklaşık 2,94 milyar $ kaybetti, Farside Investors verilerine göre",
            "id": "Kartu fakta: ETF bitcoin spot AS mencatat arus keluar bersih sekitar US$3,47 miliar dari 2 hingga 19 November 2026, dengan penarikan pada 12 dari 14 hari perdagangan; IBIT milik BlackRock sendiri kehilangan sekitar US$2,94 miliar, menurut data Farside Investors",
            "ja": "ファクトカード：米国の現物ビットコインETFは2026年11月2日〜19日に約34億7000万ドルの純流出。14営業日のうち12日で流出し、ブラックロックのIBITだけで約29億4000万ドル（Farside Investorsのデータ）",
            "ko": "팩트 카드: 미국 현물 비트코인 ETF는 2026년 11월 2~19일 약 34억7000만 달러 순유출, 14거래일 중 12일 유출. 블랙록 IBIT 단독 약 29억4000만 달러(Farside Investors 데이터)",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Farside Investors, summed by PlainBTC")},
        {"id": "funds", "file": funds_img.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of U.S. spot bitcoin ETF net flows by fund on Nov. 19, 2026: IBIT minus $541.1 million, FBTC minus $45.9 million, ARKB minus $31.3 million, GBTC minus $13.9 million, BTCW plus $0.3 million and MSBT plus $49.6 million", {
            "es": "Gráfico de barras de los flujos netos de los ETF de bitcoin al contado de EE. UU. por fondo el 19 de noviembre de 2026: IBIT −541,1 millones de dólares, FBTC −45,9 millones, ARKB −31,3 millones, GBTC −13,9 millones, BTCW +0,3 millones y MSBT +49,6 millones",
            "pt": "Gráfico de barras dos fluxos líquidos dos ETFs de bitcoin à vista dos EUA por fundo em 19 de novembro de 2026: IBIT −US$ 541,1 milhões, FBTC −US$ 45,9 milhões, ARKB −US$ 31,3 milhões, GBTC −US$ 13,9 milhões, BTCW +US$ 0,3 milhão e MSBT +US$ 49,6 milhões",
            "fr": "Graphique en barres des flux nets des ETF bitcoin au comptant américains par fonds le 19 novembre 2026 : IBIT −541,1 millions de dollars, FBTC −45,9 millions, ARKB −31,3 millions, GBTC −13,9 millions, BTCW +0,3 million et MSBT +49,6 millions",
            "de": "Balkendiagramm der Nettozuflüsse der US-Spot-Bitcoin-ETFs nach Fonds am 19. November 2026: IBIT −541,1 Mio. $, FBTC −45,9 Mio. $, ARKB −31,3 Mio. $, GBTC −13,9 Mio. $, BTCW +0,3 Mio. $ und MSBT +49,6 Mio. $",
            "ru": "Столбчатая диаграмма чистых потоков американских спотовых биткоин-ETF по фондам 19 ноября 2026 года: IBIT −$541,1 млн, FBTC −$45,9 млн, ARKB −$31,3 млн, GBTC −$13,9 млн, BTCW +$0,3 млн и MSBT +$49,6 млн",
            "tr": "19 Kasım 2026'da ABD spot bitcoin ETF'lerinin fon bazında net akışlarının çubuk grafiği: IBIT −541,1 milyon $, FBTC −45,9 milyon $, ARKB −31,3 milyon $, GBTC −13,9 milyon $, BTCW +0,3 milyon $ ve MSBT +49,6 milyon $",
            "id": "Grafik batang arus bersih ETF bitcoin spot AS per dana pada 19 November 2026: IBIT −US$541,1 juta, FBTC −US$45,9 juta, ARKB −US$31,3 juta, GBTC −US$13,9 juta, BTCW +US$0,3 juta, dan MSBT +US$49,6 juta",
            "ja": "2026年11月19日の米国現物ビットコインETFのファンド別純フローの棒グラフ：IBITはマイナス5億4110万ドル、FBTCはマイナス4590万ドル、ARKBはマイナス3130万ドル、GBTCはマイナス1390万ドル、BTCWはプラス30万ドル、MSBTはプラス4960万ドル",
            "ko": "2026년 11월 19일 미국 현물 비트코인 ETF 펀드별 순흐름 막대 차트: IBIT -5억4110만 달러, FBTC -4590만 달러, ARKB -3130만 달러, GBTC -1390만 달러, BTCW +30만 달러, MSBT +4960만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
    ]


def build_sec_fake_platforms():
    slug = "sec-fake-crypto-platforms-37-million-whatsapp-nov-2026"
    d = OUT / slug
    # SEC complaint (D. Colo., No. 1:26-cv-06302, filed Nov 19, 2026), para. 5 and 52: minimum received at each platform's accumulation address.
    chart = make_bar_chart(
        d / "chart-sec-scam-funds-by-platform",
        ["TBAA\nAug-Dec 2024", "IdeaCrypto\nJan-Jul 2025", "RealSimple\nJul-Dec 2025", "Essential Crypto\nJan-May 2026"],
        [7.32, 13.64, 10.36, 4.22],
        "Money received by each fake platform, per the SEC (US$ millions, at least)",
        colors=["#f87171", "#f87171", "#f87171", "#f87171"],
        value_fmt=lambda v: f"${v:,.2f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    # SEC complaint, paras. 1-5, 54, 56, 58.
    tl = make_timeline_card(
        d / "timeline-sec-fake-platform-scam",
        "How the scheme worked, per the SEC",
        [
            ("Step 1", "A social media ad leads to a WhatsApp chat", (96, 165, 250)),
            ("Step 2", "A fake adviser gives stock tips to win trust", (96, 165, 250)),
            ("Step 3", "Victims buy crypto on a real exchange and send it out", ORANGE),
            ("Step 4", "A fake app shows gains; a fee is demanded to withdraw", RED),
        ],
        footer="SEC complaint, D. Colo., Nov. 19, 2026",
        margin=170, wrap_w=230,
    )
    fact = make_fact_card(
        d / "fact-37-million-1500-investors",
        "SEC complaint, Nov. 19, 2026",
        "$37.4 million",
        "Taken from more than 1,500 U.S. investors between August 2024 and May 2026 by four fake adviser-and-platform pairs, the SEC says.",
        footer="SEC v. Advisor WeChat Capital et al., D. Colo.",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of money received by each fake crypto platform named by the SEC: at least $7.32 million for TBAA from August to December 2024, $13.64 million for IdeaCrypto from January to July 2025, $10.36 million for RealSimple from July to December 2025 and $4.22 million for Essential Crypto from January to May 2026", {
            "es": "Gráfico de barras del dinero recibido por cada plataforma cripto falsa citada por la SEC: al menos 7,32 millones de dólares para TBAA de agosto a diciembre de 2024, 13,64 millones para IdeaCrypto de enero a julio de 2025, 10,36 millones para RealSimple de julio a diciembre de 2025 y 4,22 millones para Essential Crypto de enero a mayo de 2026",
            "pt": "Gráfico de barras do dinheiro recebido por cada plataforma cripto falsa citada pela SEC: pelo menos US$ 7,32 milhões para a TBAA de agosto a dezembro de 2024, US$ 13,64 milhões para a IdeaCrypto de janeiro a julho de 2025, US$ 10,36 milhões para a RealSimple de julho a dezembro de 2025 e US$ 4,22 milhões para a Essential Crypto de janeiro a maio de 2026",
            "fr": "Graphique en barres de l'argent reçu par chaque fausse plateforme crypto citée par la SEC : au moins 7,32 millions de dollars pour TBAA d'août à décembre 2024, 13,64 millions pour IdeaCrypto de janvier à juillet 2025, 10,36 millions pour RealSimple de juillet à décembre 2025 et 4,22 millions pour Essential Crypto de janvier à mai 2026",
            "de": "Balkendiagramm der Gelder, die jede von der SEC genannte falsche Krypto-Plattform erhielt: mindestens 7,32 Mio. $ für TBAA von August bis Dezember 2024, 13,64 Mio. $ für IdeaCrypto von Januar bis Juli 2025, 10,36 Mio. $ für RealSimple von Juli bis Dezember 2025 und 4,22 Mio. $ für Essential Crypto von Januar bis Mai 2026",
            "ru": "Столбчатая диаграмма денег, полученных каждой фальшивой криптоплатформой из иска SEC: не менее $7,32 млн у TBAA с августа по декабрь 2024 года, $13,64 млн у IdeaCrypto с января по июль 2025 года, $10,36 млн у RealSimple с июля по декабрь 2025 года и $4,22 млн у Essential Crypto с января по май 2026 года",
            "tr": "SEC'in adını verdiği her sahte kripto platformunun aldığı paranın çubuk grafiği: Ağustos-Aralık 2024'te TBAA için en az 7,32 milyon $, Ocak-Temmuz 2025'te IdeaCrypto için 13,64 milyon $, Temmuz-Aralık 2025'te RealSimple için 10,36 milyon $ ve Ocak-Mayıs 2026'da Essential Crypto için 4,22 milyon $",
            "id": "Grafik batang uang yang diterima setiap platform kripto palsu yang disebut SEC: setidaknya US$7,32 juta untuk TBAA pada Agustus hingga Desember 2024, US$13,64 juta untuk IdeaCrypto pada Januari hingga Juli 2025, US$10,36 juta untuk RealSimple pada Juli hingga Desember 2025, dan US$4,22 juta untuk Essential Crypto pada Januari hingga Mei 2026",
            "ja": "SECが名指しした偽の暗号資産プラットフォームごとの受取額を示す棒グラフ：TBAA（2024年8月〜12月）が少なくとも732万ドル、IdeaCrypto（2025年1月〜7月）が1364万ドル、RealSimple（2025年7月〜12月）が1036万ドル、Essential Crypto（2026年1月〜5月）が422万ドル",
            "ko": "SEC가 지목한 가짜 암호화폐 플랫폼별 수취액 막대 차트: TBAA(2024년 8~12월) 최소 732만 달러, IdeaCrypto(2025년 1~7월) 1364만 달러, RealSimple(2025년 7~12월) 1036만 달러, Essential Crypto(2026년 1~5월) 422만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="SEC complaint, D. Colo., Nov. 19, 2026")},
        {"id": "steps", "file": tl.name, "w": 1200, "h": 630, "kind": "timeline",
         "alt": alts("Four steps of the scheme described by the SEC: a social media ad leads to a WhatsApp chat; a fake adviser gives stock tips to win trust; victims buy crypto on a real exchange and send it out; a fake app shows gains and a fee is demanded to withdraw", {
            "es": "Los cuatro pasos del esquema descrito por la SEC: un anuncio en redes sociales lleva a un chat de WhatsApp; un falso asesor da consejos sobre acciones para ganarse la confianza; las víctimas compran cripto en un exchange real y la envían fuera; una app falsa muestra ganancias y se exige una comisión para retirar",
            "pt": "As quatro etapas do esquema descrito pela SEC: um anúncio em rede social leva a um chat de WhatsApp; um falso consultor dá dicas de ações para ganhar confiança; as vítimas compram cripto em uma corretora real e a enviam para fora; um app falso mostra ganhos e uma taxa é exigida para sacar",
            "fr": "Les quatre étapes du stratagème décrit par la SEC : une publicité sur les réseaux sociaux mène à un groupe WhatsApp ; un faux conseiller donne des conseils boursiers pour gagner la confiance ; les victimes achètent des cryptos sur une vraie plateforme et les envoient ailleurs ; une fausse appli affiche des gains et des frais sont exigés pour retirer",
            "de": "Die vier Schritte des von der SEC beschriebenen Betrugs: Eine Social-Media-Anzeige führt in einen WhatsApp-Chat; ein falscher Berater gibt Aktientipps, um Vertrauen zu gewinnen; Opfer kaufen Krypto bei einer echten Börse und senden es weiter; eine falsche App zeigt Gewinne, und für die Auszahlung wird eine Gebühr verlangt",
            "ru": "Четыре шага схемы, описанной SEC: реклама в соцсетях ведет в чат WhatsApp; фальшивый советник дает советы по акциям, чтобы завоевать доверие; жертвы покупают криптовалюту на настоящей бирже и отправляют ее дальше; фальшивое приложение показывает прибыль, а за вывод требуют комиссию",
            "tr": "SEC'in anlattığı planın dört adımı: sosyal medya reklamı bir WhatsApp sohbetine götürüyor; sahte bir danışman güven kazanmak için hisse tavsiyeleri veriyor; mağdurlar gerçek bir borsadan kripto alıp dışarı gönderiyor; sahte bir uygulama kazanç gösteriyor ve para çekmek için ücret isteniyor",
            "id": "Empat langkah skema yang dijelaskan SEC: iklan media sosial mengarah ke obrolan WhatsApp; penasihat palsu memberi tips saham untuk meraih kepercayaan; korban membeli kripto di bursa sungguhan lalu mengirimkannya keluar; aplikasi palsu menampilkan keuntungan dan biaya diminta untuk penarikan",
            "ja": "SECが説明する手口の4段階：SNS広告からWhatsAppのチャットへ誘導、偽のアドバイザーが株の助言で信頼を得る、被害者が本物の取引所で暗号資産を買って外部へ送金、偽アプリが利益を表示し出金に手数料を要求",
            "ko": "SEC가 설명한 수법의 4단계: SNS 광고가 왓츠앱 채팅으로 유도, 가짜 자문가가 주식 팁으로 신뢰 확보, 피해자가 실제 거래소에서 암호화폐를 사서 외부로 송금, 가짜 앱이 수익을 보여 주고 출금에 수수료 요구",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="SEC complaint, D. Colo., Nov. 19, 2026")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the SEC says about $37.4 million was taken from more than 1,500 U.S. investors between August 2024 and May 2026 by four fake adviser-and-platform pairs", {
            "es": "Tarjeta: la SEC afirma que unos 37,4 millones de dólares fueron sustraídos a más de 1.500 inversores estadounidenses entre agosto de 2024 y mayo de 2026 por cuatro parejas falsas de asesor y plataforma",
            "pt": "Cartão: a SEC diz que cerca de US$ 37,4 milhões foram tirados de mais de 1.500 investidores dos EUA entre agosto de 2024 e maio de 2026 por quatro pares falsos de consultor e plataforma",
            "fr": "Carte : selon la SEC, environ 37,4 millions de dollars ont été soutirés à plus de 1 500 investisseurs américains entre août 2024 et mai 2026 par quatre faux duos conseiller-plateforme",
            "de": "Faktenkarte: Laut SEC wurden zwischen August 2024 und Mai 2026 rund 37,4 Mio. $ von mehr als 1.500 US-Anlegern durch vier falsche Berater-Plattform-Paare erbeutet",
            "ru": "Карточка: по данным SEC, с августа 2024 по май 2026 года четыре фальшивые пары «советник и платформа» забрали около $37,4 млн у более чем 1500 американских инвесторов",
            "tr": "Bilgi kartı: SEC'e göre Ağustos 2024 ile Mayıs 2026 arasında dört sahte danışman-platform ikilisi 1.500'den fazla ABD'li yatırımcıdan yaklaşık 37,4 milyon $ aldı",
            "id": "Kartu fakta: SEC menyebut sekitar US$37,4 juta diambil dari lebih dari 1.500 investor AS antara Agustus 2024 dan Mei 2026 oleh empat pasangan penasihat dan platform palsu",
            "ja": "ファクトカード：SECによると、2024年8月〜2026年5月に偽のアドバイザーとプラットフォームの4組が1500人超の米国投資家から約3740万ドルを奪った",
            "ko": "팩트 카드: SEC에 따르면 2024년 8월~2026년 5월 가짜 자문사·플랫폼 4쌍이 미국 투자자 1500명 이상에게서 약 3740만 달러를 가로챘다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="SEC complaint, D. Colo., Nov. 19, 2026")},
    ]



def build_btc_below_59k_2026_low():
    slug = "bitcoin-below-59000-near-2026-low-liquidations-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD hourly closes, Nov 18 00:00 UTC to Nov 20 19:00 UTC (1 p.m. CST). Nov 20 low $58,005.00 (18:00 UTC hour).
    # 2026 low on Kraken daily candles: $57,740.0 on Jul 1, 2026.
    xs, ys = fetch_kraken_hourly(1794960000, 1795201200, pair="XBTUSD")
    chart = make_line_chart(
        d / "chart-btc-hourly-nov-18-20",
        xs, ys,
        title="Bitcoin hourly price, Nov. 18-20, 2026 (Kraken, UTC)",
        hline=57740.0,
        hlabel="2026 low on Kraken: $57,740 (July 1)",
        date_fmt="%b %d, %H:00",
    )
    fact = make_fact_card(
        d / "fact-1-5-billion-liquidations",
        "Crypto liquidations, 24 hours to Nov. 20, 2026",
        "$1.5 billion",
        "Leveraged crypto positions closed out automatically as prices fell, according to CoinGlass data.",
        footer="CoinGlass data via CoinDesk, Nov. 20, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's hourly price on Kraken from Nov. 18 to Nov. 20, 2026, drifting between about $61,000 and $65,000 and then dropping below $59,000 on Nov. 20, close to a dashed line at the 2026 low of $57,740 from July 1", {
            "es": "Gráfico de líneas del precio horario de bitcoin en Kraken del 18 al 20 de noviembre de 2026: oscila entre unos 61.000 y 65.000 dólares y el 20 de noviembre cae por debajo de 59.000, cerca de una línea discontinua en el mínimo de 2026, 57.740 dólares, del 1 de julio",
            "pt": "Gráfico de linha do preço horário do bitcoin na Kraken de 18 a 20 de novembro de 2026: oscila entre cerca de US$ 61.000 e US$ 65.000 e, em 20 de novembro, cai abaixo de US$ 59.000, perto de uma linha tracejada na mínima de 2026, US$ 57.740, de 1º de julho",
            "fr": "Courbe du cours horaire du bitcoin sur Kraken du 18 au 20 novembre 2026 : il évolue entre environ 61 000 et 65 000 dollars, puis passe sous 59 000 dollars le 20 novembre, près d'une ligne pointillée au plus bas de 2026, 57 740 dollars, du 1er juillet",
            "de": "Liniendiagramm des stündlichen Bitcoin-Kurses bei Kraken vom 18. bis 20. November 2026: Seitwärtsbewegung zwischen rund 61.000 und 65.000 $, dann am 20. November Fall unter 59.000 $, nahe einer gestrichelten Linie beim Jahrestief 2026 von 57.740 $ vom 1. Juli",
            "ru": "Линейный график почасовой цены биткоина на Kraken с 18 по 20 ноября 2026 года: колебания примерно между $61 000 и $65 000, затем 20 ноября падение ниже $59 000, близко к пунктирной линии минимума 2026 года — $57 740 от 1 июля",
            "tr": "Bitcoin'in 18-20 Kasım 2026'da Kraken'deki saatlik fiyatının çizgi grafiği: yaklaşık 61.000 $ ile 65.000 $ arasında dolaşıyor, ardından 20 Kasım'da 59.000 $'ın altına iniyor; kesikli çizgi 1 Temmuz'daki 57.740 $'lık 2026 dibini gösteriyor",
            "id": "Grafik garis harga bitcoin per jam di Kraken pada 18 hingga 20 November 2026: bergerak di kisaran US$61.000 hingga US$65.000, lalu pada 20 November turun di bawah US$59.000, dekat garis putus-putus di level terendah 2026 sebesar US$57.740 pada 1 Juli",
            "ja": "2026年11月18〜20日のKrakenにおけるビットコイン1時間足の折れ線グラフ：約6万1000〜6万5000ドルで推移した後、11月20日に5万9000ドルを割り込み、7月1日の2026年安値5万7740ドルを示す破線に接近",
            "ko": "2026년 11월 18~20일 크라켄 비트코인 시간별 가격 선 차트: 약 6만1000~6만5000달러에서 움직이다 11월 20일 5만9000달러 아래로 떨어져, 7월 1일 기록한 2026년 저점 5만7740달러를 나타내는 점선에 근접",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD hourly closes")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $1.5 billion in leveraged crypto positions were liquidated in the 24 hours to Nov. 20, 2026, according to CoinGlass data cited by CoinDesk", {
            "es": "Tarjeta: unos 1.500 millones de dólares en posiciones apalancadas de cripto se liquidaron en las 24 horas hasta el 20 de noviembre de 2026, según datos de CoinGlass citados por CoinDesk",
            "pt": "Cartão: cerca de US$ 1,5 bilhão em posições alavancadas de cripto foram liquidadas nas 24 horas até 20 de novembro de 2026, segundo dados da CoinGlass citados pela CoinDesk",
            "fr": "Carte : environ 1,5 milliard de dollars de positions crypto à effet de levier ont été liquidées sur les 24 heures précédant le 20 novembre 2026, selon les données de CoinGlass citées par CoinDesk",
            "de": "Faktenkarte: In den 24 Stunden bis zum 20. November 2026 wurden gehebelte Krypto-Positionen im Wert von rund 1,5 Mrd. $ liquidiert, laut CoinGlass-Daten, zitiert von CoinDesk",
            "ru": "Карточка: за 24 часа до 20 ноября 2026 года было ликвидировано около $1,5 млрд в криптопозициях с плечом, по данным CoinGlass, которые приводит CoinDesk",
            "tr": "Kart: CoinDesk'in aktardığı CoinGlass verilerine göre 20 Kasım 2026'ya kadarki 24 saatte yaklaşık 1,5 milyar $'lık kaldıraçlı kripto pozisyonu tasfiye edildi",
            "id": "Kartu: sekitar US$1,5 miliar posisi kripto berleverage dilikuidasi dalam 24 jam hingga 20 November 2026, menurut data CoinGlass yang dikutip CoinDesk",
            "ja": "カード：CoinDeskが引用したCoinGlassのデータによると、2026年11月20日までの24時間に約15億ドル相当のレバレッジ付き暗号資産ポジションが強制清算された",
            "ko": "카드: 코인데스크가 인용한 코인글래스 자료에 따르면 2026년 11월 20일까지 24시간 동안 약 15억 달러 규모의 레버리지 암호화폐 포지션이 강제 청산됐다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via CoinDesk")},
    ]


def build_btc_55100_rebound():
    slug = "bitcoin-crashes-to-55100-rebounds-above-60000-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD 15-minute candles, Nov 20 12:00 UTC to Nov 21 14:00 UTC (Nov 20 6 a.m. to Nov 21 8 a.m. CST), closes plotted.
    # Frozen in i18n/content/<slug>/chart-data.json as [ts, close, low, high] (Kraken keeps only ~7 days of 15-minute candles).
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    xs = np.array([r[0] - 6 * 3600 for r in rows], dtype=float)   # shift to U.S. Central (CST, UTC-6) for axis labels
    ys = np.array([r[1] for r in rows])
    chart = make_line_chart(
        d / "chart-btc-15min-nov-20-21",
        xs, ys,
        title="Bitcoin on Nov. 20-21, 2026: 15-minute closes on Kraken (U.S. Central time)",
        hline=57740.0,
        hlabel="Previous 2026 low: $57,740 (July 1)",
        date_fmt="%b %d, %-I %p",
    )
    fact = make_fact_card(
        d / "fact-2-4-billion-liquidated",
        "Liquidated in 24 hours",
        "$2.40 billion",
        "Leveraged crypto futures bets closed by force; more than $1 billion in bitcoin and $545 million in ether",
        footer="Source: CoinGlass via CoinDesk, Nov. 21, 2026",
    )
    etf = make_bar_chart(
        d / "chart-btc-etf-flows-nov-16-20",
        ["Mon 16", "Tue 17", "Wed 18", "Thu 19", "Fri 20*"],
        [7.9, -239.9, -306.5, -582.3, -124.5],
        title="U.S. spot bitcoin ETF net flows, Nov. 16-20, 2026 (*Friday without IBIT)",
        colors=["#34d399", "#f87171", "#f87171", "#f87171", "#fca5a5"],
        value_fmt=lambda v: f"{'+' if v > 0 else '−'}${abs(v):,.1f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's 15-minute closing prices on Kraken from 6 a.m. Central time on Nov. 20 to 8 a.m. on Nov. 21, 2026: the price slides from about $62,000 to near $59,000, drops below a dashed line marking the previous 2026 low of $57,740, bottoms near $55,100 just after midnight, then climbs back above $60,000", {
            "es": "Gráfico de líneas de los precios de cierre de 15 minutos de bitcoin en Kraken desde las 6:00 (hora del centro de EE. UU.) del 20 de noviembre hasta las 8:00 del 21 de noviembre de 2026: el precio baja de unos 62.000 dólares a cerca de 59.000, cae por debajo de una línea discontinua en el mínimo anterior de 2026, 57.740 dólares, toca fondo cerca de 55.100 poco después de medianoche y vuelve a superar los 60.000",
            "pt": "Gráfico de linha dos preços de fechamento de 15 minutos do bitcoin na Kraken das 6h (horário central dos EUA) de 20 de novembro às 8h de 21 de novembro de 2026: o preço recua de cerca de US$ 62.000 para perto de US$ 59.000, cai abaixo de uma linha tracejada na mínima anterior de 2026, US$ 57.740, chega ao fundo perto de US$ 55.100 logo após a meia-noite e volta a superar US$ 60.000",
            "fr": "Courbe des cours de clôture sur 15 minutes du bitcoin sur Kraken, de 6 h (heure du Centre des États-Unis) le 20 novembre à 8 h le 21 novembre 2026 : le cours glisse d'environ 62 000 dollars vers 59 000, passe sous une ligne pointillée marquant l'ancien plus bas de 2026, 57 740 dollars, touche un creux vers 55 100 dollars peu après minuit, puis repasse au-dessus de 60 000 dollars",
            "de": "Liniendiagramm der 15-Minuten-Schlusskurse von Bitcoin bei Kraken von 6 Uhr (US-Zentralzeit) am 20. November bis 8 Uhr am 21. November 2026: Der Kurs rutscht von etwa 62.000 $ auf knapp 59.000 $, fällt unter eine gestrichelte Linie beim bisherigen Jahrestief 2026 von 57.740 $, erreicht kurz nach Mitternacht ein Tief nahe 55.100 $ und steigt dann wieder über 60.000 $",
            "ru": "Линейный график 15-минутных цен закрытия биткоина на Kraken с 6:00 по центральному времени США 20 ноября до 8:00 21 ноября 2026 года: цена сползает примерно с $62 000 к $59 000, опускается ниже пунктирной линии прежнего минимума 2026 года — $57 740, вскоре после полуночи достигает дна около $55 100, затем снова поднимается выше $60 000",
            "tr": "Bitcoin'in Kraken'deki 15 dakikalık kapanış fiyatlarının 20 Kasım ABD Merkez saatiyle 06.00'dan 21 Kasım 2026 08.00'e kadarki çizgi grafiği: fiyat yaklaşık 62.000 $'dan 59.000 $ civarına geriliyor, 2026'nın önceki dibi olan 57.740 $'ı gösteren kesikli çizginin altına iniyor, gece yarısından hemen sonra 55.100 $ civarında dip yapıyor, ardından yeniden 60.000 $'ın üzerine çıkıyor",
            "id": "Grafik garis harga penutupan 15 menit bitcoin di Kraken dari pukul 06.00 waktu Tengah AS pada 20 November hingga pukul 08.00 pada 21 November 2026: harga turun dari sekitar US$62.000 ke dekat US$59.000, jatuh di bawah garis putus-putus di level terendah 2026 sebelumnya, US$57.740, menyentuh titik terendah dekat US$55.100 sesaat setelah tengah malam, lalu naik lagi di atas US$60.000",
            "ja": "2026年11月20日午前6時（米中部時間）から11月21日午前8時までのKrakenにおけるビットコインの15分足終値の折れ線グラフ。約6万2000ドルから5万9000ドル付近まで下げた後、2026年のこれまでの安値5万7740ドルを示す破線を割り込み、深夜0時過ぎに5万5100ドル付近で底を打ち、その後6万ドルを上回るまで回復している",
            "ko": "2026년 11월 20일 오전 6시(미국 중부시간)부터 11월 21일 오전 8시까지 크라켄의 비트코인 15분 종가 선 그래프. 가격은 약 6만2000달러에서 5만9000달러 근처로 밀린 뒤 2026년 이전 저점 5만7740달러를 나타내는 점선 아래로 떨어지고, 자정 직후 5만5100달러 근처에서 바닥을 찍은 다음 다시 6만 달러 위로 올라선다",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: about $2.40 billion in leveraged crypto futures bets were liquidated over 24 hours to Nov. 21, 2026, including more than $1 billion in bitcoin and $545 million in ether, according to CoinGlass data cited by CoinDesk", {
            "es": "Tarjeta: unos 2.400 millones de dólares en apuestas apalancadas con futuros cripto se liquidaron en las 24 horas hasta el 21 de noviembre de 2026, más de 1.000 millones en bitcoin y 545 millones en ether, según datos de CoinGlass citados por CoinDesk",
            "pt": "Cartão: cerca de US$ 2,40 bilhões em apostas alavancadas com futuros de cripto foram liquidados nas 24 horas até 21 de novembro de 2026, mais de US$ 1 bilhão em bitcoin e US$ 545 milhões em ether, segundo dados da CoinGlass citados pelo CoinDesk",
            "fr": "Carte : environ 2,40 milliards de dollars de paris à effet de levier sur des contrats à terme crypto ont été liquidés en 24 heures jusqu'au 21 novembre 2026, dont plus d'un milliard en bitcoin et 545 millions en ether, selon des données de CoinGlass citées par CoinDesk",
            "de": "Faktenkarte: Rund 2,40 Mrd. $ an gehebelten Krypto-Futures-Wetten wurden in den 24 Stunden bis zum 21. November 2026 liquidiert, davon über 1 Mrd. $ in Bitcoin und 545 Mio. $ in Ether, laut von CoinDesk zitierten CoinGlass-Daten",
            "ru": "Карточка: за 24 часа до 21 ноября 2026 года было принудительно закрыто около $2,40 млрд кредитных ставок на криптофьючерсах, из них более $1 млрд в биткоине и $545 млн в эфире, по данным CoinGlass, которые приводит CoinDesk",
            "tr": "Kart: CoinDesk'in aktardığı CoinGlass verilerine göre 21 Kasım 2026'ya kadarki 24 saatte yaklaşık 2,40 milyar $'lık kaldıraçlı kripto vadeli pozisyonu tasfiye edildi; bunun 1 milyar $'dan fazlası bitcoin, 545 milyon $'ı ether",
            "id": "Kartu: sekitar US$2,40 miliar posisi berjangka kripto berleverage dilikuidasi dalam 24 jam hingga 21 November 2026, termasuk lebih dari US$1 miliar di bitcoin dan US$545 juta di ether, menurut data CoinGlass yang dikutip CoinDesk",
            "ja": "カード：CoinDeskが引用したCoinGlassのデータによると、2026年11月21日までの24時間に約24億ドル相当のレバレッジ付き暗号資産先物ポジションが強制清算され、うちビットコインが10億ドル超、イーサが5億4500万ドルだった",
            "ko": "카드: 코인데스크가 인용한 코인글래스 자료에 따르면 2026년 11월 21일까지 24시간 동안 약 24억 달러 규모의 레버리지 암호화폐 선물 포지션이 강제 청산됐으며, 이 중 비트코인이 10억 달러 이상, 이더가 5억4500만 달러였다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CoinGlass via CoinDesk")},
        {"id": "etf", "file": etf.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of daily net flows for U.S. spot bitcoin ETFs from Nov. 16 to Nov. 20, 2026: plus $7.9 million on Monday, minus $239.9 million on Tuesday, minus $306.5 million on Wednesday, minus $582.3 million on Thursday and minus $124.5 million on Friday, with BlackRock's IBIT not yet reported for Friday", {
            "es": "Gráfico de barras de los flujos netos diarios de los ETF de bitcoin al contado de EE. UU. del 16 al 20 de noviembre de 2026: +7,9 millones de dólares el lunes, −239,9 millones el martes, −306,5 millones el miércoles, −582,3 millones el jueves y −124,5 millones el viernes, todavía sin el dato de IBIT de BlackRock para el viernes",
            "pt": "Gráfico de barras dos fluxos líquidos diários dos ETFs de bitcoin à vista dos EUA de 16 a 20 de novembro de 2026: +US$ 7,9 milhões na segunda, −US$ 239,9 milhões na terça, −US$ 306,5 milhões na quarta, −US$ 582,3 milhões na quinta e −US$ 124,5 milhões na sexta, ainda sem o dado do IBIT da BlackRock para sexta",
            "fr": "Graphique en barres des flux nets quotidiens des ETF bitcoin au comptant américains du 16 au 20 novembre 2026 : +7,9 millions de dollars lundi, −239,9 millions mardi, −306,5 millions mercredi, −582,3 millions jeudi et −124,5 millions vendredi, sans le chiffre de l'IBIT de BlackRock pour vendredi",
            "de": "Balkendiagramm der täglichen Nettozuflüsse der US-Spot-Bitcoin-ETFs vom 16. bis 20. November 2026: +7,9 Mio. $ am Montag, −239,9 Mio. $ am Dienstag, −306,5 Mio. $ am Mittwoch, −582,3 Mio. $ am Donnerstag und −124,5 Mio. $ am Freitag, ohne den noch fehlenden Freitagswert von BlackRocks IBIT",
            "ru": "Столбчатая диаграмма дневных чистых потоков американских спотовых биткоин-ETF с 16 по 20 ноября 2026 года: +$7,9 млн в понедельник, −$239,9 млн во вторник, −$306,5 млн в среду, −$582,3 млн в четверг и −$124,5 млн в пятницу, без ещё не опубликованных данных IBIT от BlackRock за пятницу",
            "tr": "16-20 Kasım 2026 arasında ABD spot bitcoin ETF'lerinin günlük net akışlarının çubuk grafiği: pazartesi +7,9 milyon $, salı −239,9 milyon $, çarşamba −306,5 milyon $, perşembe −582,3 milyon $ ve cuma −124,5 milyon $; BlackRock'ın IBIT fonunun cuma verisi henüz yok",
            "id": "Grafik batang arus bersih harian ETF bitcoin spot AS dari 16 hingga 20 November 2026: +US$7,9 juta pada Senin, −US$239,9 juta pada Selasa, −US$306,5 juta pada Rabu, −US$582,3 juta pada Kamis, dan −US$124,5 juta pada Jumat, tanpa data IBIT BlackRock untuk Jumat yang belum dirilis",
            "ja": "2026年11月16日〜20日の米国現物ビットコインETFの日次純フローの棒グラフ：月曜はプラス790万ドル、火曜はマイナス2億3990万ドル、水曜はマイナス3億650万ドル、木曜はマイナス5億8230万ドル、金曜はマイナス1億2450万ドル。金曜はブラックロックのIBITの数字が未発表",
            "ko": "2026년 11월 16~20일 미국 현물 비트코인 ETF 일별 순흐름 막대 차트: 월요일 +790만 달러, 화요일 -2억3990만 달러, 수요일 -3억650만 달러, 목요일 -5억8230만 달러, 금요일 -1억2450만 달러. 금요일 블랙록 IBIT 수치는 아직 미발표",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
    ]


def build_btc_new_2026_low():
    slug = "bitcoin-new-2026-low-57661-strategy-shares-sink-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD 15-minute candles, Nov 20 00:00 to 23:45 UTC (Nov 19 6 p.m. to Nov 20 5:45 p.m. CST), lows plotted.
    # Data frozen in i18n/content/<slug>/chart-data.json (Kraken keeps only ~7 days of 15-minute candles).
    cache = I18N / slug / "chart-data.json"
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        req = urllib.request.Request("https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=15", headers={"User-Agent": "PlainBTC/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        rows = [[int(r[0]), float(r[3])] for r in next(v for k, v in data["result"].items() if k != "last")
                if 1795132800 <= int(r[0]) < 1795219200]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    xs = np.array([r[0] - 6 * 3600 for r in rows], dtype=float)   # shift to U.S. Central (CST, UTC-6) for axis labels
    ys = np.array([r[1] for r in rows])
    chart = make_line_chart(
        d / "chart-btc-15min-lows-nov-20",
        xs, ys,
        title="Bitcoin on Nov. 19-20, 2026: 15-minute lows on Kraken (U.S. Central time)",
        hline=57740.0,
        hlabel="Previous 2026 low: $57,740 (July 1)",
        date_fmt="%b %d, %-I %p",
    )
    comp = make_compare_card(
        d / "compare-july-1-vs-nov-20-lows",
        "Bitcoin's two 2026 lows",
        "July 1, 2026",
        "Nov. 20, 2026",
        [
            ("Kraken low", "$57,740.00", "$57,661.10"),
            ("Coinbase low", "$57,717.55", "$57,655.17"),
            ("Kraken close", "$59,959.40", "$58,806.30"),
        ],
        footer="Kraken and Coinbase public BTC/USD daily candles (UTC days)",
    )
    mstr = make_bar_chart(
        d / "chart-strategy-mstr-closes-nov-16-20",
        ["Mon 16", "Tue 17", "Wed 18", "Thu 19", "Fri 20"],
        [103.03, 96.50, 90.32, 86.13, 77.80],
        title="Strategy (MSTR) closing share price, Nov. 16-20, 2026",
        value_fmt=lambda v: f"${v:,.2f}",
        axis_fmt=lambda x, _p: f"${x:,.0f}",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's 15-minute lows on Kraken from 6 p.m. Central time on Nov. 19 to late afternoon on Nov. 20, 2026: the price holds near $61,000 to $62,000, falls sharply from 9 a.m., dips just below a dashed line marking the previous 2026 low of $57,740 around 1:30 p.m., then recovers toward $58,800", {
            "es": "Gráfico de líneas de los mínimos de 15 minutos de bitcoin en Kraken desde las 18:00 (hora del centro de EE. UU.) del 19 de noviembre hasta la tarde del 20 de noviembre de 2026: el precio se mantiene cerca de 61.000-62.000 dólares, cae con fuerza desde las 9:00, baja justo por debajo de una línea discontinua en el mínimo anterior de 2026, 57.740 dólares, hacia las 13:30 y luego se recupera hacia 58.800",
            "pt": "Gráfico de linha das mínimas de 15 minutos do bitcoin na Kraken das 18h (horário central dos EUA) de 19 de novembro até o fim da tarde de 20 de novembro de 2026: o preço fica perto de US$ 61.000 a US$ 62.000, cai forte a partir das 9h, passa um pouco abaixo de uma linha tracejada na mínima anterior de 2026, US$ 57.740, por volta das 13h30 e depois se recupera para perto de US$ 58.800",
            "fr": "Courbe des plus bas sur 15 minutes du bitcoin sur Kraken, de 18 h (heure du Centre des États-Unis) le 19 novembre à la fin d'après-midi du 20 novembre 2026 : le cours reste vers 61 000 à 62 000 dollars, chute à partir de 9 h, passe juste sous une ligne pointillée marquant l'ancien plus bas de 2026, 57 740 dollars, vers 13 h 30, puis remonte vers 58 800 dollars",
            "de": "Liniendiagramm der 15-Minuten-Tiefs von Bitcoin bei Kraken von 18 Uhr (US-Zentralzeit) am 19. November bis zum späten Nachmittag des 20. November 2026: Der Kurs hält sich bei 61.000 bis 62.000 $, fällt ab 9 Uhr stark, rutscht gegen 13:30 Uhr knapp unter eine gestrichelte Linie beim bisherigen Jahrestief 2026 von 57.740 $ und erholt sich dann Richtung 58.800 $",
            "ru": "Линейный график 15-минутных минимумов биткоина на Kraken с 18:00 по центральному времени США 19 ноября до вечера 20 ноября 2026 года: цена держится около $61 000–62 000, с 9:00 резко падает, около 13:30 опускается чуть ниже пунктирной линии прежнего минимума 2026 года — $57 740, затем восстанавливается к $58 800",
            "tr": "Bitcoin'in Kraken'deki 15 dakikalık diplerinin 19 Kasım ABD Merkez saatiyle 18.00'den 20 Kasım 2026 akşamüstüne kadarki çizgi grafiği: fiyat 61.000-62.000 $ civarında kalıyor, 09.00'dan itibaren sert düşüyor, 13.30 civarında 2026'nın önceki dibi olan 57.740 $'ı gösteren kesikli çizginin hemen altına iniyor, ardından 58.800 $'a doğru toparlanıyor",
            "id": "Grafik garis harga terendah 15 menit bitcoin di Kraken dari pukul 18.00 waktu Tengah AS pada 19 November hingga sore 20 November 2026: harga bertahan di sekitar US$61.000-62.000, turun tajam sejak pukul 09.00, sempat sedikit di bawah garis putus-putus di level terendah 2026 sebelumnya, US$57.740, sekitar pukul 13.30, lalu pulih ke sekitar US$58.800",
            "ja": "2026年11月19日午後6時（米中部時間）から11月20日夕方までのKrakenにおけるビットコインの15分足安値の折れ線グラフ。6万1000〜6万2000ドル付近で推移した後、午前9時から急落し、午後1時半ごろに2026年のこれまでの安値5万7740ドルを示す破線をわずかに下回り、その後5万8800ドル付近まで戻している",
            "ko": "2026년 11월 19일 오후 6시(미국 중부시간)부터 11월 20일 늦은 오후까지 크라켄의 비트코인 15분봉 저가 선 그래프. 6만1000~6만2000달러 부근에서 움직이다 오전 9시부터 급락해 오후 1시 30분쯤 이전 2026년 저점인 5만7740달러를 나타낸 점선을 살짝 밑돈 뒤 5만8800달러 부근으로 회복한다",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD 15-minute candles")},
        {"id": "compare", "file": comp.name, "w": 1200, "h": 630, "kind": "compare",
         "alt": alts("Comparison card of bitcoin's two 2026 lows: on July 1 the low was $57,740.00 on Kraken and $57,717.55 on Coinbase; on Nov. 20 it was $57,661.10 on Kraken and $57,655.17 on Coinbase. Kraken's daily close was $59,959.40 on July 1 and $58,806.30 on Nov. 20", {
            "es": "Tarjeta comparativa de los dos mínimos de bitcoin en 2026: el 1 de julio el mínimo fue de 57.740,00 dólares en Kraken y 57.717,55 en Coinbase; el 20 de noviembre, 57.661,10 en Kraken y 57.655,17 en Coinbase. El cierre diario de Kraken fue de 59.959,40 dólares el 1 de julio y 58.806,30 el 20 de noviembre",
            "pt": "Cartão comparativo das duas mínimas do bitcoin em 2026: em 1º de julho a mínima foi de US$ 57.740,00 na Kraken e US$ 57.717,55 na Coinbase; em 20 de novembro, US$ 57.661,10 na Kraken e US$ 57.655,17 na Coinbase. O fechamento diário da Kraken foi de US$ 59.959,40 em 1º de julho e US$ 58.806,30 em 20 de novembro",
            "fr": "Carte comparant les deux plus bas du bitcoin en 2026 : le 1er juillet, 57 740,00 dollars sur Kraken et 57 717,55 sur Coinbase ; le 20 novembre, 57 661,10 sur Kraken et 57 655,17 sur Coinbase. La clôture quotidienne de Kraken était de 59 959,40 dollars le 1er juillet et de 58 806,30 le 20 novembre",
            "de": "Vergleichskarte der beiden Bitcoin-Tiefs 2026: Am 1. Juli lag das Tief bei 57.740,00 $ bei Kraken und 57.717,55 $ bei Coinbase, am 20. November bei 57.661,10 $ bei Kraken und 57.655,17 $ bei Coinbase. Der Tagesschluss bei Kraken lag am 1. Juli bei 59.959,40 $ und am 20. November bei 58.806,30 $",
            "ru": "Карточка сравнения двух минимумов биткоина в 2026 году: 1 июля минимум составил $57 740,00 на Kraken и $57 717,55 на Coinbase; 20 ноября — $57 661,10 на Kraken и $57 655,17 на Coinbase. Дневное закрытие на Kraken: $59 959,40 1 июля и $58 806,30 20 ноября",
            "tr": "Bitcoin'in 2026'daki iki dibini karşılaştıran kart: 1 Temmuz'da dip Kraken'de 57.740,00 $, Coinbase'te 57.717,55 $; 20 Kasım'da Kraken'de 57.661,10 $, Coinbase'te 57.655,17 $. Kraken günlük kapanışı 1 Temmuz'da 59.959,40 $, 20 Kasım'da 58.806,30 $",
            "id": "Kartu perbandingan dua titik terendah bitcoin pada 2026: pada 1 Juli terendahnya US$57.740,00 di Kraken dan US$57.717,55 di Coinbase; pada 20 November US$57.661,10 di Kraken dan US$57.655,17 di Coinbase. Penutupan harian Kraken US$59.959,40 pada 1 Juli dan US$58.806,30 pada 20 November",
            "ja": "2026年のビットコインの2つの安値を比べたカード。7月1日の安値はKrakenで5万7740.00ドル、Coinbaseで5万7717.55ドル。11月20日はKrakenで5万7661.10ドル、Coinbaseで5万7655.17ドル。Krakenの日足終値は7月1日が5万9959.40ドル、11月20日が5万8806.30ドル",
            "ko": "2026년 비트코인의 두 저점을 비교한 카드. 7월 1일 저가는 크라켄 5만7740.00달러, 코인베이스 5만7717.55달러였고, 11월 20일은 크라켄 5만7661.10달러, 코인베이스 5만7655.17달러였다. 크라켄 일봉 종가는 7월 1일 5만9959.40달러, 11월 20일 5만8806.30달러",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Kraken and Coinbase public market data")},
        {"id": "mstr", "file": mstr.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of Strategy's (MSTR) closing share price from Nov. 16 to Nov. 20, 2026, falling every day: $103.03, $96.50, $90.32, $86.13 and $77.80", {
            "es": "Gráfico de barras del precio de cierre de la acción de Strategy (MSTR) del 16 al 20 de noviembre de 2026, que baja cada día: 103,03, 96,50, 90,32, 86,13 y 77,80 dólares",
            "pt": "Gráfico de barras do preço de fechamento da ação da Strategy (MSTR) de 16 a 20 de novembro de 2026, em queda todos os dias: US$ 103,03, US$ 96,50, US$ 90,32, US$ 86,13 e US$ 77,80",
            "fr": "Diagramme en barres du cours de clôture de l'action Strategy (MSTR) du 16 au 20 novembre 2026, en baisse chaque jour : 103,03, 96,50, 90,32, 86,13 et 77,80 dollars",
            "de": "Balkendiagramm der Schlusskurse der Strategy-Aktie (MSTR) vom 16. bis 20. November 2026, die jeden Tag fallen: 103,03 $, 96,50 $, 90,32 $, 86,13 $ und 77,80 $",
            "ru": "Столбчатая диаграмма цены закрытия акций Strategy (MSTR) с 16 по 20 ноября 2026 года, которая снижалась каждый день: $103,03, $96,50, $90,32, $86,13 и $77,80",
            "tr": "Strategy (MSTR) hissesinin 16-20 Kasım 2026 kapanış fiyatlarını gösteren ve her gün düşen sütun grafiği: 103,03 $, 96,50 $, 90,32 $, 86,13 $ ve 77,80 $",
            "id": "Grafik batang harga penutupan saham Strategy (MSTR) dari 16 hingga 20 November 2026 yang turun setiap hari: US$103,03, US$96,50, US$90,32, US$86,13, dan US$77,80",
            "ja": "2026年11月16日〜20日のストラテジー（MSTR）株の終値の棒グラフ。毎日下落し、103.03ドル、96.50ドル、90.32ドル、86.13ドル、77.80ドル",
            "ko": "2026년 11월 16~20일 스트래티지(MSTR) 주가 종가 막대 그래프. 매일 하락해 103.03달러, 96.50달러, 90.32달러, 86.13달러, 77.80달러를 기록했다",
         }),
         "caption": tr_map(CAPTION_CHART, src="Yahoo Finance daily closes (Nasdaq: MSTR)")},
    ]


def build_kraken_cad_crash():
    slug = "kraken-bitcoin-cad-flash-crash-24250-trades-stand-nov-2026"
    d = OUT / slug
    # Kraken 15-minute candles Nov 20 18:00 UTC - Nov 21 13:45 UTC, frozen in chart-data.json as
    # [ts, XBTCAD low, XBTUSD close]. Dollar-market line = XBTUSD close x 1.4325 (Bank of Canada USD/CAD, Nov 20, 2026).
    import datetime as dt
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    boc = 1.4325
    dts = [dt.datetime.fromtimestamp(r[0] - 6 * 3600, dt.UTC) for r in rows]   # U.S. Central (CST) wall clock
    cad = [r[1] for r in rows]
    ref = [r[2] * boc for r in rows]
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Bitcoin on Kraken, Nov. 20-21, 2026: CAD market vs. dollar price (Central time)")
    ax.plot(dts, ref, color="#38bdf8", linewidth=2.0, linestyle="--", label="BTC/USD close x 1.4325 (Bank of Canada rate, Nov. 20)")
    ax.plot(dts, cad, color="#f87171", linewidth=2.4, label="BTC/CAD 15-minute low")
    ax.fill_between(dts, cad, ref, color="#f87171", alpha=0.12)
    i = cad.index(min(cad))
    ax.annotate("C$24,250 at 2 a.m.", (dts[i], cad[i]), xytext=(18, -4), textcoords="offset points",
                color="#fecaca", fontsize=11, fontweight="bold", va="center")
    ax.set_ylim(15000, 95000)
    ax.yaxis.set_major_formatter(lambda x, _p: f"C${x:,.0f}")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d, %-I %p"))
    leg = ax.legend(loc="lower left", facecolor="#0b1630", edgecolor="#1e293b", fontsize=10)
    for t in leg.get_texts():
        t.set_color("#e2e8f0")
    plt.tight_layout(pad=1.2)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-kraken-btc-cad-vs-usd-nov-20-21")
    comp = make_compare_card(
        d / "compare-kraken-cad-lows-vs-normal",
        "Kraken's Canadian-dollar markets, Nov. 21",
        "Lowest trade",
        "Normal value",
        [
            ("Bitcoin", "C$24,250", "≈ C$82,636"),
            ("Ether", "C$796.27", "≈ C$2,325"),
            ("1 U.S. dollar", "C$0.30", "C$1.4325"),
        ],
        footer="Kraken data, 2 a.m. CT; normal = USD price x Bank of Canada rate",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin on Kraken from noon Central time on Nov. 20 to 7:45 a.m. on Nov. 21, 2026: a dashed blue line shows the dollar price converted to Canadian dollars, steady between about C$79,000 and C$85,000, while a red line of 15-minute lows on the Canadian-dollar market falls away from it, reaching C$24,250 at 2 a.m. before jumping back to the blue line around 4 a.m.", {
            "es": "Gráfico de líneas de bitcoin en Kraken desde el mediodía (hora del centro de EE. UU.) del 20 de noviembre hasta las 7:45 del 21 de noviembre de 2026: una línea azul discontinua muestra el precio en dólares convertido a dólares canadienses, estable entre unos 79.000 y 85.000 C$, mientras una línea roja con los mínimos de 15 minutos del mercado en dólares canadienses se separa de ella, llega a 24.250 C$ a las 2:00 y vuelve a la línea azul hacia las 4:00",
            "pt": "Gráfico de linha do bitcoin na Kraken do meio-dia (horário central dos EUA) de 20 de novembro às 7h45 de 21 de novembro de 2026: uma linha azul tracejada mostra o preço em dólar convertido para dólar canadense, estável entre cerca de C$ 79.000 e C$ 85.000, enquanto uma linha vermelha com as mínimas de 15 minutos do mercado em dólar canadense se afasta dela, chega a C$ 24.250 às 2h e volta à linha azul por volta das 4h",
            "fr": "Courbe du bitcoin sur Kraken de midi (heure du Centre des États-Unis) le 20 novembre à 7 h 45 le 21 novembre 2026 : une ligne bleue pointillée montre le cours en dollars converti en dollars canadiens, stable entre environ 79 000 et 85 000 $ CA, tandis qu'une ligne rouge des plus bas sur 15 minutes du marché en dollars canadiens s'en écarte, tombe à 24 250 $ CA à 2 h puis rejoint la ligne bleue vers 4 h",
            "de": "Liniendiagramm von Bitcoin bei Kraken von 12 Uhr mittags (US-Zentralzeit) am 20. November bis 7:45 Uhr am 21. November 2026: Eine gestrichelte blaue Linie zeigt den in kanadische Dollar umgerechneten Dollarkurs, stabil zwischen etwa 79.000 und 85.000 C$, während eine rote Linie der 15-Minuten-Tiefs im Markt gegen kanadische Dollar davon abweicht, um 2 Uhr 24.250 C$ erreicht und gegen 4 Uhr wieder zur blauen Linie springt",
            "ru": "Линейный график биткоина на Kraken с полудня по центральному времени США 20 ноября до 7:45 21 ноября 2026 года: синяя пунктирная линия — долларовая цена в пересчёте на канадские доллары, она держится между примерно C$79 000 и C$85 000; красная линия 15-минутных минимумов рынка в канадских долларах отрывается от неё, в 2:00 доходит до C$24 250 и около 4:00 возвращается к синей линии",
            "tr": "Bitcoin'in Kraken'deki seyrini 20 Kasım ABD Merkez saatiyle öğleden 21 Kasım 2026 saat 07.45'e kadar gösteren çizgi grafiği: kesikli mavi çizgi Kanada dolarına çevrilmiş dolar fiyatını gösteriyor ve yaklaşık 79.000-85.000 C$ arasında sabit kalıyor; Kanada doları piyasasının 15 dakikalık diplerini gösteren kırmızı çizgi ondan ayrılıyor, saat 02.00'de 24.250 C$'a iniyor ve 04.00 civarında mavi çizgiye geri dönüyor",
            "id": "Grafik garis bitcoin di Kraken dari tengah hari waktu Tengah AS pada 20 November hingga pukul 07.45 pada 21 November 2026: garis biru putus-putus menunjukkan harga dolar AS yang dikonversi ke dolar Kanada, stabil di sekitar C$79.000 hingga C$85.000, sedangkan garis merah harga terendah 15 menit di pasar dolar Kanada menjauh darinya, mencapai C$24.250 pukul 02.00, lalu kembali ke garis biru sekitar pukul 04.00",
            "ja": "2026年11月20日正午（米中部時間）から11月21日午前7時45分までのKrakenにおけるビットコインの折れ線グラフ。青い破線はドル価格をカナダドルに換算したもので、約7万9000〜8万5000カナダドルで安定している。赤い線はカナダドル市場の15分足安値で、青い線から離れて午前2時に2万4250カナダドルまで下がり、午前4時ごろ青い線の水準に戻っている",
            "ko": "2026년 11월 20일 정오(미국 중부시간)부터 11월 21일 오전 7시 45분까지 크라켄의 비트코인 선 그래프. 파란 점선은 달러 가격을 캐나다 달러로 환산한 값으로 약 7만9000~8만5000캐나다달러에서 안정적이고, 캐나다 달러 시장의 15분봉 저가를 나타낸 빨간 선은 여기서 떨어져 오전 2시 2만4250캐나다달러까지 내려간 뒤 오전 4시쯤 파란 선 수준으로 돌아온다",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/CAD and BTC/USD 15-minute candles; Bank of Canada USD/CAD rate")},
        {"id": "compare", "file": comp.name, "w": 1200, "h": 630, "kind": "compare",
         "alt": alts("Comparison card of Kraken's Canadian-dollar markets on Nov. 21, 2026: bitcoin's lowest trade was C$24,250 against a normal value of about C$82,636; ether's was C$796.27 against about C$2,325; one U.S. dollar traded as low as C$0.30 against the Bank of Canada rate of C$1.4325", {
            "es": "Tarjeta comparativa de los mercados en dólares canadienses de Kraken el 21 de noviembre de 2026: la operación más baja de bitcoin fue de 24.250 C$ frente a un valor normal de unos 82.636 C$; la de ether, 796,27 C$ frente a unos 2.325 C$; un dólar estadounidense llegó a cotizar a 0,30 C$ frente al tipo del Banco de Canadá de 1,4325 C$",
            "pt": "Cartão comparativo dos mercados em dólar canadense da Kraken em 21 de novembro de 2026: a negociação mais baixa do bitcoin foi de C$ 24.250, contra um valor normal de cerca de C$ 82.636; a do ether, C$ 796,27, contra cerca de C$ 2.325; um dólar americano chegou a ser negociado a C$ 0,30, contra a taxa do Banco do Canadá de C$ 1,4325",
            "fr": "Carte comparative des marchés en dollars canadiens de Kraken le 21 novembre 2026 : la transaction la plus basse du bitcoin s'est faite à 24 250 $ CA pour une valeur normale d'environ 82 636 $ CA ; celle de l'ether à 796,27 $ CA pour environ 2 325 $ CA ; un dollar américain s'est échangé jusqu'à 0,30 $ CA, contre un taux de la Banque du Canada de 1,4325 $ CA",
            "de": "Vergleichskarte der Kraken-Märkte gegen kanadische Dollar am 21. November 2026: Der tiefste Bitcoin-Handel lag bei 24.250 C$ bei einem normalen Wert von etwa 82.636 C$, bei Ether 796,27 C$ gegenüber etwa 2.325 C$; ein US-Dollar wurde bis zu 0,30 C$ gehandelt, der Kurs der Bank of Canada lag bei 1,4325 C$",
            "ru": "Карточка сравнения рынков Kraken в канадских долларах 21 ноября 2026 года: самая низкая сделка по биткоину — C$24 250 при нормальной цене около C$82 636; по эфиру — C$796,27 при примерно C$2 325; один доллар США торговался всего за C$0,30 при курсе Банка Канады C$1,4325",
            "tr": "Kraken'in Kanada doları piyasalarını 21 Kasım 2026 için karşılaştıran kart: bitcoin'de en düşük işlem 24.250 C$ oldu, normal değer yaklaşık 82.636 C$ idi; ether'de 796,27 C$, normal değer yaklaşık 2.325 C$; bir ABD doları 0,30 C$'a kadar el değiştirdi, Kanada Merkez Bankası kuru ise 1,4325 C$ idi",
            "id": "Kartu perbandingan pasar dolar Kanada di Kraken pada 21 November 2026: transaksi bitcoin terendah C$24.250 dibandingkan nilai normal sekitar C$82.636; ether C$796,27 dibandingkan sekitar C$2.325; satu dolar AS sempat diperdagangkan serendah C$0,30, sedangkan kurs Bank of Canada C$1,4325",
            "ja": "2026年11月21日のKrakenのカナダドル建て市場を比べたカード。ビットコインの最安取引は2万4250カナダドルで、通常の価値は約8万2636カナダドル。イーサは796.27カナダドルで、通常は約2325カナダドル。1米ドルは最安0.30カナダドルで取引され、カナダ銀行のレートは1.4325カナダドル",
            "ko": "2026년 11월 21일 크라켄 캐나다 달러 시장을 비교한 카드. 비트코인 최저 거래가는 2만4250캐나다달러로 정상 가치 약 8만2636캐나다달러와 비교되고, 이더는 796.27캐나다달러로 약 2325캐나다달러와 비교된다. 1미국달러는 최저 0.30캐나다달러에 거래됐고 캐나다은행 환율은 1.4325캐나다달러였다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Kraken public market data; Bank of Canada exchange rate, Nov. 20, 2026")},
    ]


def build_death_bets_act():
    slug = "senate-passes-death-bets-act-prediction-markets-nov-2026"
    d = OUT / slug
    # Congress.gov S.4035 actions: introduced Mar 10, 2026; Curtis cosponsor Sep 30, 2026; passed Senate by voice vote Nov 19, 2026.
    tl = make_timeline_card(
        d / "timeline-death-bets-act",
        "S. 4035, the DEATH BETS Act",
        [
            ("Mar. 10", "Sen. Schiff introduces the bill", (96, 165, 250)),
            ("Sep. 30", "Sen. Curtis signs on as cosponsor", (96, 165, 250)),
            ("Nov. 19", "Passes the Senate by voice vote", GREEN),
            ("Next", "House vote, then the president's signature", ORANGE),
        ],
        footer="Congress.gov · U.S. Senate floor log, 2026",
        margin=190, wrap_w=240,
    )
    fact = make_fact_card(
        d / "fact-1-2-million-polymarket-iran-bets",
        "Why insider trading worries lawmakers",
        "$1.2 million",
        "Made by six Polymarket wallets betting on the timing of U.S. strikes on Iran in February 2026, per Bubblemaps.",
        footer="Bubblemaps via CoinDesk, Nov. 20, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "timeline",
         "alt": alts("Timeline of S. 4035, the DEATH BETS Act: introduced by Sen. Schiff on March 10, 2026, Sen. Curtis signed on as cosponsor on Sept. 30, passed the Senate by voice vote on Nov. 19; next it needs a House vote and the president's signature", {
            "es": "Cronología del S. 4035, la ley DEATH BETS: presentada por el senador Schiff el 10 de marzo de 2026, el senador Curtis se sumó como copatrocinador el 30 de septiembre y el Senado la aprobó por votación oral el 19 de noviembre; ahora necesita un voto de la Cámara de Representantes y la firma del presidente",
            "pt": "Linha do tempo do S. 4035, a lei DEATH BETS: apresentada pelo senador Schiff em 10 de março de 2026, o senador Curtis aderiu como coautor em 30 de setembro e o Senado a aprovou por votação simbólica em 19 de novembro; agora precisa de votação na Câmara e da sanção do presidente",
            "fr": "Chronologie du S. 4035, le DEATH BETS Act : déposé par le sénateur Schiff le 10 mars 2026, le sénateur Curtis s'y est associé comme coparrain le 30 septembre, adopté par le Sénat par vote oral le 19 novembre ; il lui faut encore un vote de la Chambre et la signature du président",
            "de": "Zeitleiste zu S. 4035, dem DEATH BETS Act: am 10. März 2026 von Senator Schiff eingebracht, Senator Curtis wurde am 30. September Mitunterstützer, am 19. November per Stimmabstimmung vom Senat verabschiedet; als Nächstes braucht es ein Votum des Repräsentantenhauses und die Unterschrift des Präsidenten",
            "ru": "Хронология законопроекта S. 4035 (DEATH BETS Act): внесен сенатором Шиффом 10 марта 2026 года, сенатор Кертис стал соавтором 30 сентября, Сенат принял его голосованием «с голоса» 19 ноября; дальше нужны голосование в Палате представителей и подпись президента",
            "tr": "S. 4035 DEATH BETS Yasası'nın zaman çizelgesi: Senatör Schiff 10 Mart 2026'da sundu, Senatör Curtis 30 Eylül'de ortak sponsor oldu, Senato 19 Kasım'da sözlü oylamayla kabul etti; sırada Temsilciler Meclisi oylaması ve başkanın imzası var",
            "id": "Linimasa S. 4035, DEATH BETS Act: diajukan Senator Schiff pada 10 Maret 2026, Senator Curtis bergabung sebagai pendukung bersama pada 30 September, disahkan Senat lewat pemungutan suara lisan pada 19 November; berikutnya perlu pemungutan suara DPR dan tanda tangan presiden",
            "ja": "S. 4035（DEATH BETS法案）の年表：2026年3月10日にシフ上院議員が提出、9月30日にカーティス上院議員が共同提案者に加わり、11月19日に上院が発声投票で可決。今後は下院での採決と大統領の署名が必要",
            "ko": "S. 4035(DEATH BETS 법안) 연표: 2026년 3월 10일 시프 상원의원이 발의, 9월 30일 커티스 상원의원이 공동 발의자로 합류, 11월 19일 상원이 구두 표결로 통과. 다음은 하원 표결과 대통령 서명",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Congress.gov, U.S. Senate floor log")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: six Polymarket wallets made about $1.2 million betting on the timing of U.S. strikes on Iran in February 2026, according to Bubblemaps as cited by CoinDesk", {
            "es": "Tarjeta: seis billeteras de Polymarket ganaron unos 1,2 millones de dólares apostando sobre el momento de los ataques de EE. UU. contra Irán en febrero de 2026, según Bubblemaps citado por CoinDesk",
            "pt": "Cartão: seis carteiras da Polymarket ganharam cerca de US$ 1,2 milhão apostando no momento dos ataques dos EUA ao Irã em fevereiro de 2026, segundo a Bubblemaps citada pela CoinDesk",
            "fr": "Carte : six portefeuilles Polymarket ont gagné environ 1,2 million de dollars en pariant sur la date des frappes américaines contre l'Iran en février 2026, selon Bubblemaps cité par CoinDesk",
            "de": "Faktenkarte: Sechs Polymarket-Wallets verdienten rund 1,2 Mio. $ mit Wetten auf den Zeitpunkt der US-Angriffe auf Iran im Februar 2026, laut Bubblemaps, zitiert von CoinDesk",
            "ru": "Карточка: шесть кошельков на Polymarket заработали около $1,2 млн на ставках о сроках ударов США по Ирану в феврале 2026 года, по данным Bubblemaps, которые приводит CoinDesk",
            "tr": "Kart: CoinDesk'in aktardığı Bubblemaps verilerine göre altı Polymarket cüzdanı, Şubat 2026'da ABD'nin İran'a yönelik saldırılarının zamanlamasına bahis oynayarak yaklaşık 1,2 milyon $ kazandı",
            "id": "Kartu: enam dompet Polymarket meraup sekitar US$1,2 juta dari taruhan soal waktu serangan AS ke Iran pada Februari 2026, menurut Bubblemaps yang dikutip CoinDesk",
            "ja": "カード：CoinDeskが引用したBubblemapsによると、Polymarketの6つのウォレットが2026年2月の米国によるイラン攻撃のタイミングに賭けて約120万ドルの利益を得た",
            "ko": "카드: 코인데스크가 인용한 버블맵스에 따르면 폴리마켓 지갑 6개가 2026년 2월 미국의 이란 공습 시점에 베팅해 약 120만 달러를 벌었다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bubblemaps via CoinDesk")},
    ]



def build_abraxas_withdrawals():
    slug = "bitcoin-61500-abraxas-capital-1-billion-btc-off-exchanges-nov-2026"
    d = OUT / slug
    # Kraken XBTUSD 15-minute candles, Nov 21 06:00 UTC to Nov 22 18:45 UTC (Sat 12 a.m. to Sun 12:45 p.m. CST), closes plotted.
    # Frozen in i18n/content/<slug>/chart-data.json as [ts, close, low, high].
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    xs = np.array([r[0] - 6 * 3600 for r in rows], dtype=float)   # U.S. Central (CST, UTC-6) on the axis
    ys = np.array([r[1] for r in rows])
    chart = make_line_chart(
        d / "chart-btc-15min-nov-21-22",
        xs, ys,
        title="Bitcoin on Nov. 21-22, 2026: 15-minute closes on Kraken (U.S. Central time)",
        hline=59206.0,
        hlabel="Average price of the Abraxas-linked withdrawals: $59,206 (Lookonchain)",
        date_fmt="%a %-I %p",
    )
    fact = make_fact_card(
        d / "fact-17597-btc-withdrawn",
        "Pulled off Binance and Kraken",
        "17,597 BTC",
        "About $1.04 billion at an average price of $59,206, sent to wallets Arkham labels Abraxas Capital",
        footer="Source: Lookonchain (Arkham labels), Nov. 22, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's 15-minute closing prices on Kraken from midnight Central time on Saturday, Nov. 21, to 12:45 p.m. on Sunday, Nov. 22, 2026: the price starts near $55,600, just after Saturday's low of $55,100, climbs above $60,000 by Saturday morning, dips back below $59,000 late Saturday night, then rises above $61,000 on Sunday morning and holds near $60,700. A dashed line marks $59,206, the average price of the Abraxas-linked withdrawals", {
            "es": "Gráfico de líneas de los precios de cierre de 15 minutos de bitcoin en Kraken desde la medianoche (hora del centro de EE. UU.) del sábado 21 de noviembre hasta las 12:45 del domingo 22 de noviembre de 2026: el precio parte de unos 55.600 dólares, justo después del mínimo del sábado de 55.100, supera los 60.000 el sábado por la mañana, vuelve por debajo de 59.000 el sábado por la noche y sube por encima de 61.000 el domingo por la mañana para mantenerse cerca de 60.700. Una línea discontinua marca 59.206 dólares, el precio medio de los retiros vinculados a Abraxas",
            "pt": "Gráfico de linha dos preços de fechamento de 15 minutos do bitcoin na Kraken da meia-noite (horário central dos EUA) de sábado, 21 de novembro, às 12h45 de domingo, 22 de novembro de 2026: o preço começa perto de US$ 55.600, logo após a mínima de sábado, de US$ 55.100, passa de US$ 60.000 na manhã de sábado, volta para baixo de US$ 59.000 no fim da noite de sábado e sobe acima de US$ 61.000 na manhã de domingo, ficando perto de US$ 60.700. Uma linha tracejada marca US$ 59.206, o preço médio dos saques ligados à Abraxas",
            "fr": "Courbe des cours de clôture sur 15 minutes du bitcoin sur Kraken, de minuit (heure du Centre des États-Unis) le samedi 21 novembre à 12 h 45 le dimanche 22 novembre 2026 : le cours part d'environ 55 600 dollars, juste après le plus bas de samedi à 55 100 dollars, repasse au-dessus de 60 000 dollars samedi matin, redescend sous 59 000 dollars tard samedi soir, puis dépasse 61 000 dollars dimanche matin et se maintient près de 60 700 dollars. Une ligne pointillée marque 59 206 dollars, le prix moyen des retraits liés à Abraxas",
            "de": "Liniendiagramm der 15-Minuten-Schlusskurse von Bitcoin bei Kraken von Mitternacht (US-Zentralzeit) am Samstag, 21. November, bis 12:45 Uhr am Sonntag, 22. November 2026: Der Kurs beginnt bei rund 55.600 $, kurz nach dem Samstagstief von 55.100 $, steigt bis Samstagmorgen über 60.000 $, rutscht spät am Samstagabend wieder unter 59.000 $ und klettert am Sonntagmorgen über 61.000 $, bevor er sich bei etwa 60.700 $ hält. Eine gestrichelte Linie markiert 59.206 $, den Durchschnittspreis der Abraxas zugeordneten Abhebungen",
            "ru": "Линейный график 15-минутных цен закрытия биткоина на Kraken с полуночи по центральному времени США в субботу, 21 ноября, до 12:45 в воскресенье, 22 ноября 2026 года: цена начинается около $55 600, сразу после субботнего минимума $55 100, к утру субботы поднимается выше $60 000, поздно вечером в субботу снова опускается ниже $59 000, а в воскресенье утром поднимается выше $61 000 и держится около $60 700. Пунктирная линия отмечает $59 206 — среднюю цену выводов, связанных с Abraxas",
            "tr": "21 Kasım cumartesi gece yarısından (ABD Merkezi saati) 22 Kasım 2026 pazar 12.45'e kadar Kraken'de bitcoinin 15 dakikalık kapanış fiyatlarının çizgi grafiği: fiyat cumartesi günü görülen 55.100 $'lık dip seviyenin hemen ardından yaklaşık 55.600 $'dan başlıyor, cumartesi sabahı 60.000 $'ın üzerine çıkıyor, cumartesi gecesi geç saatlerde yeniden 59.000 $'ın altına iniyor, pazar sabahı 61.000 $'ın üzerine yükseliyor ve 60.700 $ civarında tutunuyor. Kesikli çizgi, Abraxas ile ilişkilendirilen çekimlerin ortalama fiyatı olan 59.206 $'ı gösteriyor",
            "id": "Grafik garis harga penutupan 15 menit bitcoin di Kraken dari tengah malam waktu Central AS pada Sabtu, 21 November, hingga pukul 12.45 pada Minggu, 22 November 2026: harga dimulai di sekitar US$55.600, tepat setelah titik terendah Sabtu di US$55.100, naik di atas US$60.000 pada Sabtu pagi, kembali di bawah US$59.000 pada Sabtu larut malam, lalu naik di atas US$61.000 pada Minggu pagi dan bertahan di dekat US$60.700. Garis putus-putus menandai US$59.206, harga rata-rata penarikan yang dikaitkan dengan Abraxas",
            "ja": "2026年11月21日（土）午前0時（米中部時間）から22日（日）午後0時45分までのKrakenにおけるビットコインの15分足終値の折れ線グラフ：土曜の安値5万5100ドル直後の約5万5600ドルから始まり、土曜朝に6万ドルを回復、土曜深夜に再び5万9000ドルを割り込んだ後、日曜朝に6万1000ドルを上回り、約6万700ドル近辺で推移。破線はAbraxasに関連付けられた引き出しの平均価格5万9206ドルを示す",
            "ko": "2026년 11월 21일(토) 자정(미국 중부시간)부터 22일(일) 오후 12시 45분까지 크라켄 비트코인 15분 종가 선 그래프: 토요일 저점 5만5,100달러 직후인 약 5만5,600달러에서 시작해 토요일 아침 6만 달러를 넘었다가 토요일 밤늦게 다시 5만9,000달러 아래로 내려간 뒤, 일요일 아침 6만1,000달러를 넘어 약 6만700달러 부근을 유지. 점선은 아브락사스와 연결된 출금의 평균 가격인 5만9,206달러를 표시",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD (15-minute candles); Lookonchain (average withdrawal price)")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: 17,597 BTC pulled off Binance and Kraken, about $1.04 billion at an average price of $59,206, sent to wallets Arkham labels Abraxas Capital. Source: Lookonchain, Nov. 22, 2026", {
            "es": "Tarjeta de datos: 17.597 BTC retirados de Binance y Kraken, unos 1.040 millones de dólares a un precio medio de 59.206 dólares, enviados a carteras que Arkham atribuye a Abraxas Capital. Fuente: Lookonchain, 22 de noviembre de 2026",
            "pt": "Cartão de dados: 17.597 BTC retirados da Binance e da Kraken, cerca de US$ 1,04 bilhão a um preço médio de US$ 59.206, enviados a carteiras que a Arkham atribui à Abraxas Capital. Fonte: Lookonchain, 22 de novembro de 2026",
            "fr": "Fiche chiffrée : 17 597 BTC retirés de Binance et de Kraken, soit environ 1,04 milliard de dollars à un prix moyen de 59 206 dollars, envoyés vers des portefeuilles qu'Arkham attribue à Abraxas Capital. Source : Lookonchain, 22 novembre 2026",
            "de": "Faktenkarte: 17.597 BTC von Binance und Kraken abgezogen, rund 1,04 Mrd. $ zu einem Durchschnittspreis von 59.206 $, an Wallets, die Arkham Abraxas Capital zuordnet. Quelle: Lookonchain, 22. November 2026",
            "ru": "Карточка с фактом: 17 597 BTC выведены с Binance и Kraken — около $1,04 млрд по средней цене $59 206 — на кошельки, которые Arkham относит к Abraxas Capital. Источник: Lookonchain, 22 ноября 2026 года",
            "tr": "Bilgi kartı: Binance ve Kraken'den 17.597 BTC çekildi; ortalama 59.206 $ fiyatla yaklaşık 1,04 milyar $ değerindeki bu bitcoinler, Arkham'ın Abraxas Capital'e ait olarak etiketlediği cüzdanlara gönderildi. Kaynak: Lookonchain, 22 Kasım 2026",
            "id": "Kartu fakta: 17.597 BTC ditarik dari Binance dan Kraken, sekitar US$1,04 miliar dengan harga rata-rata US$59.206, dikirim ke dompet yang diberi label Abraxas Capital oleh Arkham. Sumber: Lookonchain, 22 November 2026",
            "ja": "ファクトカード：BinanceとKrakenから1万7597 BTCが引き出され、平均価格5万9206ドルで約10.4億ドル相当。ArkhamがAbraxas Capitalのものとラベル付けしたウォレットへ送られた。出典：Lookonchain、2026年11月22日",
            "ko": "팩트 카드: 바이낸스와 크라켄에서 1만7,597 BTC 출금, 평균 가격 5만9,206달러 기준 약 10억4,000만 달러 규모로, 아캄이 아브락사스 캐피털로 표시한 지갑으로 이동. 출처: 룩온체인, 2026년 11월 22일",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Lookonchain, citing Arkham Intelligence wallet labels")},
    ]


def build_chainflip_bounty():
    slug = "chainflip-loss-12-million-bitcoin-10-percent-bounty-nov-2026"
    d = OUT / slug
    # Amounts from Chainflip Labs (chainflip.io/return). USD values at Kraken 1-hour open prices for the
    # 07:00 UTC candle on Nov 21, 2026 (1 a.m. Central): XBTUSD 57,965.5, ETHUSD 1,637.68; stablecoins at $1.
    btc_usd = 122.86137042 * 57965.5 / 1e6     # 7.122
    eth_usd = 520.2243399 * 1637.68 / 1e6      # 0.852
    chart = make_bar_chart(
        d / "chart-chainflip-loss-by-asset",
        ["122.86 BTC\n(Bitcoin vault)", "520.22 ETH\n(Ethereum vault)", "3.25M USDC\n(Ethereum vault)", "758,141 USDT\n(Ethereum vault)"],
        [btc_usd, eth_usd, 3.24963141, 0.75814133],
        "What Chainflip says was taken on Nov. 21, in U.S. dollars (total about $12.0M)",
        colors=["#f7931a", "#818cf8", "#38bdf8", "#34d399"],
        value_fmt=lambda v: f"${v:,.2f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    tl = make_timeline_card(
        d / "timeline-chainflip-bounty",
        "Chainflip theft and bounty offer (U.S. Central time)",
        [
            ("Sat 1:01 a.m.", "122.86 BTC leaves the Bitcoin side in one transaction", (248, 113, 113)),
            ("Sat 1:10 a.m.", "520 ETH, 3.25M USDC and 758,141 USDT leave the Ethereum vault", (248, 113, 113)),
            ("Sat 1:22 p.m.", "Chainflip offers: keep 10%, return 90%", ORANGE),
            ("Mon 12:38 p.m.", "Deadline (18:38 UTC, Nov. 23) to return 110.58 BTC and 2,618.1 ETH", (96, 165, 250)),
        ],
        footer="Bitcoin blocks 976,865, 976,943 · Ethereum 26,461,896 · Chainflip",
        margin=170, wrap_w=250,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of what Chainflip says was taken on Nov. 21, 2026, valued at Kraken prices at 1 a.m. Central time: 122.86 BTC worth about $7.12 million, 520.22 ETH worth about $0.85 million, 3.25 million USDC and 758,141 USDT, about $12.0 million in total", {
            "es": "Gráfico de barras de lo que Chainflip dice que se llevaron el 21 de noviembre de 2026, valorado a precios de Kraken a la 1 a. m. hora del centro de EE. UU.: 122,86 BTC por unos 7,12 millones de dólares, 520,22 ETH por unos 0,85 millones, 3,25 millones de USDC y 758.141 USDT, en total unos 12,0 millones de dólares",
            "pt": "Gráfico de barras do que a Chainflip diz ter sido levado em 21 de novembro de 2026, avaliado a preços da Kraken à 1h, horário central dos EUA: 122,86 BTC, cerca de US$ 7,12 milhões; 520,22 ETH, cerca de US$ 0,85 milhão; 3,25 milhões de USDC e 758.141 USDT, cerca de US$ 12,0 milhões no total",
            "fr": "Diagramme en barres de ce que Chainflip dit avoir perdu le 21 novembre 2026, valorisé aux cours de Kraken à 1 h, heure du Centre des États-Unis : 122,86 BTC pour environ 7,12 millions de dollars, 520,22 ETH pour environ 0,85 million, 3,25 millions d'USDC et 758 141 USDT, soit environ 12,0 millions de dollars au total",
            "de": "Balkendiagramm dessen, was laut Chainflip am 21. November 2026 entwendet wurde, bewertet zu Kraken-Kursen um 1 Uhr US-Central-Zeit: 122,86 BTC im Wert von rund 7,12 Mio. $, 520,22 ETH im Wert von rund 0,85 Mio. $, 3,25 Mio. USDC und 758.141 USDT, insgesamt rund 12,0 Mio. $",
            "ru": "Столбчатая диаграмма того, что, по словам Chainflip, было похищено 21 ноября 2026 года, по ценам Kraken на 1:00 по центральному времени США: 122,86 BTC примерно на $7,12 млн, 520,22 ETH примерно на $0,85 млн, 3,25 млн USDC и 758 141 USDT, всего около $12,0 млн",
            "tr": "Chainflip'in 21 Kasım 2026'da alındığını söylediği varlıkların, ABD Merkezi saatiyle 01.00'deki Kraken fiyatlarıyla sütun grafiği: yaklaşık 7,12 milyon $ değerinde 122,86 BTC, yaklaşık 0,85 milyon $ değerinde 520,22 ETH, 3,25 milyon USDC ve 758.141 USDT, toplam yaklaşık 12,0 milyon $",
            "id": "Diagram batang aset yang menurut Chainflip diambil pada 21 November 2026, dinilai dengan harga Kraken pukul 01.00 waktu Central AS: 122,86 BTC senilai sekitar US$7,12 juta, 520,22 ETH senilai sekitar US$0,85 juta, 3,25 juta USDC, dan 758.141 USDT, total sekitar US$12,0 juta",
            "ja": "2026年11月21日にChainflipが奪われたとする資産の棒グラフ（米中部時間午前1時のKraken価格で評価）：122.86 BTC（約712万ドル）、520.22 ETH（約85万ドル）、325万USDC、75万8141 USDT、合計約1200万ドル",
            "ko": "체인플립이 2026년 11월 21일 탈취당했다고 밝힌 자산의 막대 그래프(미국 중부시간 오전 1시 크라켄 가격 기준): 122.86 BTC 약 712만 달러, 520.22 ETH 약 85만 달러, 325만 USDC, 75만 8,141 USDT, 합계 약 1,200만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Chainflip Labs (amounts); Kraken BTC/USD and ETH/USD prices, 07:00 UTC Nov. 21, 2026")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline in U.S. Central time: Saturday 1:01 a.m., 122.86 BTC leaves the Bitcoin side of Chainflip in one transaction; 1:10 a.m., 520 ETH, 3.25 million USDC and 758,141 USDT leave the Ethereum vault; 1:22 p.m., Chainflip offers to let the attacker keep 10% if 90% is returned; Monday 12:38 p.m. (18:38 UTC, Nov. 23), deadline to return 110.58 BTC and 2,618.1 ETH", {
            "es": "Cronología en hora del centro de EE. UU.: sábado 1:01 a. m., 122,86 BTC salen del lado de Bitcoin de Chainflip en una sola transacción; 1:10 a. m., 520 ETH, 3,25 millones de USDC y 758.141 USDT salen de la bóveda de Ethereum; 1:22 p. m., Chainflip ofrece al atacante quedarse con el 10 % si devuelve el 90 %; lunes 12:38 p. m. (18:38 UTC, 23 de noviembre), plazo para devolver 110,58 BTC y 2.618,1 ETH",
            "pt": "Linha do tempo no horário central dos EUA: sábado 1h01, 122,86 BTC saem do lado Bitcoin da Chainflip em uma única transação; 1h10, 520 ETH, 3,25 milhões de USDC e 758.141 USDT saem do cofre de Ethereum; 13h22, a Chainflip oferece ao invasor ficar com 10% se devolver 90%; segunda 12h38 (18h38 UTC, 23 de novembro), prazo para devolver 110,58 BTC e 2.618,1 ETH",
            "fr": "Chronologie en heure du Centre des États-Unis : samedi 1 h 01, 122,86 BTC quittent le côté Bitcoin de Chainflip en une seule transaction ; 1 h 10, 520 ETH, 3,25 millions d'USDC et 758 141 USDT quittent le coffre Ethereum ; 13 h 22, Chainflip propose à l'attaquant de garder 10 % s'il rend 90 % ; lundi 12 h 38 (18 h 38 UTC, 23 novembre), date limite pour rendre 110,58 BTC et 2 618,1 ETH",
            "de": "Zeitleiste in US-Central-Zeit: Samstag 1:01 Uhr, 122,86 BTC verlassen die Bitcoin-Seite von Chainflip in einer einzigen Transaktion; 1:10 Uhr, 520 ETH, 3,25 Mio. USDC und 758.141 USDT verlassen den Ethereum-Tresor; 13:22 Uhr, Chainflip bietet dem Angreifer an, 10 % zu behalten, wenn er 90 % zurückgibt; Montag 12:38 Uhr (18:38 UTC, 23. November), Frist für die Rückgabe von 110,58 BTC und 2.618,1 ETH",
            "ru": "Хронология по центральному времени США: суббота, 1:01 — 122,86 BTC уходят с биткоин-стороны Chainflip одной транзакцией; 1:10 — 520 ETH, 3,25 млн USDC и 758 141 USDT уходят из хранилища в Ethereum; 13:22 — Chainflip предлагает атакующему оставить себе 10%, если он вернёт 90%; понедельник, 12:38 (18:38 UTC, 23 ноября) — срок вернуть 110,58 BTC и 2618,1 ETH",
            "tr": "ABD Merkezi saatiyle zaman çizelgesi: cumartesi 01.01'de 122,86 BTC tek bir işlemle Chainflip'in Bitcoin tarafından çıkıyor; 01.10'da 520 ETH, 3,25 milyon USDC ve 758.141 USDT Ethereum kasasından çıkıyor; 13.22'de Chainflip saldırgana %90'ı iade ederse %10'u tutmayı teklif ediyor; pazartesi 12.38 (18.38 UTC, 23 Kasım), 110,58 BTC ve 2.618,1 ETH iadesi için son tarih",
            "id": "Linimasa waktu Central AS: Sabtu 01.01, 122,86 BTC keluar dari sisi Bitcoin Chainflip dalam satu transaksi; 01.10, 520 ETH, 3,25 juta USDC, dan 758.141 USDT keluar dari brankas Ethereum; 13.22, Chainflip menawarkan penyerang menyimpan 10% jika 90% dikembalikan; Senin 12.38 (18.38 UTC, 23 November), batas waktu mengembalikan 110,58 BTC dan 2.618,1 ETH",
            "ja": "時系列（米中部時間）：土曜午前1時01分、1件の取引で122.86 BTCがChainflipのビットコイン側から流出。午前1時10分、520 ETH、325万USDC、75万8141 USDTがイーサリアム金庫から流出。午後1時22分、Chainflipが90％を返せば10％を保持してよいと提案。月曜午後0時38分（11月23日18時38分UTC）、110.58 BTCと2618.1 ETHの返還期限",
            "ko": "타임라인(미국 중부시간): 토요일 오전 1시 1분, 거래 한 건으로 122.86 BTC가 체인플립 비트코인 쪽에서 유출, 오전 1시 10분, 520 ETH와 325만 USDC, 75만 8,141 USDT가 이더리움 금고에서 유출, 오후 1시 22분, 체인플립이 90%를 돌려주면 10%를 가져도 된다고 제안, 월요일 오후 12시 38분(11월 23일 18:38 UTC), 110.58 BTC와 2,618.1 ETH 반환 기한",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bitcoin and Ethereum blockchain data (mempool.space, Blockscout); Chainflip Labs; Chainflip on X")},
    ]


def build_core_node_stall():
    slug = "bitcoin-core-node-stall-bug-ai-found-fix-nov-2026"
    d = OUT / slug
    data = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    labels = [g[0] for g in data["groups"]]
    values = [g[1] for g in data["groups"]]
    chart = make_bar_chart(
        d / "chart-reachable-nodes-by-version",
        labels, values,
        "Reachable bitcoin nodes by Bitcoin Core version, Nov. 22, 2026 (21,840 nodes)",
        colors=["#34d399", "#f87171", "#b91c1c", "#64748b", "#475569"],
        value_fmt=lambda v: f"{v:,.0f}",
        axis_fmt=lambda x, _p: f"{x:,.0f}",
    )
    tl = make_timeline_card(
        d / "timeline-cve-2026-117348",
        "Bitcoin Core node-stall bug: from AI scan to public fix",
        [
            ("Jul 8", "AI scan (Project Loupe at Spiral) reports the bug", (96, 165, 250)),
            ("Aug 4-6", "Second researcher reports it; fix written and merged", ORANGE),
            ("Oct 27", "Bitcoin Core 32.1 ships with the fix", GREEN),
            ("Nov 20", "30.5 and 31.3 released; bug made public", (248, 113, 113)),
        ],
        footer="Source: Bitcoin Core advisory CVE-2026-117348 (bitcoincore.org)",
        margin=170, wrap_w=250,
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of 21,840 reachable bitcoin nodes on Nov. 22, 2026, by Bitcoin Core version: 7,153 on a fixed version (32.x, 31.3 or 30.5), 6,138 on affected 30.x or 31.x versions with a fix available, 2,636 on affected 29.x with no fix, 2,872 on versions older than 29.0, and 3,041 running other or custom software", {
            "es": "Gráfico de barras de 21.840 nodos de bitcoin accesibles el 22 de noviembre de 2026, por versión de Bitcoin Core: 7.153 con una versión corregida (32.x, 31.3 o 30.5), 6.138 con versiones 30.x o 31.x afectadas que ya tienen parche, 2.636 con la 29.x afectada y sin parche, 2.872 con versiones anteriores a la 29.0 y 3.041 con otro software o compilaciones propias",
            "pt": "Gráfico de barras de 21.840 nós de bitcoin acessíveis em 22 de novembro de 2026, por versão do Bitcoin Core: 7.153 em versão corrigida (32.x, 31.3 ou 30.5), 6.138 em versões 30.x ou 31.x afetadas com correção disponível, 2.636 na 29.x afetada sem correção, 2.872 em versões anteriores à 29.0 e 3.041 com outro software ou versões próprias",
            "fr": "Diagramme en barres de 21 840 nœuds bitcoin joignables le 22 novembre 2026, par version de Bitcoin Core : 7 153 sur une version corrigée (32.x, 31.3 ou 30.5), 6 138 sur des versions 30.x ou 31.x touchées pour lesquelles un correctif existe, 2 636 sur la 29.x touchée et sans correctif, 2 872 sur des versions antérieures à la 29.0 et 3 041 sur d'autres logiciels ou des versions personnalisées",
            "de": "Balkendiagramm von 21.840 erreichbaren Bitcoin-Nodes am 22. November 2026 nach Bitcoin-Core-Version: 7.153 mit einer behobenen Version (32.x, 31.3 oder 30.5), 6.138 mit betroffenen Versionen 30.x oder 31.x, für die es ein Update gibt, 2.636 mit der betroffenen 29.x ohne Update, 2.872 mit Versionen älter als 29.0 und 3.041 mit anderer oder angepasster Software",
            "ru": "Столбчатая диаграмма 21 840 доступных узлов биткоина на 22 ноября 2026 года по версиям Bitcoin Core: 7153 на исправленной версии (32.x, 31.3 или 30.5), 6138 на уязвимых версиях 30.x или 31.x, для которых есть исправление, 2636 на уязвимой 29.x без исправления, 2872 на версиях старше 29.0 и 3041 на другом или собственном ПО",
            "tr": "22 Kasım 2026'da erişilebilir 21.840 bitcoin düğümünün Bitcoin Core sürümüne göre sütun grafiği: 7.153 düzeltilmiş sürümde (32.x, 31.3 veya 30.5), 6.138 düzeltmesi çıkmış etkilenen 30.x veya 31.x sürümlerinde, 2.636 düzeltme almayacak etkilenen 29.x'te, 2.872 29.0'dan eski sürümlerde ve 3.041 başka ya da özel yazılımda",
            "id": "Diagram batang 21.840 node bitcoin yang dapat dijangkau pada 22 November 2026 menurut versi Bitcoin Core: 7.153 memakai versi yang sudah diperbaiki (32.x, 31.3, atau 30.5), 6.138 memakai versi 30.x atau 31.x yang terdampak dan sudah ada perbaikannya, 2.636 memakai 29.x yang terdampak tanpa perbaikan, 2.872 memakai versi lebih lama dari 29.0, dan 3.041 memakai perangkat lunak lain atau buatan sendiri",
            "ja": "2026年11月22日時点で到達可能なビットコインノード2万1840台のBitcoin Coreバージョン別棒グラフ：修正版（32.x、31.3、30.5）が7153台、修正版が出ている影響対象の30.x・31.xが6138台、修正のない影響対象29.xが2636台、29.0より古い版が2872台、その他・独自ソフトが3041台",
            "ko": "2026년 11월 22일 접속 가능한 비트코인 노드 2만 1,840개의 비트코인 코어 버전별 막대 그래프: 수정된 버전(32.x, 31.3, 30.5) 7,153개, 패치가 나온 영향받는 30.x·31.x 6,138개, 패치가 없는 영향받는 29.x 2,636개, 29.0보다 오래된 버전 2,872개, 기타 또는 자체 소프트웨어 3,041개",
         }),
         "caption": tr_map(CAPTION_CHART, src="BTC Nodes (btcnodes.io) reachable-node snapshot, 13:24 UTC Nov. 22, 2026; version groups per the Bitcoin Core advisory")},
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline of the Bitcoin Core node-stall bug CVE-2026-117348: July 8, an AI scan by Project Loupe at Spiral reports it; Aug. 4 to 6, a second researcher reports it and a fix is written and merged; Oct. 27, Bitcoin Core 32.1 ships with the fix; Nov. 20, versions 30.5 and 31.3 are released and the bug is made public", {
            "es": "Cronología del fallo de Bitcoin Core CVE-2026-117348 que podía paralizar nodos: 8 de julio, un escaneo con IA de Project Loupe en Spiral lo reporta; del 4 al 6 de agosto, un segundo investigador lo reporta y se escribe e integra el arreglo; 27 de octubre, sale Bitcoin Core 32.1 con el arreglo; 20 de noviembre, se publican las versiones 30.5 y 31.3 y el fallo se hace público",
            "pt": "Linha do tempo da falha CVE-2026-117348 do Bitcoin Core que podia travar nós: 8 de julho, uma varredura com IA do Project Loupe, na Spiral, a reporta; de 4 a 6 de agosto, um segundo pesquisador a reporta e a correção é escrita e incorporada; 27 de outubro, o Bitcoin Core 32.1 sai com a correção; 20 de novembro, as versões 30.5 e 31.3 são lançadas e a falha se torna pública",
            "fr": "Chronologie de la faille CVE-2026-117348 de Bitcoin Core qui pouvait bloquer des nœuds : 8 juillet, une analyse par IA de Project Loupe chez Spiral la signale ; du 4 au 6 août, un second chercheur la signale et un correctif est écrit puis intégré ; 27 octobre, Bitcoin Core 32.1 sort avec le correctif ; 20 novembre, les versions 30.5 et 31.3 sortent et la faille est rendue publique",
            "de": "Zeitleiste des Bitcoin-Core-Fehlers CVE-2026-117348, der Nodes ausbremsen konnte: 8. Juli, ein KI-Scan von Project Loupe bei Spiral meldet ihn; 4. bis 6. August, ein zweiter Forscher meldet ihn, ein Fix wird geschrieben und übernommen; 27. Oktober, Bitcoin Core 32.1 erscheint mit dem Fix; 20. November, die Versionen 30.5 und 31.3 erscheinen und der Fehler wird öffentlich gemacht",
            "ru": "Хронология ошибки Bitcoin Core CVE-2026-117348, из-за которой узлы могли зависать: 8 июля — ИИ-сканер Project Loupe в Spiral сообщает о ней; 4–6 августа — о ней сообщает второй исследователь, исправление написано и принято; 27 октября — выходит Bitcoin Core 32.1 с исправлением; 20 ноября — выходят версии 30.5 и 31.3, ошибка раскрыта публично",
            "tr": "Düğümleri durdurabilen Bitcoin Core hatası CVE-2026-117348'in zaman çizelgesi: 8 Temmuz'da Spiral'deki Project Loupe'un yapay zekâ taraması hatayı bildiriyor; 4-6 Ağustos'ta ikinci bir araştırmacı bildiriyor, düzeltme yazılıp birleştiriliyor; 27 Ekim'de düzeltmeyi içeren Bitcoin Core 32.1 çıkıyor; 20 Kasım'da 30.5 ve 31.3 sürümleri yayımlanıyor ve hata kamuoyuna açıklanıyor",
            "id": "Linimasa celah Bitcoin Core CVE-2026-117348 yang bisa membuat node macet: 8 Juli, pemindaian AI Project Loupe di Spiral melaporkannya; 4 sampai 6 Agustus, peneliti kedua melaporkannya dan perbaikan ditulis lalu digabungkan; 27 Oktober, Bitcoin Core 32.1 rilis dengan perbaikan; 20 November, versi 30.5 dan 31.3 dirilis dan celah diumumkan ke publik",
            "ja": "ノードを停止させ得るBitcoin Coreの不具合CVE-2026-117348の時系列：7月8日、SpiralのProject LoupeによるAIスキャンが報告。8月4〜6日、別の研究者も報告し、修正が作成・統合。10月27日、修正入りのBitcoin Core 32.1公開。11月20日、30.5と31.3を公開し不具合を公表",
            "ko": "노드를 멈추게 할 수 있던 비트코인 코어 버그 CVE-2026-117348 타임라인: 7월 8일 스파이럴의 프로젝트 루프 AI 스캔이 보고, 8월 4~6일 두 번째 연구자가 보고하고 수정이 작성·병합, 10월 27일 수정이 포함된 비트코인 코어 32.1 출시, 11월 20일 30.5와 31.3 출시 및 버그 공개",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Bitcoin Core security advisory CVE-2026-117348, Nov. 20, 2026")},
    ]


def build_fusionist_ace():
    slug = "fusionist-ace-bridge-exploit-10-quintillion-tokens-nov-2026"
    d = OUT / slug
    # CoinGecko ACE ("endurance") hourly prices Nov 21 01:00 UTC - Nov 23 00:00 UTC, frozen in chart-data.json:
    # about $0.086 at 17:00 UTC Nov 22 (before the first mint at 17:55 UTC), $0.0664 at 23:00 UTC, $0.0761 at 00:00 UTC Nov 23.
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    chart = make_line_chart(
        d / "chart-ace-hourly-nov-21-22",
        [r[0] for r in rows], [r[1] for r in rows],
        title="Fusionist (ACE) hourly price, Nov. 21-22, 2026 (CoinGecko, UTC)",
        hline=0.0862,
        hlabel="Before the exploit ≈ $0.086",
        date_fmt="%b %d %H:%M",
        yfmt=lambda x, _p: f"${x:.3f}",
    )
    fact = make_fact_card(
        d / "fact-ace-supply-10-quintillion",
        "ACE supply on BNB Chain · Nov. 22, 2026",
        "≈10,020,000,000,000,000,000",
        "ACE tokens after Sunday's unbacked mints, up from about 53.7 million. ACE's maximum supply is 147 million.",
        footer="BNB Chain ACE contract (BscScan) · The Block · Blockaid",
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the ACE token's supply on BNB Chain reached about 10,020,000,000,000,000,000 (about 10 quintillion) after unbacked mints on Nov. 22, 2026, up from about 53.7 million; ACE's maximum supply is 147 million", {
            "es": "Tarjeta de datos: el suministro del token ACE en BNB Chain llegó a unos 10.020.000.000.000.000.000 (unos 10 trillones) tras las emisiones sin respaldo del 22 de noviembre de 2026, frente a unos 53,7 millones antes; el suministro máximo de ACE es de 147 millones",
            "pt": "Cartão de dados: a oferta do token ACE na BNB Chain chegou a cerca de 10.020.000.000.000.000.000 (cerca de 10 quintilhões) após as emissões sem lastro de 22 de novembro de 2026, ante cerca de 53,7 milhões antes; a oferta máxima de ACE é de 147 milhões",
            "fr": "Fiche chiffrée : l'offre du jeton ACE sur BNB Chain a atteint environ 10 020 000 000 000 000 000 (environ 10 trillions) après les émissions sans contrepartie du 22 novembre 2026, contre environ 53,7 millions avant ; l'offre maximale d'ACE est de 147 millions",
            "de": "Faktenkarte: Das Angebot des ACE-Tokens auf der BNB Chain stieg nach ungedeckten Prägungen am 22. November 2026 auf rund 10.020.000.000.000.000.000 (rund 10 Trillionen), zuvor waren es rund 53,7 Millionen; das Höchstangebot von ACE liegt bei 147 Millionen",
            "ru": "Карточка с фактом: после необеспеченного выпуска 22 ноября 2026 года предложение токена ACE в BNB Chain достигло примерно 10 020 000 000 000 000 000 (около 10 квинтиллионов), тогда как раньше было около 53,7 млн; максимальное предложение ACE — 147 млн",
            "tr": "Bilgi kartı: ACE tokeninin BNB Chain'deki arzı, 22 Kasım 2026'daki karşılıksız basımların ardından yaklaşık 10.020.000.000.000.000.000'e (yaklaşık 10 kentilyon) çıktı; önceki arz yaklaşık 53,7 milyondu; ACE'nin azami arzı 147 milyon",
            "id": "Kartu fakta: pasokan token ACE di BNB Chain mencapai sekitar 10.020.000.000.000.000.000 (sekitar 10 kuintiliun) setelah pencetakan tanpa jaminan pada 22 November 2026, naik dari sekitar 53,7 juta; pasokan maksimum ACE adalah 147 juta",
            "ja": "ファクトカード：2026年11月22日の裏付けのない発行により、BNBチェーン上のACEトークンの供給量は約5370万枚から約1000京枚（10,020,000,000,000,000,000枚）に急増。ACEの最大供給量は1億4700万枚",
            "ko": "팩트 카드: 2026년 11월 22일 담보 없는 발행 이후 BNB체인의 ACE 토큰 공급량이 약 5,370만 개에서 약 1,002경 개(10,020,000,000,000,000,000개)로 늘어남. ACE의 최대 공급량은 1억 4,700만 개",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="ACE token contract on BNB Chain (BscScan), read Nov. 22, 2026; The Block; Blockaid")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of the Fusionist ACE token's hourly price on Nov. 21-22, 2026: steady near $0.086 until about 17:00 UTC on Nov. 22, then a fall to about $0.066 at 23:00 UTC and a partial rebound to about $0.076", {
            "es": "Gráfico de líneas del precio horario del token ACE de Fusionist del 21 al 22 de noviembre de 2026: estable cerca de 0,086 dólares hasta las 17:00 UTC del 22 de noviembre, luego una caída hasta unos 0,066 dólares a las 23:00 UTC y un rebote parcial hasta unos 0,076",
            "pt": "Gráfico de linha do preço horário do token ACE da Fusionist de 21 a 22 de novembro de 2026: estável perto de US$ 0,086 até cerca de 17h UTC de 22 de novembro, depois uma queda para cerca de US$ 0,066 às 23h UTC e uma recuperação parcial para cerca de US$ 0,076",
            "fr": "Courbe du cours horaire du jeton ACE de Fusionist les 21 et 22 novembre 2026 : stable vers 0,086 dollar jusqu'à environ 17 h UTC le 22 novembre, puis une baisse vers 0,066 dollar à 23 h UTC et un rebond partiel vers 0,076 dollar",
            "de": "Liniendiagramm des stündlichen Kurses des Fusionist-Tokens ACE am 21. und 22. November 2026: stabil bei rund 0,086 $ bis etwa 17:00 UTC am 22. November, dann ein Rückgang auf rund 0,066 $ um 23:00 UTC und eine teilweise Erholung auf rund 0,076 $",
            "ru": "Линейный график почасовой цены токена ACE проекта Fusionist 21–22 ноября 2026 года: около $0,086 примерно до 17:00 UTC 22 ноября, затем падение примерно до $0,066 к 23:00 UTC и частичный отскок примерно до $0,076",
            "tr": "Fusionist'in ACE tokeninin 21-22 Kasım 2026 saatlik fiyatının çizgi grafiği: 22 Kasım 17.00 UTC'ye kadar 0,086 $ civarında yatay, ardından 23.00 UTC'de yaklaşık 0,066 $'a düşüş ve yaklaşık 0,076 $'a kısmi toparlanma",
            "id": "Grafik garis harga per jam token ACE Fusionist pada 21-22 November 2026: stabil di sekitar US$0,086 hingga sekitar pukul 17.00 UTC 22 November, lalu turun ke sekitar US$0,066 pada pukul 23.00 UTC dan pulih sebagian ke sekitar US$0,076",
            "ja": "2026年11月21〜22日のFusionistのACEトークンの1時間ごとの価格の折れ線グラフ：11月22日17時（UTC）ごろまでは約0.086ドルで安定、その後23時（UTC）に約0.066ドルまで下落し、約0.076ドルまで一部回復",
            "ko": "2026년 11월 21~22일 퓨저니스트 ACE 토큰의 시간별 가격 선 그래프: 11월 22일 17시(UTC)께까지 약 0.086달러에서 안정, 이후 23시(UTC) 약 0.066달러로 하락했다가 약 0.076달러로 일부 반등",
         }),
         "caption": tr_map(CAPTION_CHART, src="CoinGecko, Fusionist (ACE) hourly prices, Nov. 21-22, 2026")},
    ]


def build_trump_dinner():
    slug = "trump-memecoin-second-dinner-token-down-99-percent-nov-2026"
    d = OUT / slug
    # Kraken TRUMPUSD daily closes (00:00 UTC candles) Jan 18, 2025 - Nov 22, 2026, frozen in chart-data.json.
    # Highest close $46.591 (Jan 19, 2025); May 22, 2025 (first dinner) close $14.717; record low $0.798 (Nov 21, 2026 06:00 UTC hour).
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    chart = make_line_chart(
        d / "chart-trump-daily-2025-2026",
        [r[0] for r in rows], [r[1] for r in rows],
        title="TRUMP daily close on Kraken, 2025-2026 (dashed line: first dinner, $14.72)",
        hline=14.717,
        hlabel=None,
        date_fmt="%b %Y",
        yfmt=lambda x, _p: f"${x:,.0f}",
    )
    fact = make_fact_card(
        d / "fact-leaderboard-8-6m-vs-148m",
        "TRUMP dinner leaderboard wallets",
        "$8.6M vs. $148M",
        "Combined holdings listed for the Nov. 22, 2026 dinner versus the first dinner in May 2025. One holder qualified with about $518 of TRUMP.",
        footer="Reuters · The Block (Washington Post analysis)",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of the TRUMP memecoin's daily closing price on Kraken from January 2025 to Nov. 22, 2026: a spike to about $46.59 in January 2025, about $14.72 on the day of the first holder dinner in May 2025, and a long slide to about $0.88", {
            "es": "Gráfico de líneas del precio de cierre diario del memecoin TRUMP en Kraken desde enero de 2025 hasta el 22 de noviembre de 2026: un pico de unos 46,59 dólares en enero de 2025, unos 14,72 dólares el día de la primera cena de tenedores en mayo de 2025 y una larga caída hasta unos 0,88 dólares",
            "pt": "Gráfico de linha do preço de fechamento diário da memecoin TRUMP na Kraken de janeiro de 2025 a 22 de novembro de 2026: um pico de cerca de US$ 46,59 em janeiro de 2025, cerca de US$ 14,72 no dia do primeiro jantar de detentores em maio de 2025 e uma longa queda até cerca de US$ 0,88",
            "fr": "Courbe du cours de clôture quotidien du memecoin TRUMP sur Kraken de janvier 2025 au 22 novembre 2026 : un pic vers 46,59 dollars en janvier 2025, environ 14,72 dollars le jour du premier dîner des détenteurs en mai 2025, puis une longue glissade jusqu'à environ 0,88 dollar",
            "de": "Liniendiagramm des täglichen Schlusskurses des TRUMP-Memecoins auf Kraken von Januar 2025 bis 22. November 2026: ein Hoch bei rund 46,59 $ im Januar 2025, rund 14,72 $ am Tag des ersten Halter-Dinners im Mai 2025 und ein langer Abstieg auf rund 0,88 $",
            "ru": "Линейный график дневной цены закрытия мемкоина TRUMP на Kraken с января 2025 года по 22 ноября 2026 года: всплеск примерно до $46,59 в январе 2025 года, около $14,72 в день первого ужина для держателей в мае 2025 года и долгое падение примерно до $0,88",
            "tr": "TRUMP memecoin'inin Ocak 2025'ten 22 Kasım 2026'ya Kraken'deki günlük kapanış fiyatının çizgi grafiği: Ocak 2025'te yaklaşık 46,59 $'a sıçrama, Mayıs 2025'teki ilk sahipler yemeği gününde yaklaşık 14,72 $ ve yaklaşık 0,88 $'a uzun bir düşüş",
            "id": "Grafik garis harga penutupan harian memecoin TRUMP di Kraken dari Januari 2025 hingga 22 November 2026: lonjakan ke sekitar US$46,59 pada Januari 2025, sekitar US$14,72 pada hari makan malam pemegang pertama pada Mei 2025, lalu penurunan panjang ke sekitar US$0,88",
            "ja": "2025年1月から2026年11月22日までのKrakenにおけるTRUMPミームコインの日次終値の折れ線グラフ：2025年1月に約46.59ドルまで急騰、2025年5月の初回保有者ディナー当日は約14.72ドル、その後約0.88ドルまで長期下落",
            "ko": "2025년 1월부터 2026년 11월 22일까지 크라켄의 TRUMP 밈코인 일일 종가 선 그래프: 2025년 1월 약 46.59달러로 급등, 2025년 5월 첫 보유자 만찬 당일 약 14.72달러, 이후 약 0.88달러까지 장기 하락",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken, TRUMP/USD daily closes, Jan. 2025 - Nov. 22, 2026")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: wallets on the public leaderboard for the Nov. 22, 2026 TRUMP dinner held a combined $8.6 million, versus $148 million for the first dinner in May 2025; one holder qualified with about $518 of TRUMP", {
            "es": "Tarjeta de datos: las carteras de la clasificación pública para la cena TRUMP del 22 de noviembre de 2026 sumaban 8,6 millones de dólares, frente a 148 millones en la primera cena de mayo de 2025; un tenedor se clasificó con unos 518 dólares en TRUMP",
            "pt": "Cartão de dados: as carteiras do ranking público para o jantar TRUMP de 22 de novembro de 2026 somavam US$ 8,6 milhões, contra US$ 148 milhões no primeiro jantar, em maio de 2025; um detentor se classificou com cerca de US$ 518 em TRUMP",
            "fr": "Fiche chiffrée : les portefeuilles du classement public du dîner TRUMP du 22 novembre 2026 détenaient au total 8,6 millions de dollars, contre 148 millions pour le premier dîner en mai 2025 ; un détenteur s'est qualifié avec environ 518 dollars de TRUMP",
            "de": "Faktenkarte: Die Wallets auf der öffentlichen Rangliste für das TRUMP-Dinner am 22. November 2026 hielten zusammen 8,6 Mio. $, beim ersten Dinner im Mai 2025 waren es 148 Mio. $; ein Halter qualifizierte sich mit TRUMP im Wert von rund 518 $",
            "ru": "Карточка с фактом: кошельки из публичного рейтинга ужина TRUMP 22 ноября 2026 года вместе держали $8,6 млн против $148 млн перед первым ужином в мае 2025 года; один держатель прошёл отбор, имея TRUMP примерно на $518",
            "tr": "Bilgi kartı: 22 Kasım 2026 TRUMP yemeğinin herkese açık sıralamasındaki cüzdanlar toplam 8,6 milyon $ tutuyordu; Mayıs 2025'teki ilk yemekte bu rakam 148 milyon $'dı; bir sahip yaklaşık 518 $'lık TRUMP ile yer kazandı",
            "id": "Kartu fakta: dompet di papan peringkat publik untuk makan malam TRUMP 22 November 2026 memegang total US$8,6 juta, dibandingkan US$148 juta untuk makan malam pertama pada Mei 2025; satu pemegang lolos dengan TRUMP senilai sekitar US$518",
            "ja": "ファクトカード：2026年11月22日のTRUMPディナーの公開ランキングに載ったウォレットの保有額は合計860万ドル。2025年5月の初回ディナーでは1億4800万ドルだった。約518ドル分のTRUMPで出席資格を得た保有者もいた",
            "ko": "팩트 카드: 2026년 11월 22일 TRUMP 만찬 공개 순위표에 오른 지갑들의 보유액 합계는 860만 달러로, 2025년 5월 첫 만찬 때의 1억 4,800만 달러에 크게 못 미침. 약 518달러어치 TRUMP로 자격을 얻은 보유자도 있었음",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Reuters; The Block, citing a Washington Post analysis")},
    ]


def build_etf_weekly_179():
    slug = "bitcoin-etfs-1-79-billion-weekly-outflow-fourth-week-nov-2026"
    d = OUT / slug
    # Weekly sums of Farside's daily "Total" column (US$m), weeks starting Sep 28 - Nov 16, 2026, frozen in chart-data.json.
    data = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    labels = ["Week of " + w[0] if i == 0 else w[0] for i, w in enumerate(data["weeks"])]
    vals = [w[1] for w in data["weeks"]]
    cols = ["#34d399" if v > 0 else "#f87171" for v in vals]
    chart = make_bar_chart(
        d / "chart-btc-etf-weekly-flows",
        labels, vals,
        title="U.S. spot bitcoin ETFs: weekly net flows, Sep. 28 - Nov. 20, 2026 (US$ millions)",
        colors=cols,
        value_fmt=lambda v: (f"+${v:,.0f}M" if v > 0 else f"-${-v:,.0f}M"),
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    fact = make_fact_card(
        d / "fact-ibit-544-7-million-record",
        "BlackRock IBIT · Friday, Nov. 20, 2026",
        "-$544.7 million",
        "IBIT's biggest one-day outflow since its 2024 launch, beating the $541.1 million record set a day earlier.",
        footer="Farside Investors, daily IBIT flows since Jan. 2024",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of weekly net flows into U.S. spot bitcoin ETFs from the week of Sep. 28 to the week of Nov. 16, 2026: +$241M, -$679M, -$228M, +$301M, then four straight weeks of outflows: -$202M, -$1,282M, -$1,065M and -$1,790M", {
            "es": "Gráfico de barras de los flujos netos semanales de los ETF de bitcoin al contado de EE. UU. desde la semana del 28 de septiembre hasta la del 16 de noviembre de 2026: +241 M$, -679 M$, -228 M$, +301 M$ y luego cuatro semanas seguidas de salidas: -202 M$, -1.282 M$, -1.065 M$ y -1.790 M$",
            "pt": "Gráfico de barras dos fluxos líquidos semanais dos ETFs de bitcoin à vista dos EUA da semana de 28 de setembro à de 16 de novembro de 2026: +US$ 241 mi, -US$ 679 mi, -US$ 228 mi, +US$ 301 mi e depois quatro semanas seguidas de saídas: -US$ 202 mi, -US$ 1.282 mi, -US$ 1.065 mi e -US$ 1.790 mi",
            "fr": "Graphique en barres des flux nets hebdomadaires des ETF bitcoin au comptant américains, de la semaine du 28 septembre à celle du 16 novembre 2026 : +241 M$, -679 M$, -228 M$, +301 M$, puis quatre semaines de sorties d'affilée : -202 M$, -1 282 M$, -1 065 M$ et -1 790 M$",
            "de": "Balkendiagramm der wöchentlichen Nettozuflüsse der US-Spot-Bitcoin-ETFs von der Woche ab 28. September bis zur Woche ab 16. November 2026: +241 Mio. $, -679 Mio. $, -228 Mio. $, +301 Mio. $, danach vier Abflusswochen in Folge: -202 Mio. $, -1.282 Mio. $, -1.065 Mio. $ und -1.790 Mio. $",
            "ru": "Столбчатая диаграмма недельных чистых потоков американских спотовых биткоин-ETF с недели 28 сентября по неделю 16 ноября 2026 года: +$241 млн, -$679 млн, -$228 млн, +$301 млн, затем четыре недели оттока подряд: -$202 млн, -$1282 млн, -$1065 млн и -$1790 млн",
            "tr": "ABD spot bitcoin ETF'lerinin 28 Eylül haftasından 16 Kasım 2026 haftasına kadar haftalık net akışlarının çubuk grafiği: +241 milyon $, -679 milyon $, -228 milyon $, +301 milyon $, ardından üst üste dört haftalık çıkış: -202 milyon $, -1.282 milyon $, -1.065 milyon $ ve -1.790 milyon $",
            "id": "Grafik batang arus bersih mingguan ETF bitcoin spot AS dari pekan 28 September hingga pekan 16 November 2026: +US$241 juta, -US$679 juta, -US$228 juta, +US$301 juta, lalu empat pekan arus keluar berturut-turut: -US$202 juta, -US$1.282 juta, -US$1.065 juta, dan -US$1.790 juta",
            "ja": "米国の現物ビットコインETFの週間純フローの棒グラフ（2026年9月28日の週から11月16日の週まで）：プラス2億4100万ドル、マイナス6億7900万ドル、マイナス2億2800万ドル、プラス3億100万ドルの後、4週連続の流出：マイナス2億200万ドル、マイナス12億8200万ドル、マイナス10億6500万ドル、マイナス17億9000万ドル",
            "ko": "2026년 9월 28일 주간부터 11월 16일 주간까지 미국 현물 비트코인 ETF의 주간 순흐름 막대 차트: +2억4100만 달러, -6억7900만 달러, -2억2800만 달러, +3억100만 달러, 이후 4주 연속 유출: -2억200만 달러, -12억8200만 달러, -10억6500만 달러, -17억9000만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: BlackRock's IBIT lost a net $544.7 million on Friday, Nov. 20, 2026, its biggest one-day outflow since its 2024 launch, beating the $541.1 million record set a day earlier", {
            "es": "Tarjeta de datos: el IBIT de BlackRock perdió 544,7 millones de dólares netos el viernes 20 de noviembre de 2026, su mayor salida en un día desde su lanzamiento en 2024, por encima del récord de 541,1 millones fijado un día antes",
            "pt": "Cartão de dados: o IBIT da BlackRock perdeu US$ 544,7 milhões líquidos na sexta-feira, 20 de novembro de 2026, sua maior saída em um dia desde o lançamento em 2024, superando o recorde de US$ 541,1 milhões do dia anterior",
            "fr": "Fiche chiffrée : l'IBIT de BlackRock a perdu 544,7 millions de dollars nets le vendredi 20 novembre 2026, sa plus forte sortie sur une journée depuis son lancement en 2024, au-delà du record de 541,1 millions établi la veille",
            "de": "Faktenkarte: BlackRocks IBIT verlor am Freitag, 20. November 2026, netto 544,7 Mio. $, der größte Tagesabfluss seit dem Start 2024, und übertraf damit den Rekord von 541,1 Mio. $ vom Vortag",
            "ru": "Карточка с фактом: из IBIT от BlackRock в пятницу, 20 ноября 2026 года, ушло $544,7 млн чистыми, это крупнейший дневной отток с запуска фонда в 2024 году, выше рекорда в $541,1 млн, установленного днём ранее",
            "tr": "Bilgi kartı: BlackRock'ın IBIT fonundan 20 Kasım 2026 Cuma günü net 544,7 milyon $ çıktı; bu, fonun 2024'teki lansmanından bu yana en büyük günlük çıkış ve bir gün önceki 541,1 milyon $'lık rekoru geride bırakıyor",
            "id": "Kartu fakta: IBIT milik BlackRock kehilangan bersih US$544,7 juta pada Jumat, 20 November 2026, arus keluar harian terbesar sejak peluncurannya pada 2024, melampaui rekor US$541,1 juta sehari sebelumnya",
            "ja": "ファクトカード：ブラックロックのIBITは2026年11月20日（金）に純額5億4470万ドルの流出。2024年の上場以来最大の1日の流出で、前日に記録した5億4110万ドルを上回った",
            "ko": "팩트 카드: 블랙록 IBIT에서 2026년 11월 20일(금) 순 5억4470만 달러가 빠져나가 2024년 출시 이후 최대 일일 유출을 기록, 하루 전 세운 5억4110만 달러 기록을 넘어섬",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Farside Investors")},
    ]


def build_strategy_457():
    slug = "strategy-buys-457-bitcoin-212-million-strc-buyback-nov-2026"
    d = OUT / slug
    # Strategy Form 8-K, Nov. 23, 2026 (period Nov. 16-22): BTC purchases $29.6M, STRC repurchases $211.8M, preferred dividends paid from USD Reserve $17.6M.
    chart = make_bar_chart(
        d / "chart-strategy-uses-of-cash-nov-16-22",
        ["Bitcoin bought\n(457 BTC)", "STRC shares\nbought back", "Preferred dividends\npaid"],
        [29.6, 211.8, 17.6],
        title="Where Strategy's money went, Nov. 16-22, 2026 (US$ millions)",
        colors=["#f7931a", "#38bdf8", "#94a3b8"],
        value_fmt=lambda v: f"${v:,.1f}M",
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    fact = make_fact_card(
        d / "fact-strategy-851305-btc",
        "Strategy bitcoin holdings · Nov. 22, 2026",
        "851,305 BTC",
        "bought for about $64.23 billion, an average of $75,446 per coin. Last week's 457 BTC cost $64,898 each.",
        footer="Strategy Form 8-K, Nov. 23, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of how Strategy used its money from Nov. 16 to 22, 2026: $29.6 million on 457 bitcoin, $211.8 million buying back STRC preferred shares and $17.6 million on preferred dividends", {
            "es": "Gráfico de barras de cómo usó Strategy su dinero del 16 al 22 de noviembre de 2026: 29,6 millones de dólares en 457 bitcoins, 211,8 millones en recomprar acciones preferentes STRC y 17,6 millones en dividendos preferentes",
            "pt": "Gráfico de barras de como a Strategy usou seu dinheiro de 16 a 22 de novembro de 2026: US$ 29,6 milhões em 457 bitcoins, US$ 211,8 milhões na recompra de ações preferenciais STRC e US$ 17,6 milhões em dividendos preferenciais",
            "fr": "Graphique en barres de l'utilisation de l'argent de Strategy du 16 au 22 novembre 2026 : 29,6 millions de dollars pour 457 bitcoins, 211,8 millions pour racheter des actions privilégiées STRC et 17,6 millions de dividendes privilégiés",
            "de": "Balkendiagramm, wofür Strategy vom 16. bis 22. November 2026 Geld ausgab: 29,6 Mio. $ für 457 Bitcoin, 211,8 Mio. $ für den Rückkauf von STRC-Vorzugsaktien und 17,6 Mio. $ für Vorzugsdividenden",
            "ru": "Столбчатая диаграмма расходов Strategy с 16 по 22 ноября 2026 года: $29,6 млн на 457 биткоинов, $211,8 млн на выкуп привилегированных акций STRC и $17,6 млн на дивиденды по привилегированным акциям",
            "tr": "Strategy'nin 16-22 Kasım 2026 arasında parasını nasıl kullandığını gösteren çubuk grafik: 457 bitcoin için 29,6 milyon $, STRC imtiyazlı hisselerinin geri alımı için 211,8 milyon $ ve imtiyazlı hisse temettüleri için 17,6 milyon $",
            "id": "Grafik batang penggunaan dana Strategy pada 16-22 November 2026: US$29,6 juta untuk 457 bitcoin, US$211,8 juta untuk membeli kembali saham preferen STRC, dan US$17,6 juta untuk dividen saham preferen",
            "ja": "2026年11月16日から22日にストラテジーが資金をどう使ったかを示す棒グラフ：457ビットコインの購入に2960万ドル、STRC優先株の買い戻しに2億1180万ドル、優先株配当に1760万ドル",
            "ko": "2026년 11월 16~22일 스트래티지의 자금 사용처 막대 차트: 비트코인 457개 매수에 2960만 달러, STRC 우선주 재매입에 2억1180만 달러, 우선주 배당에 1760만 달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Strategy Form 8-K, Nov. 23, 2026")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Strategy held 851,305 bitcoin as of Nov. 22, 2026, bought for about $64.23 billion at an average of $75,446 per coin; last week's 457 BTC cost $64,898 each", {
            "es": "Tarjeta de datos: Strategy tenía 851.305 bitcoins al 22 de noviembre de 2026, comprados por unos 64.230 millones de dólares a un promedio de 75.446 dólares por moneda; los 457 BTC de la semana pasada costaron 64.898 dólares cada uno",
            "pt": "Cartão de dados: a Strategy tinha 851.305 bitcoins em 22 de novembro de 2026, comprados por cerca de US$ 64,23 bilhões a uma média de US$ 75.446 por moeda; os 457 BTC da semana passada custaram US$ 64.898 cada",
            "fr": "Fiche chiffrée : Strategy détenait 851 305 bitcoins au 22 novembre 2026, achetés pour environ 64,23 milliards de dollars, soit 75 446 dollars en moyenne par bitcoin ; les 457 BTC de la semaine dernière ont coûté 64 898 dollars pièce",
            "de": "Faktenkarte: Strategy hielt am 22. November 2026 851.305 Bitcoin, gekauft für rund 64,23 Mrd. $ zu durchschnittlich 75.446 $ je Coin; die 457 BTC der Vorwoche kosteten je 64.898 $",
            "ru": "Карточка с фактом: на 22 ноября 2026 года у Strategy было 851 305 биткоинов, купленных примерно за $64,23 млрд по средней цене $75 446 за монету; 457 BTC за прошлую неделю обошлись по $64 898 за штуку",
            "tr": "Bilgi kartı: Strategy 22 Kasım 2026 itibarıyla 851.305 bitcoin tutuyordu; bunları coin başına ortalama 75.446 $'dan yaklaşık 64,23 milyar $'a aldı; geçen haftaki 457 BTC'nin her biri 64.898 $'a mal oldu",
            "id": "Kartu fakta: Strategy memegang 851.305 bitcoin per 22 November 2026, dibeli sekitar US$64,23 miliar dengan rata-rata US$75.446 per koin; 457 BTC pekan lalu dibeli seharga US$64.898 per koin",
            "ja": "ファクトカード：ストラテジーは2026年11月22日時点で851,305ビットコインを保有。取得総額は約642億3000万ドル、平均取得価格は1枚75,446ドル。先週の457BTCは1枚64,898ドル",
            "ko": "팩트 카드: 스트래티지는 2026년 11월 22일 기준 비트코인 851,305개를 보유, 총 약 642억3000만 달러에 개당 평균 75,446달러로 매수. 지난주 457 BTC는 개당 64,898달러",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Strategy Form 8-K, Nov. 23, 2026")},
    ]


def build_binance_security_review():
    slug = "binance-hires-mandiant-slowmist-verichains-security-review-nov-2026"
    d = OUT / slug
    # Dates/figures: Reuters (Oct. 29 hack ~ $6.3B; Nov. 18 ADGM order), CoinDesk (Nov. 1 phased reopening),
    # Bitcoin Magazine (Nov. 12 coverage > $6.34B), Binance / PR Newswire (Nov. 23 engagement of three firms).
    tl = make_timeline_card(
        d / "timeline-binance-hack-to-security-review",
        "Binance since the October hack",
        [
            ("Oct. 29", "Hackers take about $6.3 billion from Binance hot wallets", (248, 113, 113)),
            ("Nov. 1", "Withdrawals start reopening in phases", (96, 165, 250)),
            ("Nov. 12", "Binance says it covered the losses with $6.34B+ of its own money", GREEN),
            ("Nov. 18", "Abu Dhabi court order to help recover frozen funds", (96, 165, 250)),
            ("Nov. 23", "Mandiant, SlowMist and Verichains hired to review security", ORANGE),
        ],
        footer="Reuters · CoinDesk · Bitcoin Magazine · Binance",
        margin=150, wrap_w=200,
    )
    fact = make_fact_card(
        d / "fact-binance-three-firms-review",
        "Binance security chief Jimmy Su · Nov. 23, 2026",
        "3 outside firms",
        "\u201cThey will review our systems and tell us where we can be stronger. We are committed to acting on what they find.\u201d",
        footer="Binance announcement via PR Newswire, Nov. 23, 2026",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "timeline",
         "alt": alts("Timeline: on Oct. 29 hackers took about $6.3 billion from Binance; on Nov. 1 withdrawals started reopening in phases; on Nov. 12 Binance said it covered the losses with more than $6.34 billion of its own money; on Nov. 18 it got an Abu Dhabi court order to help recover frozen funds; on Nov. 23 it hired Mandiant, SlowMist and Verichains to review its security", {
            "es": "Cronología: el 29 de octubre unos hackers robaron cerca de 6.300 millones de dólares a Binance; el 1 de noviembre los retiros empezaron a reabrirse por fases; el 12 de noviembre Binance dijo que cubrió las pérdidas con más de 6.340 millones de dólares propios; el 18 de noviembre obtuvo una orden judicial en Abu Dabi para recuperar fondos congelados; el 23 de noviembre contrató a Mandiant, SlowMist y Verichains para revisar su seguridad",
            "pt": "Linha do tempo: em 29 de outubro hackers levaram cerca de US$ 6,3 bilhões da Binance; em 1º de novembro os saques começaram a reabrir em etapas; em 12 de novembro a Binance disse ter coberto as perdas com mais de US$ 6,34 bilhões próprios; em 18 de novembro obteve uma ordem judicial em Abu Dhabi para recuperar fundos congelados; em 23 de novembro contratou Mandiant, SlowMist e Verichains para revisar sua segurança",
            "fr": "Chronologie : le 29 octobre, des pirates dérobent environ 6,3 milliards de dollars à Binance ; le 1er novembre, les retraits rouvrent par étapes ; le 12 novembre, Binance dit avoir couvert les pertes avec plus de 6,34 milliards de dollars de ses fonds ; le 18 novembre, elle obtient une ordonnance d'un tribunal d'Abou Dhabi pour récupérer des fonds gelés ; le 23 novembre, elle engage Mandiant, SlowMist et Verichains pour auditer sa sécurité",
            "de": "Zeitleiste: Am 29. Oktober erbeuten Hacker rund 6,3 Mrd. $ bei Binance; am 1. November öffnen Auszahlungen schrittweise wieder; am 12. November erklärt Binance, die Verluste mit über 6,34 Mrd. $ aus eigenen Mitteln gedeckt zu haben; am 18. November erhält Binance einen Gerichtsbeschluss in Abu Dhabi zur Rückholung eingefrorener Gelder; am 23. November beauftragt Binance Mandiant, SlowMist und Verichains mit einer Sicherheitsprüfung",
            "ru": "Хронология: 29 октября хакеры похитили у Binance около $6,3 млрд; 1 ноября вывод средств начали поэтапно открывать; 12 ноября Binance заявила, что покрыла потери более чем $6,34 млрд собственных средств; 18 ноября биржа получила судебный приказ в Абу-Даби для возврата замороженных средств; 23 ноября наняла Mandiant, SlowMist и Verichains для проверки безопасности",
            "tr": "Zaman çizelgesi: 29 Ekim'de hackerlar Binance'ten yaklaşık 6,3 milyar $ çaldı; 1 Kasım'da para çekme işlemleri aşamalı olarak yeniden açılmaya başladı; 12 Kasım'da Binance kayıpları kendi kasasından 6,34 milyar $'ı aşan tutarla karşıladığını söyledi; 18 Kasım'da dondurulan fonları geri almak için Abu Dabi'de mahkeme kararı aldı; 23 Kasım'da güvenliğini incelemeleri için Mandiant, SlowMist ve Verichains'i görevlendirdi",
            "id": "Linimasa: pada 29 Oktober peretas mengambil sekitar US$6,3 miliar dari Binance; pada 1 November penarikan mulai dibuka kembali bertahap; pada 12 November Binance mengatakan telah menutup kerugian dengan lebih dari US$6,34 miliar dana sendiri; pada 18 November Binance memperoleh perintah pengadilan Abu Dhabi untuk memulihkan dana yang dibekukan; pada 23 November Binance menunjuk Mandiant, SlowMist, dan Verichains untuk meninjau keamanannya",
            "ja": "時系列：10月29日、ハッカーがバイナンスから約63億ドルを奪う。11月1日、出金が段階的に再開。11月12日、バイナンスが自己資金63億4000万ドル超で損失を補填したと発表。11月18日、凍結資金の回収に向けアブダビの裁判所命令を取得。11月23日、Mandiant、SlowMist、Verichainsにセキュリティ審査を依頼",
            "ko": "타임라인: 10월 29일 해커가 바이낸스에서 약 63억 달러 탈취; 11월 1일 출금이 단계적으로 재개; 11월 12일 바이낸스가 자체 자금 63억4000만 달러 이상으로 손실을 보전했다고 발표; 11월 18일 동결 자금 회수를 위한 아부다비 법원 명령 확보; 11월 23일 맨디언트, 슬로우미스트, 베리체인스에 보안 점검 의뢰",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Reuters, CoinDesk, Bitcoin Magazine, Binance")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Binance has hired 3 outside firms. Security chief Jimmy Su: \u201cThey will review our systems and tell us where we can be stronger. We are committed to acting on what they find.\u201d", {
            "es": "Tarjeta: Binance contrató a 3 firmas externas. El jefe de seguridad Jimmy Su: \u201cRevisarán nuestros sistemas y nos dirán dónde podemos ser más fuertes. Nos comprometemos a actuar según lo que encuentren.\u201d",
            "pt": "Cartão: a Binance contratou 3 empresas externas. O chefe de segurança Jimmy Su: \u201cElas vão revisar nossos sistemas e nos dizer onde podemos ser mais fortes. Estamos comprometidos a agir com base no que encontrarem.\u201d",
            "fr": "Fiche : Binance a engagé 3 cabinets extérieurs. Son responsable de la sécurité, Jimmy Su : « Ils examineront nos systèmes et nous diront où nous pouvons être plus solides. Nous nous engageons à agir sur ce qu'ils trouveront. »",
            "de": "Faktenkarte: Binance hat 3 externe Firmen beauftragt. Sicherheitschef Jimmy Su: \u201eSie werden unsere Systeme prüfen und uns sagen, wo wir stärker werden können. Wir verpflichten uns, auf ihre Ergebnisse zu reagieren.\u201c",
            "ru": "Карточка: Binance наняла 3 внешние компании. Директор по безопасности Джимми Су: «Они проверят наши системы и скажут, где мы можем стать сильнее. Мы намерены действовать по итогам их выводов».",
            "tr": "Bilgi kartı: Binance 3 dış firmayla anlaştı. Güvenlik şefi Jimmy Su: \u201cSistemlerimizi inceleyip nerede daha güçlü olabileceğimizi söyleyecekler. Bulduklarına göre harekete geçmeye kararlıyız.\u201d",
            "id": "Kartu fakta: Binance menunjuk 3 perusahaan luar. Kepala keamanan Jimmy Su: \u201cMereka akan meninjau sistem kami dan memberi tahu di mana kami bisa lebih kuat. Kami berkomitmen menindaklanjuti temuan mereka.\u201d",
            "ja": "ファクトカード：バイナンスは外部の3社に依頼。最高セキュリティ責任者ジミー・スー氏「彼らは当社のシステムを審査し、どこを強化できるかを教えてくれる。我々は彼らの指摘に基づいて行動することを約束する」",
            "ko": "팩트 카드: 바이낸스가 외부 업체 3곳에 의뢰. 지미 수 최고보안책임자: \u201c그들이 우리 시스템을 점검하고 어디를 더 강화할 수 있는지 알려줄 것이다. 우리는 그들의 지적에 따라 조치할 것을 약속한다.\u201d",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Binance via PR Newswire, Nov. 23, 2026")},
    ]


def build_ark_withdraws_cd20():
    slug = "ark-invest-withdraws-coindesk-20-crypto-etfs-nov-2026"
    d = OUT / slug
    import datetime as dt
    # Kraken public daily OHLC (XBTUSD), closed daily candles Jan. 1 to Nov. 22, 2026 (close = next 00:00 UTC).
    url = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440&since=1767225600"
    req = urllib.request.Request(url, headers={"User-Agent": "PlainBTC/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.loads(resp.read().decode())["result"]["XXBTZUSD"]
    end = dt.datetime(2026, 11, 22, tzinfo=dt.UTC).timestamp()
    rows = [r for r in rows if r[0] <= end]
    xs = [dt.datetime.fromtimestamp(r[0], dt.UTC) for r in rows]
    ys = [float(r[4]) for r in rows]
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Bitcoin from ARK's filing to its withdrawal request (Kraken daily close, US$)")
    orange = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    ax.plot(xs, ys, color=orange, linewidth=2.2)
    ax.fill_between(xs, ys, min(ys) * 0.97, color=orange, alpha=0.12)
    for day, label, col in ((dt.datetime(2026, 1, 23, tzinfo=dt.UTC), "Jan. 23: ARK files S-1s", "#38bdf8"),
                            (dt.datetime(2026, 11, 20, tzinfo=dt.UTC), "Nov. 20: withdrawal requests", "#f87171")):
        i = xs.index(day)
        ax.axvline(day, color=col, linestyle="--", linewidth=1.4)
        ax.scatter([day], [ys[i]], color=col, s=60, zorder=5)
        ax.annotate(f"{label}\n${ys[i]:,.0f}", (day, ys[i]), xytext=(12 if i < len(xs) / 2 else -12, 30),
                    textcoords="offset points", ha="left" if i < len(xs) / 2 else "right",
                    color=col, fontsize=12, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
    plt.tight_layout(pad=1.2)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor()); plt.close(fig); buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-bitcoin-ark-filing-to-withdrawal")
    cmp_ = make_compare_card(
        d / "compare-ark-two-coindesk-20-funds",
        "The two ARK funds that will not launch",
        "Full-index fund",
        "ex-Bitcoin fund",
        [
            ("Goal", "Follow the CoinDesk 20, an index of 20 large cryptos", "Same index, with bitcoin exposure stripped out"),
            ("How", "Long CoinDesk 20 index futures, no coins held", "Index futures plus short CME bitcoin futures"),
            ("Status", "Never effective, no shares sold", "Never effective, no shares sold"),
        ],
        footer="ARK Form RW filings, Nov. 20, 2026 · CoinDesk",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts(f"Line chart of bitcoin's daily close on Kraken in 2026: about ${ys[xs.index(dt.datetime(2026,1,23,tzinfo=dt.UTC))]:,.0f} on Jan. 23, when ARK filed for its CoinDesk 20 ETFs, and about ${ys[xs.index(dt.datetime(2026,11,20,tzinfo=dt.UTC))]:,.0f} on Nov. 20, when it asked the SEC to withdraw them", {
            "es": "Gráfico de líneas del cierre diario de bitcoin en Kraken en 2026: unos 89.495 dólares el 23 de enero, cuando ARK registró sus ETF del CoinDesk 20, y unos 58.806 dólares el 20 de noviembre, cuando pidió a la SEC retirarlos",
            "pt": "Gráfico de linha do fechamento diário do bitcoin na Kraken em 2026: cerca de US$ 89.495 em 23 de janeiro, quando a ARK registrou seus ETFs do CoinDesk 20, e cerca de US$ 58.806 em 20 de novembro, quando pediu à SEC para retirá-los",
            "fr": "Graphique en courbe de la clôture quotidienne du bitcoin sur Kraken en 2026 : environ 89 495 dollars le 23 janvier, quand ARK a déposé ses ETF CoinDesk 20, et environ 58 806 dollars le 20 novembre, quand elle a demandé à la SEC de les retirer",
            "de": "Liniendiagramm des täglichen Bitcoin-Schlusskurses bei Kraken 2026: rund 89.495 $ am 23. Januar, als ARK seine CoinDesk-20-ETFs anmeldete, und rund 58.806 $ am 20. November, als ARK die SEC um Rücknahme bat",
            "ru": "Линейный график дневного закрытия биткоина на Kraken в 2026 году: около $89 495 23 января, когда ARK подала заявки на ETF на CoinDesk 20, и около $58 806 20 ноября, когда она попросила SEC их отозвать",
            "tr": "Bitcoin'in 2026'da Kraken'deki günlük kapanışını gösteren çizgi grafik: ARK'ın CoinDesk 20 ETF'leri için başvurduğu 23 Ocak'ta yaklaşık 89.495 $, SEC'ten bunları geri çekmeyi istediği 20 Kasım'da yaklaşık 58.806 $",
            "id": "Grafik garis harga penutupan harian bitcoin di Kraken pada 2026: sekitar US$89.495 pada 23 Januari, saat ARK mendaftarkan ETF CoinDesk 20, dan sekitar US$58.806 pada 20 November, saat ARK meminta SEC menariknya",
            "ja": "2026年のクラーケンにおけるビットコイン日次終値の折れ線グラフ：ARKがCoinDesk 20 ETFを申請した1月23日は約89,495ドル、SECに取り下げを求めた11月20日は約58,806ドル",
            "ko": "2026년 크라켄 비트코인 일일 종가 선 차트: ARK가 코인데스크 20 ETF를 신청한 1월 23일 약 89,495달러, SEC에 철회를 요청한 11월 20일 약 58,806달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken")},
        {"id": "compare", "file": cmp_.name, "w": 1200, "h": 630, "kind": "compare",
         "alt": alts("Comparison of the two ARK funds that will not launch: the full-index fund would have followed the CoinDesk 20 through index futures; the ex-Bitcoin fund would have added short CME bitcoin futures to strip out bitcoin. Neither became effective or sold shares", {
            "es": "Comparación de los dos fondos de ARK que no se lanzarán: el fondo del índice completo habría seguido el CoinDesk 20 con futuros sobre el índice; el fondo sin bitcoin habría añadido futuros cortos de bitcoin de CME para quitar el bitcoin. Ninguno entró en vigor ni vendió acciones",
            "pt": "Comparação dos dois fundos da ARK que não serão lançados: o fundo do índice completo seguiria o CoinDesk 20 com futuros do índice; o fundo sem bitcoin acrescentaria futuros vendidos de bitcoin da CME para tirar o bitcoin. Nenhum entrou em vigor nem vendeu cotas",
            "fr": "Comparaison des deux fonds d'ARK qui ne verront pas le jour : le fonds sur l'indice complet aurait suivi le CoinDesk 20 via des contrats à terme sur l'indice ; le fonds hors bitcoin y aurait ajouté des positions vendeuses sur les contrats à terme bitcoin du CME pour retirer le bitcoin. Aucun n'est entré en vigueur ni n'a vendu de parts",
            "de": "Vergleich der zwei ARK-Fonds, die nicht starten: Der Gesamtindex-Fonds hätte den CoinDesk 20 über Indexfutures abgebildet; der Ex-Bitcoin-Fonds hätte zusätzlich CME-Bitcoin-Futures leerverkauft, um Bitcoin herauszurechnen. Keiner wurde wirksam oder verkaufte Anteile",
            "ru": "Сравнение двух фондов ARK, которые не будут запущены: фонд на полный индекс следовал бы за CoinDesk 20 через фьючерсы на индекс; фонд без биткоина добавлял бы короткие позиции по биткоин-фьючерсам CME, чтобы убрать биткоин. Ни один не вступил в силу и не продал ни одной акции",
            "tr": "Piyasaya çıkmayacak iki ARK fonunun karşılaştırması: tam endeks fonu CoinDesk 20'yi endeks vadelileriyle izleyecekti; bitcoin hariç fon ise bitcoini çıkarmak için CME bitcoin vadelilerinde kısa pozisyon ekleyecekti. Hiçbiri yürürlüğe girmedi, hisse satmadı",
            "id": "Perbandingan dua dana ARK yang batal diluncurkan: dana indeks penuh akan mengikuti CoinDesk 20 lewat kontrak berjangka indeks; dana tanpa bitcoin akan menambah posisi short kontrak berjangka bitcoin CME untuk menghapus bitcoin. Keduanya tidak pernah efektif dan tidak menjual saham",
            "ja": "立ち上げられないARKの2本のファンドの比較：全指数型はCoinDesk 20を指数先物で追う設計、ビットコイン除外型はさらにCMEビットコイン先物を売り建ててビットコイン分を除く設計。どちらも登録は発効せず、株式も販売されていない",
            "ko": "출시되지 않을 ARK 펀드 2종 비교: 전체 지수 펀드는 지수 선물로 코인데스크 20을 추종하고, 비트코인 제외 펀드는 CME 비트코인 선물 매도를 더해 비트코인을 제외할 계획이었다. 둘 다 효력이 발생하지 않았고 주식도 판매되지 않았다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="ARK Form RW filings (SEC EDGAR), CoinDesk")},
    ]


def build_huang_btc_fade():
    slug = "bitcoin-spikes-to-64500-on-huang-return-then-fades-nov-2026"
    d = OUT / slug
    import datetime as dt
    # Kraken XBTUSD 15-minute candles Nov 23, 2026 00:00-17:45 CST, frozen in chart-data.json at 6:00 p.m. CST.
    rows = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))["rows"]
    cst = lambda ts: dt.datetime.fromtimestamp(ts - 6 * 3600, dt.UTC)   # CST wall clock on a UTC axis
    xs = [cst(r[0]) for r in rows]; ys = [r[1] for r in rows]
    hi_i = max(range(len(rows)), key=lambda i: rows[i][2]); lo_i = min(range(len(rows)), key=lambda i: rows[i][3] if rows[i][0] > rows[hi_i][0] else 1e9)
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
    style_axes(ax, "Bitcoin on Monday, Nov. 23 (Kraken, 15-minute closes, Central time)")
    orange = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    ax.plot(xs, ys, color=orange, linewidth=2.4)
    ax.fill_between(xs, ys, 60000, color=orange, alpha=0.12)
    news = dt.datetime(2026, 11, 23, 7, 55, tzinfo=dt.UTC)
    ax.axvline(news, color="#38bdf8", linestyle="--", linewidth=1.4)
    ax.text(news - dt.timedelta(minutes=12), 64650, "Nvidia reinstates\nJensen Huang", color="#38bdf8", fontsize=12, fontweight="bold", ha="right", va="top")
    hx, hv = xs[hi_i], rows[hi_i][2]; lx, lv = xs[lo_i], rows[lo_i][3]
    ax.scatter([hx], [hv], color=GREEN and "#34d399", s=70, zorder=5)
    ax.annotate(f"High ${hv:,.0f}", (hx, hv), xytext=(12, 4), textcoords="offset points", color="#34d399", fontsize=13, fontweight="bold")
    ax.scatter([lx], [lv], color="#f87171", s=70, zorder=5)
    ax.annotate(f"Afternoon low ${lv:,.0f}", (lx, lv), xytext=(10, -18), textcoords="offset points", color="#f87171", fontsize=13, fontweight="bold")
    ax.annotate(f"5:45 p.m. ${ys[-1]:,.0f}", (xs[-1], ys[-1]), xytext=(-8, 22), textcoords="offset points", color="#e2e8f0", fontsize=12, fontweight="bold", ha="right")
    ax.set_ylim(60000, 65000)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-I %p"))
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
    plt.tight_layout(pad=1.2)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor()); plt.close(fig); buf.seek(0)
    chart = save_image(Image.open(buf).convert("RGB"), d / "chart-bitcoin-nov-23-huang-spike-kraken")
    assert round(hv) == 64520 and round(lv) == 60680, (hv, lv)
    # Monday's moves, all from The Motley Fool, Nov. 23, 2026 (indexes at the close; bitcoin early evening).
    labels = ["Nasdaq Composite", "iShares Bitcoin Trust (IBIT)", "S&P 500", "Bitcoin"]
    vals = [6.51, 4.85, 4.73, 0.08]
    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=100)
    style_axes(ax, "Monday, Nov. 23: stocks soar, bitcoin stays flat (% change)")
    cols = ["#60a5fa", "#a78bfa", "#60a5fa", orange]
    ax.set_axisbelow(True)
    ax.barh(range(len(vals))[::-1], vals, color=cols, height=0.55, edgecolor="#0b1630")
    for i, v in enumerate(vals):
        ax.text(v + 0.08, len(vals) - 1 - i, f"+{v:.2f}%", va="center", color="#e2e8f0", fontsize=15, fontweight="bold")
    ax.set_yticks(range(len(vals))[::-1], labels)
    ax.tick_params(axis="y", labelsize=14, colors="#e2e8f0")
    ax.set_xlim(0, 7.6); ax.xaxis.set_major_formatter(lambda x, _p: f"{x:.0f}%")
    ax.grid(True, axis="x"); ax.grid(False, axis="y")
    plt.tight_layout(pad=1.2)
    fig.text(0.01, 0.01, "Indexes and IBIT at the close; bitcoin in the early evening. Source: The Motley Fool", color="#94a3b8", ha="left", fontsize=10)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor()); plt.close(fig); buf.seek(0)
    bars = save_image(Image.open(buf).convert("RGB"), d / "chart-monday-moves-nasdaq-vs-bitcoin")
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin on Kraken on Nov. 23, 2026, in Central time: flat near $61,200 overnight, a jump right after Nvidia reinstated Jensen Huang, a high of $64,520 around 8:15 a.m., an afternoon low of $60,680 and about $61,214 at 5:45 p.m.", {
            "es": "Gráfico de líneas de bitcoin en Kraken el 23 de noviembre de 2026, en hora del centro de EE. UU.: estable cerca de 61.200 dólares durante la noche, un salto justo después de que Nvidia restituyera a Jensen Huang, un máximo de 64.520 dólares hacia las 8:15, un mínimo de 60.680 dólares por la tarde y unos 61.214 dólares a las 17:45",
            "pt": "Gráfico de linha do bitcoin na Kraken em 23 de novembro de 2026, no horário central dos EUA: estável perto de US$ 61.200 durante a madrugada, um salto logo depois de a Nvidia reconduzir Jensen Huang, máxima de US$ 64.520 por volta das 8h15, mínima de US$ 60.680 à tarde e cerca de US$ 61.214 às 17h45",
            "fr": "Graphique en courbe du bitcoin sur Kraken le 23 novembre 2026, heure du Centre des États-Unis : stable vers 61 200 dollars pendant la nuit, un bond juste après le retour de Jensen Huang chez Nvidia, un plus haut de 64 520 dollars vers 8 h 15, un plus bas de 60 680 dollars l'après-midi et environ 61 214 dollars à 17 h 45",
            "de": "Liniendiagramm von Bitcoin bei Kraken am 23. November 2026, US-Zentralzeit: über Nacht stabil bei rund 61.200 $, ein Sprung direkt nach der Wiedereinsetzung von Jensen Huang bei Nvidia, ein Hoch von 64.520 $ gegen 8:15 Uhr, ein Tief von 60.680 $ am Nachmittag und rund 61.214 $ um 17:45 Uhr",
            "ru": "Линейный график биткоина на Kraken 23 ноября 2026 года по центральному времени США: ночью около $61 200, скачок сразу после того, как Nvidia вернула Дженсена Хуанга, максимум $64 520 около 8:15, дневной минимум $60 680 и около $61 214 в 17:45",
            "tr": "23 Kasım 2026'da Kraken'de bitcoinin ABD Merkez saatine göre çizgi grafiği: gece boyunca 61.200 $ civarında yatay, Nvidia'nın Jensen Huang'ı göreve iade etmesinin hemen ardından sıçrama, 08.15 civarında 64.520 $ zirve, öğleden sonra 60.680 $ dip ve 17.45'te yaklaşık 61.214 $",
            "id": "Grafik garis bitcoin di Kraken pada 23 November 2026, waktu Central AS: datar di sekitar US$61.200 sepanjang malam, melonjak tepat setelah Nvidia mengangkat kembali Jensen Huang, puncak US$64.520 sekitar pukul 08.15, titik terendah sore US$60.680, dan sekitar US$61.214 pukul 17.45",
            "ja": "2026年11月23日のクラーケンにおけるビットコインの折れ線グラフ（米中部時間）：夜間は約61,200ドルで横ばい、エヌビディアがジェンスン・フアン氏の復帰を発表した直後に急騰、午前8時15分ごろに高値64,520ドル、午後に安値60,680ドル、午後5時45分は約61,214ドル",
            "ko": "2026년 11월 23일 크라켄 비트코인 선 차트(미국 중부시간): 밤사이 약 61,200달러에서 횡보, 엔비디아가 젠슨 황을 복귀시킨 직후 급등, 오전 8시 15분경 고점 64,520달러, 오후 저점 60,680달러, 오후 5시 45분 약 61,214달러",
         }),
         "caption": tr_map(CAPTION_CHART, src="Kraken")},
        {"id": "moves", "file": bars.name, "w": 1200, "h": 630, "kind": "chart",
         "alt": alts("Bar chart of Monday, Nov. 23, 2026 moves: Nasdaq Composite +6.51%, iShares Bitcoin Trust (IBIT) +4.85%, S&P 500 +4.73%, bitcoin +0.08%", {
            "es": "Gráfico de barras de los movimientos del lunes 23 de noviembre de 2026: Nasdaq Composite +6,51%, iShares Bitcoin Trust (IBIT) +4,85%, S&P 500 +4,73%, bitcoin +0,08%",
            "pt": "Gráfico de barras das variações de segunda-feira, 23 de novembro de 2026: Nasdaq Composite +6,51%, iShares Bitcoin Trust (IBIT) +4,85%, S&P 500 +4,73%, bitcoin +0,08%",
            "fr": "Graphique en barres des variations du lundi 23 novembre 2026 : Nasdaq Composite +6,51 %, iShares Bitcoin Trust (IBIT) +4,85 %, S&P 500 +4,73 %, bitcoin +0,08 %",
            "de": "Balkendiagramm der Bewegungen am Montag, 23. November 2026: Nasdaq Composite +6,51 %, iShares Bitcoin Trust (IBIT) +4,85 %, S&P 500 +4,73 %, Bitcoin +0,08 %",
            "ru": "Столбчатая диаграмма изменений в понедельник, 23 ноября 2026 года: Nasdaq Composite +6,51%, iShares Bitcoin Trust (IBIT) +4,85%, S&P 500 +4,73%, биткоин +0,08%",
            "tr": "23 Kasım 2026 Pazartesi günkü değişimlerin çubuk grafiği: Nasdaq Composite +%6,51, iShares Bitcoin Trust (IBIT) +%4,85, S&P 500 +%4,73, bitcoin +%0,08",
            "id": "Grafik batang pergerakan Senin, 23 November 2026: Nasdaq Composite +6,51%, iShares Bitcoin Trust (IBIT) +4,85%, S&P 500 +4,73%, bitcoin +0,08%",
            "ja": "2026年11月23日（月）の騰落率の棒グラフ：ナスダック総合指数+6.51%、iシェアーズ・ビットコイン・トラスト（IBIT）+4.85%、S&P500+4.73%、ビットコイン+0.08%",
            "ko": "2026년 11월 23일(월) 등락률 막대 차트: 나스닥 종합지수 +6.51%, 아이셰어즈 비트코인 트러스트(IBIT) +4.85%, S&P 500 +4.73%, 비트코인 +0.08%",
         }),
         "caption": tr_map(CAPTION_CHART, src="The Motley Fool")},
    ]


def build_cftc_crypto_reserves():
    slug = "cftc-staff-bitcoin-ether-stablecoins-count-toward-exchange-reserves-nov-2026"
    d = OUT / slug
    fact = make_fact_card(
        d / "fact-cftc-20-percent-haircut-bitcoin-ether",
        "CFTC staff advisory · Nov. 23, 2026",
        "20% / 2% haircuts",
        "Minimum discount when bitcoin and ether (20%) or payment stablecoins (2%) count toward a year of operating reserves",
        footer="CFTC Letter No. 26-31 · Release 9331-26",
    )
    # Reserve structure from CFTC Letter No. 26-31 (17 CFR 37.1303, 38.1101(e), 39.11(e)(2)).
    orange = f"#{ORANGE[0]:02x}{ORANGE[1]:02x}{ORANGE[2]:02x}"
    rows = [("Clearinghouses (DCOs)", 6), ("Futures exchanges (DCMs)", 6), ("Swap facilities (SEFs)", 3)]
    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=100)
    style_axes(ax, "12 months of operating costs: where bitcoin, ether and stablecoins can count")
    ax.set_axisbelow(True)
    for i, (lab, liq) in enumerate(rows):
        ax.barh(i, liq, color="#64748b", height=0.55, edgecolor="#0b1630")
        ax.barh(i, 12 - liq, left=liq, color=orange, height=0.55, edgecolor="#0b1630")
        ax.text(liq / 2, i, f"at least {liq} mo.\ncash / liquid", ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        ax.text(liq + (12 - liq) / 2, i, f"up to {12 - liq} mo. may include\ncrypto after haircuts", ha="center", va="center", color="#0b1630", fontsize=12, fontweight="bold")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.tick_params(axis="y", labelsize=13, colors="#e2e8f0")
    ax.set_xlim(0, 12); ax.set_xticks(range(0, 13, 3)); ax.xaxis.set_major_formatter(lambda x, _p: f"{x:.0f} mo.")
    ax.grid(True, axis="x"); ax.grid(False, axis="y")
    plt.tight_layout(pad=1.2)
    fig.text(0.01, 0.01, "SEF cash cushion: 3 months or wind-down costs, whichever is greater. Source: CFTC Letter No. 26-31", color="#94a3b8", ha="left", fontsize=10)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor()); plt.close(fig); buf.seek(0)
    res = save_image(Image.open(buf).convert("RGB"), d / "chart-cftc-reserve-where-crypto-counts")
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: CFTC staff advisory, Nov. 23, 2026. Haircuts of at least 20% for bitcoin and ether and 2% for payment stablecoins when they count toward a year of operating reserves", {
            "es": "Tarjeta: aviso del personal de la CFTC, 23 de noviembre de 2026. Descuentos de al menos el 20% para bitcoin y ether y del 2% para las stablecoins de pago cuando cuentan para un año de reservas operativas",
            "pt": "Cartão: comunicado da equipe da CFTC, 23 de novembro de 2026. Descontos de pelo menos 20% para bitcoin e ether e de 2% para stablecoins de pagamento quando contam para um ano de reservas operacionais",
            "fr": "Fiche : avis des services de la CFTC, 23 novembre 2026. Décotes d'au moins 20 % pour le bitcoin et l'ether et de 2 % pour les stablecoins de paiement lorsqu'ils comptent dans une année de réserves de fonctionnement",
            "de": "Faktenkarte: Hinweis der CFTC-Mitarbeiter vom 23. November 2026. Abschläge von mindestens 20 % für Bitcoin und Ether und 2 % für Zahlungs-Stablecoins, wenn sie auf ein Jahr Betriebsreserven angerechnet werden",
            "ru": "Карточка: разъяснение сотрудников CFTC от 23 ноября 2026 года. Дисконт не менее 20% для биткоина и эфира и 2% для платёжных стейблкоинов, когда они засчитываются в годовой резерв на операционные расходы",
            "tr": "Bilgi kartı: CFTC personel duyurusu, 23 Kasım 2026. Bitcoin ve ether bir yıllık işletme rezervine sayıldığında en az %20, ödeme stablecoin'leri için %2 kesinti",
            "id": "Kartu fakta: imbauan staf CFTC, 23 November 2026. Potongan nilai minimal 20% untuk bitcoin dan ether serta 2% untuk stablecoin pembayaran saat dihitung sebagai cadangan operasional satu tahun",
            "ja": "ファクトカード：CFTCスタッフ勧告（2026年11月23日）。ビットコインとイーサは最低20%、決済用ステーブルコインは2%のヘアカットを適用して1年分の運営資金に算入できる",
            "ko": "팩트 카드: CFTC 실무진 권고(2026년 11월 23일). 비트코인과 이더는 최소 20%, 결제용 스테이블코인은 2%의 헤어컷을 적용해 1년치 운영 준비금에 산입 가능",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CFTC Letter No. 26-31, Nov. 23, 2026")},
        {"id": "reserve", "file": res.name, "w": 1200, "h": 630, "kind": "chart",
         "alt": alts("Diagram of the 12-month operating reserve: clearinghouses and futures exchanges must keep at least 6 months in cash or highly liquid securities and swap facilities at least 3 months; only the rest may include bitcoin, ether and payment stablecoins after haircuts", {
            "es": "Diagrama de la reserva operativa de 12 meses: las cámaras de compensación y los mercados de futuros deben mantener al menos 6 meses en efectivo o valores muy líquidos y las plataformas de swaps al menos 3 meses; solo el resto puede incluir bitcoin, ether y stablecoins de pago tras los descuentos",
            "pt": "Diagrama da reserva operacional de 12 meses: câmaras de compensação e bolsas de futuros devem manter pelo menos 6 meses em dinheiro ou títulos de alta liquidez e plataformas de swaps pelo menos 3 meses; só o restante pode incluir bitcoin, ether e stablecoins de pagamento após os descontos",
            "fr": "Schéma de la réserve de fonctionnement de 12 mois : les chambres de compensation et les marchés à terme doivent garder au moins 6 mois en liquidités ou titres très liquides, les plateformes de swaps au moins 3 mois ; seul le reste peut inclure du bitcoin, de l'ether et des stablecoins de paiement après décote",
            "de": "Diagramm der 12-monatigen Betriebsreserve: Clearinghäuser und Terminbörsen müssen mindestens 6 Monate in Bargeld oder hochliquiden Wertpapieren halten, Swap-Handelsplattformen mindestens 3 Monate; nur der Rest darf nach Abschlägen Bitcoin, Ether und Zahlungs-Stablecoins enthalten",
            "ru": "Схема годового резерва на операционные расходы: клиринговые палаты и фьючерсные биржи должны держать не менее 6 месяцев в деньгах или высоколиквидных бумагах, своп-площадки не менее 3 месяцев; только остаток может включать биткоин, эфир и платёжные стейблкоины с дисконтом",
            "tr": "12 aylık işletme rezervi şeması: takas kuruluşları ve vadeli işlem borsaları en az 6 aylık tutarı nakit veya yüksek likiditeli menkul kıymetlerde, swap platformları en az 3 aylık tutarı tutmalı; yalnızca kalan kısım kesintilerden sonra bitcoin, ether ve ödeme stablecoin'i içerebilir",
            "id": "Diagram cadangan operasional 12 bulan: lembaga kliring dan bursa berjangka wajib menyimpan minimal 6 bulan dalam kas atau sekuritas sangat likuid, fasilitas swap minimal 3 bulan; hanya sisanya yang boleh berisi bitcoin, ether, dan stablecoin pembayaran setelah potongan nilai",
            "ja": "12か月分の運営資金の図：清算機関と先物取引所は少なくとも6か月分、スワップ執行施設は少なくとも3か月分を現金または流動性の高い証券で保有する必要があり、残りの部分にのみヘアカット後のビットコイン、イーサ、決済用ステーブルコインを含められる",
            "ko": "12개월 운영 준비금 도식: 청산소와 선물거래소는 최소 6개월분, 스와프 거래 플랫폼은 최소 3개월분을 현금이나 고유동성 증권으로 보유해야 하며, 나머지만 헤어컷 적용 후 비트코인, 이더, 결제용 스테이블코인을 포함할 수 있다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="CFTC Letter No. 26-31")},
    ]


def build_etf_nov_record_471():
    slug = "bitcoin-etfs-record-4-71-billion-november-outflows-nov-2026"
    d = OUT / slug
    # Monthly sums of Farside's daily "Total" column (US$m), Jan - Nov 23, 2026, frozen in chart-data.json (read Nov 24, 2026).
    data = json.loads((I18N / slug / "chart-data.json").read_text(encoding="utf-8"))
    labels = [m[0] for m in data["months"]]; labels[-1] = "Nov*"
    vals = [m[1] for m in data["months"]]
    assert round(vals[-1]) == -4707 and round(vals[5]) == -4510, vals
    cols = ["#34d399" if v > 0 else "#f87171" for v in vals]
    cols[-1] = "#dc2626"
    chart = make_bar_chart(
        d / "chart-btc-etf-monthly-flows-2026",
        labels, vals,
        title="U.S. spot bitcoin ETFs: monthly net flows in 2026 (US$ millions, *Nov. through Nov. 23)",
        colors=cols,
        value_fmt=lambda v: (f"+{v/1000:,.2f}B" if v > 0 else f"-{-v/1000:,.2f}B") if abs(v) >= 1000 else (f"+{v:,.0f}M" if v > 0 else f"-{-v:,.0f}M"),
        axis_fmt=lambda x, _p: f"${x:,.0f}M",
    )
    fact = make_fact_card(
        d / "fact-november-4-71-billion-record-outflow",
        "U.S. spot bitcoin ETFs · Nov. 1-23, 2026",
        "-$4.71 billion",
        "Largest monthly net outflow since the funds launched in January 2024, ahead of June 2026 (-$4.51 billion)",
        footer="Farside Investors, daily flows since Jan. 2024 (PlainBTC count)",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of monthly net flows into U.S. spot bitcoin ETFs in 2026: outflows of $1.60B in January, $0.21B in February, $2.41B in May, $4.51B in June and $0.52B in October, inflows in March, April, July, August and September, and a record $4.71B outflow in November through Nov. 23", {
            "es": "Gráfico de barras de los flujos netos mensuales de los ETF de bitcoin al contado de EE. UU. en 2026: salidas de 1.600 M$ en enero, 210 M$ en febrero, 2.410 M$ en mayo, 4.510 M$ en junio y 520 M$ en octubre, entradas en marzo, abril, julio, agosto y septiembre, y una salida récord de 4.710 M$ en noviembre hasta el día 23",
            "pt": "Gráfico de barras dos fluxos líquidos mensais dos ETFs de bitcoin à vista dos EUA em 2026: saídas de US$ 1,60 bi em janeiro, US$ 0,21 bi em fevereiro, US$ 2,41 bi em maio, US$ 4,51 bi em junho e US$ 0,52 bi em outubro, entradas em março, abril, julho, agosto e setembro, e saída recorde de US$ 4,71 bi em novembro até o dia 23",
            "fr": "Graphique en barres des flux nets mensuels des ETF bitcoin au comptant américains en 2026 : sorties de 1,60 Md$ en janvier, 0,21 Md$ en février, 2,41 Md$ en mai, 4,51 Md$ en juin et 0,52 Md$ en octobre, entrées en mars, avril, juillet, août et septembre, et sortie record de 4,71 Md$ en novembre jusqu'au 23",
            "de": "Balkendiagramm der monatlichen Nettozuflüsse der US-Spot-Bitcoin-ETFs 2026: Abflüsse von 1,60 Mrd. $ im Januar, 0,21 Mrd. $ im Februar, 2,41 Mrd. $ im Mai, 4,51 Mrd. $ im Juni und 0,52 Mrd. $ im Oktober, Zuflüsse im März, April, Juli, August und September und ein Rekordabfluss von 4,71 Mrd. $ im November bis zum 23.",
            "ru": "Столбчатая диаграмма месячных чистых потоков американских спотовых биткоин-ETF в 2026 году: отток $1,60 млрд в январе, $0,21 млрд в феврале, $2,41 млрд в мае, $4,51 млрд в июне и $0,52 млрд в октябре, приток в марте, апреле, июле, августе и сентябре и рекордный отток $4,71 млрд в ноябре по 23-е число",
            "tr": "ABD spot bitcoin ETF'lerinin 2026'daki aylık net akışlarının çubuk grafiği: ocakta 1,60 milyar $, şubatta 0,21 milyar $, mayısta 2,41 milyar $, haziranda 4,51 milyar $ ve ekimde 0,52 milyar $ çıkış; mart, nisan, temmuz, ağustos ve eylülde giriş; kasımda 23'üne kadar rekor 4,71 milyar $ çıkış",
            "id": "Grafik batang arus bersih bulanan ETF bitcoin spot AS pada 2026: arus keluar US$1,60 miliar pada Januari, US$0,21 miliar pada Februari, US$2,41 miliar pada Mei, US$4,51 miliar pada Juni, dan US$0,52 miliar pada Oktober, arus masuk pada Maret, April, Juli, Agustus, dan September, serta arus keluar rekor US$4,71 miliar pada November hingga tanggal 23",
            "ja": "2026年の米国ビットコイン現物ETFの月間純フローの棒グラフ：1月16億ドル、2月2.1億ドル、5月24.1億ドル、6月45.1億ドル、10月5.2億ドルの流出、3月・4月・7月・8月・9月は流入、11月は23日までで過去最大の47.1億ドルの流出",
            "ko": "2026년 미국 비트코인 현물 ETF 월간 순유출입 막대그래프: 1월 16억 달러, 2월 2.1억 달러, 5월 24.1억 달러, 6월 45.1억 달러, 10월 5.2억 달러 유출, 3월·4월·7월·8월·9월 유입, 11월은 23일까지 사상 최대 47.1억 달러 유출",
         }),
         "caption": tr_map(CAPTION_CHART, src="Farside Investors")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: U.S. spot bitcoin ETFs lost a net $4.71 billion from Nov. 1 to Nov. 23, 2026, the largest monthly outflow since their January 2024 launch, ahead of June 2026's $4.51 billion", {
            "es": "Tarjeta: los ETF de bitcoin al contado de EE. UU. perdieron en neto 4.710 millones de dólares del 1 al 23 de noviembre de 2026, la mayor salida mensual desde su lanzamiento en enero de 2024, por delante de los 4.510 millones de junio de 2026",
            "pt": "Cartão: os ETFs de bitcoin à vista dos EUA perderam em termos líquidos US$ 4,71 bilhões de 1º a 23 de novembro de 2026, a maior saída mensal desde o lançamento em janeiro de 2024, acima dos US$ 4,51 bilhões de junho de 2026",
            "fr": "Fiche : les ETF bitcoin au comptant américains ont perdu en net 4,71 milliards de dollars du 1er au 23 novembre 2026, la plus forte sortie mensuelle depuis leur lancement en janvier 2024, devant les 4,51 milliards de juin 2026",
            "de": "Faktenkarte: US-Spot-Bitcoin-ETFs verloren vom 1. bis 23. November 2026 netto 4,71 Mrd. Dollar, der größte Monatsabfluss seit ihrem Start im Januar 2024, vor den 4,51 Mrd. Dollar im Juni 2026",
            "ru": "Карточка: американские спотовые биткоин-ETF потеряли в чистом выражении $4,71 млрд с 1 по 23 ноября 2026 года, это крупнейший месячный отток с их запуска в январе 2024 года, больше $4,51 млрд в июне 2026 года",
            "tr": "Bilgi kartı: ABD spot bitcoin ETF'leri 1-23 Kasım 2026 arasında net 4,71 milyar dolar kaybetti; bu, Ocak 2024'teki lansmanlarından bu yana en büyük aylık çıkış ve Haziran 2026'daki 4,51 milyar doları geride bıraktı",
            "id": "Kartu fakta: ETF bitcoin spot AS kehilangan bersih US$4,71 miliar pada 1-23 November 2026, arus keluar bulanan terbesar sejak diluncurkan pada Januari 2024, melampaui US$4,51 miliar pada Juni 2026",
            "ja": "ファクトカード：米国ビットコイン現物ETFは2026年11月1日から23日に差し引き47.1億ドルを失った。2024年1月の上場以来最大の月間流出で、2026年6月の45.1億ドルを上回る",
            "ko": "팩트 카드: 미국 비트코인 현물 ETF는 2026년 11월 1~23일 순 47.1억 달러가 빠져나갔다. 2024년 1월 출시 이후 최대 월간 유출로, 2026년 6월의 45.1억 달러를 넘어섰다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Farside Investors")},
    ]


def build_korea_digital_asset_bill():
    slug = "south-korea-crypto-bill-bank-led-stablecoins-ico-20-percent-exchange-cap-nov-2026"
    d = OUT / slug
    fact = make_fact_card(
        d / "fact-korea-banks-more-than-50-percent-stablecoin",
        "South Korea FSC draft bill · Nov. 24, 2026",
        "Banks > 50%",
        "Won stablecoins would first come only from consortia majority-owned by banks; a fintech firm can still be the top shareholder",
        footer="Financial Services Commission press release · Yonhap",
    )
    cmp_ = make_compare_card(
        d / "compare-korea-stablecoin-issuers-vs-exchanges",
        "South Korea's draft digital asset law",
        "Stablecoin issuers",
        "Crypto exchanges",
        [
            ("Owners", "Banks together own more than 50%", "Top holder capped at 20% (34% with FSC OK)"),
            ("Rules", "5 billion won capital, 100% reserves, no interest", "Licenses for trading, brokerage and custody"),
            ("If hacked", "Reserves kept apart and paid to holders first", "Firms repay users even without fault"),
        ],
        footer="FSC press release, Nov. 24, 2026 · needs National Assembly approval",
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: under South Korea's draft digital asset bill of Nov. 24, 2026, won stablecoins would first come only from consortia in which banks own more than 50%, while a fintech firm can still be the largest shareholder", {
            "es": "Tarjeta: según el proyecto de ley de activos digitales de Corea del Sur del 24 de noviembre de 2026, las stablecoins en wones solo podrían emitirlas al principio consorcios con más del 50% en manos de bancos, aunque una fintech puede ser el mayor accionista",
            "pt": "Cartão: pelo projeto de lei de ativos digitais da Coreia do Sul de 24 de novembro de 2026, stablecoins em won só poderiam ser emitidas no início por consórcios com mais de 50% nas mãos de bancos, embora uma fintech possa ser a maior acionista",
            "fr": "Fiche : selon le projet de loi sud-coréen sur les actifs numériques du 24 novembre 2026, les stablecoins en wons ne pourraient d'abord être émis que par des consortiums détenus à plus de 50 % par des banques, une fintech pouvant rester premier actionnaire",
            "de": "Faktenkarte: Nach Südkoreas Gesetzentwurf für digitale Vermögenswerte vom 24. November 2026 dürften Won-Stablecoins zunächst nur Konsortien ausgeben, die zu mehr als 50 % Banken gehören; ein Fintech kann dennoch größter Einzelaktionär sein",
            "ru": "Карточка: по законопроекту Южной Кореи о цифровых активах от 24 ноября 2026 года стейблкоины в вонах сначала смогут выпускать только консорциумы, где банкам принадлежит более 50%, при этом финтех-компания может быть крупнейшим акционером",
            "tr": "Bilgi kartı: Güney Kore'nin 24 Kasım 2026 tarihli dijital varlık yasa tasarısına göre won stablecoin'lerini ilk aşamada yalnızca bankaların yüzde 50'den fazlasına sahip olduğu konsorsiyumlar çıkarabilecek; bir fintek yine de en büyük hissedar olabilir",
            "id": "Kartu fakta: menurut RUU aset digital Korea Selatan tanggal 24 November 2026, stablecoin won awalnya hanya boleh diterbitkan konsorsium yang lebih dari 50% dimiliki bank, meski perusahaan fintech tetap bisa menjadi pemegang saham terbesar",
            "ja": "ファクトカード：2026年11月24日の韓国デジタル資産法案では、ウォン建てステーブルコインは当初、銀行が合計50%超を保有するコンソーシアムのみが発行でき、フィンテック企業も筆頭株主になれる",
            "ko": "팩트 카드: 2026년 11월 24일 한국 디지털자산법안에 따르면 원화 스테이블코인은 초기에 은행이 과반 지분을 보유한 컨소시엄만 발행할 수 있으며, 핀테크 기업도 최대주주로 참여할 수 있다",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Financial Services Commission (Korea), Nov. 24, 2026")},
        {"id": "compare", "file": cmp_.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Comparison card of South Korea's draft digital asset law: stablecoin issuers need banks to own more than 50%, 5 billion won in capital, 100% reserves and no interest, with reserves paid to holders first; exchanges face a 20% cap per shareholder (34% with approval), three licenses and liability for hacks even without fault", {
            "es": "Tarjeta comparativa del proyecto de ley de activos digitales de Corea del Sur: los emisores de stablecoins necesitan más del 50% en manos de bancos, 5.000 millones de wones de capital, reservas del 100% y sin intereses, con las reservas pagadas primero a los tenedores; los exchanges tienen un tope del 20% por accionista (34% con aprobación), tres licencias y responsabilidad por hackeos aun sin culpa",
            "pt": "Cartão comparativo do projeto de lei de ativos digitais da Coreia do Sul: emissores de stablecoins precisam de mais de 50% nas mãos de bancos, 5 bilhões de wons de capital, reservas de 100% e nada de juros, com as reservas pagas primeiro aos detentores; corretoras têm limite de 20% por acionista (34% com aprovação), três licenças e responsabilidade por ataques mesmo sem culpa",
            "fr": "Fiche comparative du projet de loi sud-coréen sur les actifs numériques : les émetteurs de stablecoins doivent être détenus à plus de 50 % par des banques, avoir 5 milliards de wons de capital, 100 % de réserves et ne verser aucun intérêt, les réserves revenant d'abord aux détenteurs ; les plateformes d'échange ont un plafond de 20 % par actionnaire (34 % avec accord), trois licences et une responsabilité en cas de piratage même sans faute",
            "de": "Vergleichskarte zu Südkoreas Gesetzentwurf für digitale Vermögenswerte: Stablecoin-Emittenten brauchen Banken mit mehr als 50 %, 5 Mrd. Won Kapital, 100 % Reserven und dürfen keine Zinsen zahlen, die Reserven gehen zuerst an die Inhaber; Börsen haben eine Obergrenze von 20 % je Aktionär (34 % mit Genehmigung), drei Lizenzen und haften bei Hacks auch ohne Verschulden",
            "ru": "Сравнительная карточка законопроекта Южной Кореи о цифровых активах: эмитентам стейблкоинов нужны банки с долей более 50%, капитал 5 млрд вон, резервы 100% и запрет на проценты, а резервы в первую очередь идут держателям; для бирж лимит 20% на акционера (34% с одобрения), три лицензии и ответственность за взломы даже без вины",
            "tr": "Güney Kore'nin dijital varlık yasa tasarısı karşılaştırma kartı: stablecoin ihraççılarında bankaların payı yüzde 50'den fazla olmalı, 5 milyar won sermaye, yüzde 100 rezerv ve faiz yok, rezervler önce sahiplere ödenir; borsalarda hissedar başına yüzde 20 sınır (onayla yüzde 34), üç lisans ve kusur olmasa bile hack sorumluluğu",
            "id": "Kartu perbandingan RUU aset digital Korea Selatan: penerbit stablecoin harus lebih dari 50% dimiliki bank, bermodal 5 miliar won, cadangan 100%, dan tanpa bunga, dengan cadangan dibayarkan lebih dulu ke pemegang; bursa kripto dibatasi 20% per pemegang saham (34% dengan persetujuan), tiga izin, dan tanggung jawab atas peretasan meski tanpa kesalahan",
            "ja": "韓国デジタル資産法案の比較カード：ステーブルコイン発行体は銀行の合計持ち分50%超、資本金50億ウォン、100%の準備資産、利息支払い禁止で、準備資産は保有者に優先して支払われる。取引所は株主1人あたり20%（承認で34%）の上限、3つの認可、過失がなくてもハッキング時の賠償責任",
            "ko": "한국 디지털자산법안 비교 카드: 스테이블코인 발행사는 은행 과반 지분, 자기자본 50억 원, 100% 준비자산, 이자 지급 금지이며 준비자산은 보유자에게 우선 지급된다. 거래소는 주주당 20% 상한(승인 시 34%), 3개 인가, 무과실 해킹 배상책임",
         }),
         "caption": tr_map(CAPTION_SOURCE, src="Financial Services Commission (Korea), Nov. 24, 2026")},
    ]


def build_krak_credit_cards():
    slug = "kraken-krak-credit-cards-4-percent-bitcoin-cashback-usdc-secured-nov-2026"
    d = OUT / slug
    fact = make_fact_card(
        d / "fact-krak-up-to-4-percent-cashback",
        "Krak U.S. credit cards · waitlist Nov. 24, 2026",
        "Up to 4%",
        "Cashback in U.S. dollars or bitcoin on the Krak Credit Card and Krak Secured Card, expected to ship in early 2027",
        footer="Payward statement via The Block · APR and fees not yet disclosed",
    )
    cmp_ = make_compare_card(
        d / "compare-krak-credit-vs-secured-card",
        "Krak's planned U.S. cards: both pay up to 4% cashback",
        "Krak Credit Card",
        "Krak Secured Card",
        [
            ("Made for", "People with established credit", "People building or rebuilding credit"),
            ("Backing", "Regular credit line", "$350 to $5,000 USDC deposit"),
            ("Needs", "Krakpass: $6.29/month, billed yearly", "Krakpass; USDC can earn up to 4% APY"),
        ],
        footer="Payward via The Block, Nov. 24, 2026 · ships early 2027",
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: Krak's planned U.S. credit cards, announced with a waitlist on Nov. 24, 2026, offer up to 4% cashback in U.S. dollars or bitcoin and are expected to ship in early 2027; APR and fees are not yet disclosed", KRAK_FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Payward statement via The Block, Nov. 24, 2026")},
        {"id": "compare", "file": cmp_.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Comparison card of Krak's two planned U.S. credit cards: the Krak Credit Card is for people with established credit and uses a regular credit line; the Krak Secured Card is for people building or rebuilding credit and is backed by a $350 to $5,000 USDC deposit; both pay up to 4% cashback in dollars or bitcoin and require Krakpass at $6.29 a month billed yearly", KRAK_CMP_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Payward statement via The Block, Nov. 24, 2026")},
    ]

KRAK_FACT_ALTS = {
 "es": "Tarjeta: las tarjetas de crédito de Krak para EE. UU., con lista de espera abierta el 24 de noviembre de 2026, ofrecen hasta un 4% de reembolso en dólares o en bitcoin y deberían enviarse a principios de 2027; la TAE y las comisiones aún no se han publicado",
 "pt": "Cartão: os cartões de crédito da Krak para os EUA, com lista de espera aberta em 24 de novembro de 2026, oferecem até 4% de cashback em dólares ou em bitcoin e devem ser enviados no início de 2027; juros e tarifas ainda não foram divulgados",
 "fr": "Fiche : les cartes de crédit américaines de Krak, dont la liste d'attente a ouvert le 24 novembre 2026, offrent jusqu'à 4 % de cashback en dollars ou en bitcoin et doivent être expédiées début 2027 ; le taux d'intérêt et les frais ne sont pas encore publiés",
 "de": "Faktenkarte: Die geplanten US-Kreditkarten von Krak, Warteliste seit 24. November 2026, bieten bis zu 4 % Cashback in US-Dollar oder Bitcoin und sollen Anfang 2027 verschickt werden; Zinssatz und Gebühren sind noch nicht veröffentlicht",
 "ru": "Карточка: кредитные карты Krak для США, лист ожидания открыт 24 ноября 2026 года, дают до 4% кэшбэка в долларах или биткоинах, рассылка ожидается в начале 2027 года; ставка и комиссии пока не раскрыты",
 "tr": "Bilgi kartı: Krak'ın ABD için planladığı kredi kartları, bekleme listesi 24 Kasım 2026'da açıldı, dolar veya bitcoin olarak yüzde 4'e kadar nakit iade sunuyor ve 2027 başında gönderilmesi bekleniyor; faiz oranı ve ücretler henüz açıklanmadı",
 "id": "Kartu fakta: kartu kredit Krak untuk AS, daftar tunggu dibuka 24 November 2026, menawarkan cashback hingga 4% dalam dolar AS atau bitcoin dan diperkirakan dikirim awal 2027; bunga dan biaya belum diumumkan",
 "ja": "ファクトカード：2026年11月24日にウェイトリストを開始したKrakの米国向けクレジットカードは、米ドルまたはビットコインで最大4%のキャッシュバックを提供し、2027年初めに発送予定。金利と手数料は未公表",
 "ko": "팩트 카드: 2026년 11월 24일 대기자 명단을 연 Krak의 미국 신용카드는 미국 달러 또는 비트코인으로 최대 4% 캐시백을 제공하며 2027년 초 발송 예정이다. 금리와 수수료는 아직 공개되지 않았다"
}
KRAK_CMP_ALTS = {
 "es": "Tarjeta comparativa de las dos tarjetas de crédito previstas por Krak en EE. UU.: la Krak Credit Card es para personas con historial crediticio y usa una línea de crédito normal; la Krak Secured Card es para quien construye o reconstruye su crédito y está respaldada por un depósito de 350 a 5.000 dólares en USDC; ambas pagan hasta un 4% en dólares o bitcoin y requieren Krakpass a 6,29 dólares al mes con pago anual",
 "pt": "Cartão comparativo dos dois cartões de crédito planejados pela Krak nos EUA: o Krak Credit Card é para quem já tem histórico de crédito e usa uma linha de crédito comum; o Krak Secured Card é para quem está construindo ou reconstruindo o crédito e é garantido por um depósito de 350 a 5.000 dólares em USDC; ambos pagam até 4% em dólares ou bitcoin e exigem Krakpass a 6,29 dólares por mês no plano anual",
 "fr": "Fiche comparative des deux cartes de crédit prévues par Krak aux États-Unis : la Krak Credit Card s'adresse aux personnes ayant déjà un historique de crédit et utilise une ligne de crédit classique ; la Krak Secured Card vise ceux qui construisent ou reconstruisent leur crédit et est garantie par un dépôt de 350 à 5 000 dollars en USDC ; les deux versent jusqu'à 4 % en dollars ou en bitcoin et exigent Krakpass à 6,29 dollars par mois en formule annuelle",
 "de": "Vergleichskarte der zwei geplanten US-Kreditkarten von Krak: Die Krak Credit Card richtet sich an Menschen mit Kredithistorie und nutzt einen normalen Kreditrahmen; die Krak Secured Card ist für den Auf- oder Wiederaufbau der Bonität gedacht und durch eine USDC-Einlage von 350 bis 5.000 US-Dollar gedeckt; beide zahlen bis zu 4 % in Dollar oder Bitcoin und erfordern Krakpass für 6,29 US-Dollar im Monat bei jährlicher Zahlung",
 "ru": "Сравнительная карточка двух кредитных карт Krak для США: Krak Credit Card для людей с кредитной историей и обычным кредитным лимитом; Krak Secured Card для тех, кто создаёт или восстанавливает кредитную историю, обеспечена депозитом от 350 до 5000 долларов в USDC; обе дают до 4% в долларах или биткоинах и требуют Krakpass за 6,29 доллара в месяц при оплате за год",
 "tr": "Krak'ın ABD için planladığı iki kredi kartının karşılaştırma kartı: Krak Credit Card kredi geçmişi olanlar için normal bir kredi limitiyle; Krak Secured Card kredi geçmişi oluşturan veya onaran kişiler için 350 ile 5.000 dolar arası USDC teminatıyla; ikisi de dolar veya bitcoin olarak yüzde 4'e kadar iade öder ve yıllık ödemede aylık 6,29 dolarlık Krakpass gerektirir",
 "id": "Kartu perbandingan dua kartu kredit Krak yang direncanakan di AS: Krak Credit Card untuk orang yang sudah punya riwayat kredit dengan limit kredit biasa; Krak Secured Card untuk yang sedang membangun atau memperbaiki kredit dan dijamin deposit USDC 350 sampai 5.000 dolar; keduanya memberi hingga 4% dalam dolar atau bitcoin dan mewajibkan Krakpass seharga 6,29 dolar per bulan jika dibayar tahunan",
 "ja": "Krakが米国で予定する2種類のクレジットカードの比較カード：Krak Credit Cardは信用履歴がある人向けで通常の与信枠、Krak Secured Cardは信用を築く・立て直す人向けで350〜5,000ドルのUSDC預け入れが担保。どちらもドルまたはビットコインで最大4%を還元し、年払いで月6.29ドルのKrakpassが必要",
 "ko": "Krak이 미국에서 준비 중인 신용카드 2종 비교 카드: Krak Credit Card는 신용 이력이 있는 사람을 위한 일반 신용한도 카드, Krak Secured Card는 신용을 쌓거나 회복하려는 사람을 위한 카드로 350~5,000달러의 USDC 예치금이 담보다. 두 카드 모두 달러 또는 비트코인으로 최대 4%를 돌려주며 연간 결제 시 월 6.29달러의 Krakpass가 필요하다"
}



# --- Nov 24, 2026 evening run: Fidelity DeFi tokens, Coldcard postmortem -------------------------
FID_SLUG = "fidelity-crypto-adds-aave-link-uni-nov-2026"
COLD_SLUG = "coldcard-postmortem-weak-seeds-bitcoin-thefts-nov-2026"


def make_multi_pct_chart(path: Path, series, title: str, w=1200, h=675) -> Path:
    """Percent change from the first close for several assets (frozen Kraken data)."""
    import datetime as dt
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    style_axes(ax, title)
    for label, pts, col in series:
        base = pts[0][1]
        dts = [dt.datetime.fromtimestamp(t, dt.UTC) for t, _ in pts]
        ys = [(v / base - 1) * 100 for _, v in pts]
        ax.plot(dts, ys, color=col, linewidth=2.4, label=f"{label}  {ys[-1]:+.0f}%")
        ax.text(dts[-1], ys[-1], f"  {ys[-1]:+.0f}%", color=col, fontsize=12, fontweight="bold", va="center")
    ax.axhline(0, color="#475569", linewidth=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.yaxis.set_major_formatter(lambda x, _p: f"{x:+.0f}%")
    leg = ax.legend(loc="lower left", frameon=False, fontsize=12)
    for t in leg.get_texts():
        t.set_color("#e2e8f0")
    ax.margins(x=0.08)
    plt.tight_layout(pad=1.2)
    fig.text(0.99, 0.01, "plainbtc.com", color="#64748b", ha="right", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return save_image(Image.open(buf).convert("RGB"), path)


def build_fidelity_defi_tokens():
    d = OUT / FID_SLUG
    data = json.loads((I18N / FID_SLUG / "chart-data.json").read_text(encoding="utf-8"))["series"]
    chart = make_multi_pct_chart(
        d / "chart-aave-link-uni-since-oct-25",
        [("AAVE", data["AAVEUSD"], "#9896ff"), ("LINK", data["LINKUSD"], "#375bd2"), ("UNI", data["UNIUSD"], "#ff007a")],
        "AAVE, LINK and UNI: change since Oct. 25, 2026 (USD)",
    )
    fact = make_fact_card(
        d / "fact-fidelity-crypto-seven-coins",
        "Fidelity Crypto · Nov. 24, 2026",
        "+AAVE  +LINK  +UNI",
        "Seven cryptocurrencies plus the FIDD stablecoin. 1% fee per buy or sell, trades from $1, not available in Oregon for the new tokens",
        footer="Source: Fidelity Crypto help pages and Fidelity post on X",
    )
    return [
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: on Nov. 24, 2026 Fidelity Crypto added AAVE, LINK and UNI, bringing it to seven cryptocurrencies plus the FIDD stablecoin; trades cost a 1% fee, start at $1, and the new tokens are not available in Oregon", FID_FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Fidelity Crypto help pages, Nov. 24, 2026")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of AAVE, LINK and UNI prices in U.S. dollars since Oct. 25, 2026: by the evening of Nov. 24 UNI was down about 32%, AAVE about 31% and LINK about 23%", FID_CHART_ALTS),
         "caption": tr_map(CAPTION_CHART, src="Kraken daily closes, Oct. 25 to Nov. 24, 2026")},
    ]


FID_FACT_ALTS = {
 "es": "Tarjeta: el 24 de noviembre de 2026 Fidelity Crypto añadió AAVE, LINK y UNI y pasa a ofrecer siete criptomonedas más la stablecoin FIDD; cada operación cuesta un 1%, se puede empezar con 1 dólar y los nuevos tokens no están disponibles en Oregón",
 "pt": "Cartão: em 24 de novembro de 2026 a Fidelity Crypto adicionou AAVE, LINK e UNI e passou a oferecer sete criptomoedas mais a stablecoin FIDD; cada operação custa 1%, começa em US$ 1 e os novos tokens não estão disponíveis no Oregon",
 "fr": "Fiche : le 24 novembre 2026, Fidelity Crypto a ajouté AAVE, LINK et UNI et propose désormais sept cryptomonnaies plus le stablecoin FIDD ; chaque transaction coûte 1 %, dès 1 dollar, et les nouveaux jetons ne sont pas disponibles en Oregon",
 "de": "Faktenkarte: Am 24. November 2026 hat Fidelity Crypto AAVE, LINK und UNI aufgenommen und bietet nun sieben Kryptowährungen plus den Stablecoin FIDD; jeder Kauf und Verkauf kostet 1 %, ab 1 US-Dollar, und die neuen Token sind in Oregon nicht verfügbar",
 "ru": "Карточка: 24 ноября 2026 года Fidelity Crypto добавила AAVE, LINK и UNI, теперь на платформе семь криптовалют и стейблкоин FIDD; комиссия 1% за покупку или продажу, сделки от 1 доллара, новые токены недоступны в Орегоне",
 "tr": "Bilgi kartı: Fidelity Crypto 24 Kasım 2026'da AAVE, LINK ve UNI'yi ekledi ve artık yedi kripto para ile FIDD stablecoin'i sunuyor; her alım ve satım yüzde 1 ücretli, işlemler 1 dolardan başlıyor ve yeni tokenlar Oregon'da sunulmuyor",
 "id": "Kartu fakta: pada 24 November 2026 Fidelity Crypto menambahkan AAVE, LINK, dan UNI sehingga kini menawarkan tujuh kripto plus stablecoin FIDD; setiap beli atau jual dikenai biaya 1%, mulai dari 1 dolar, dan token baru tidak tersedia di Oregon",
 "ja": "ファクトカード: 2026年11月24日、Fidelity CryptoはAAVE、LINK、UNIを追加し、暗号資産7銘柄とステーブルコインFIDDを扱うようになった。売買ごとに1%の手数料、1ドルから取引可能、新トークンはオレゴン州では利用できない",
 "ko": "팩트 카드: 2026년 11월 24일 Fidelity Crypto가 AAVE, LINK, UNI를 추가해 암호화폐 7종과 스테이블코인 FIDD를 제공하게 됐다. 매수와 매도마다 1% 수수료, 1달러부터 거래 가능, 새 토큰은 오리건주에서 이용할 수 없다",
}
FID_CHART_ALTS = {
 "es": "Gráfico de líneas de los precios de AAVE, LINK y UNI en dólares desde el 25 de octubre de 2026: en la tarde del 24 de noviembre UNI había caído cerca de un 32%, AAVE cerca de un 31% y LINK cerca de un 23%",
 "pt": "Gráfico de linhas dos preços de AAVE, LINK e UNI em dólares desde 25 de outubro de 2026: na noite de 24 de novembro o UNI acumulava queda de cerca de 32%, o AAVE de cerca de 31% e o LINK de cerca de 23%",
 "fr": "Graphique en courbes des prix d'AAVE, LINK et UNI en dollars depuis le 25 octobre 2026 : le soir du 24 novembre, UNI avait perdu environ 32 %, AAVE environ 31 % et LINK environ 23 %",
 "de": "Liniendiagramm der Kurse von AAVE, LINK und UNI in US-Dollar seit dem 25. Oktober 2026: Am Abend des 24. November lag UNI rund 32 % im Minus, AAVE rund 31 % und LINK rund 23 %",
 "ru": "Линейный график цен AAVE, LINK и UNI в долларах с 25 октября 2026 года: к вечеру 24 ноября UNI подешевел примерно на 32%, AAVE примерно на 31%, LINK примерно на 23%",
 "tr": "AAVE, LINK ve UNI'nin 25 Ekim 2026'dan bu yana dolar fiyatlarını gösteren çizgi grafik: 24 Kasım akşamı UNI yaklaşık yüzde 32, AAVE yaklaşık yüzde 31 ve LINK yaklaşık yüzde 23 düşüşteydi",
 "id": "Grafik garis harga AAVE, LINK, dan UNI dalam dolar AS sejak 25 Oktober 2026: pada malam 24 November UNI turun sekitar 32%, AAVE sekitar 31%, dan LINK sekitar 23%",
 "ja": "2026年10月25日以降のAAVE、LINK、UNIのドル建て価格の折れ線グラフ。11月24日夜時点でUNIは約32%、AAVEは約31%、LINKは約23%下落",
 "ko": "2026년 10월 25일 이후 AAVE, LINK, UNI의 달러 가격 꺾은선 그래프: 11월 24일 저녁 기준 UNI는 약 32%, AAVE는 약 31%, LINK는 약 23% 하락",
}


def build_coldcard_postmortem():
    d = OUT / COLD_SLUG
    tl = make_timeline_card(
        d / "timeline-coldcard-weak-seed-2021-2026",
        "Coldcard seed flaw · timeline",
        [
            ("Mar 2021", "Firmware starts making seeds with a weak software generator", ORANGE),
            ("Jul 29, 2026", "Thieves rebuild keys offline and start draining wallets", RED),
            ("Jul 31, 2026", "Coinkite ships fixed firmware", GREEN),
            ("Nov 23, 2026", "Coinkite publishes its postmortem", (96, 165, 250)),
        ],
        footer="Source: Coinkite postmortem, Nov. 23, 2026",
        margin=170, wrap_w=250,
    )
    chart = make_bar_chart(
        d / "chart-coldcard-seed-entropy-bits",
        ["Mk2 / Mk3\n(affected)", "Mk4 / Mk5 / Q\n(affected)", "Intended\ntarget"],
        [40, 72, 128],
        "Real randomness in Coldcard seeds (bits, Coinkite estimate)",
        colors=["#f87171", "#fb923c", "#34d399"],
        value_fmt=lambda v: f"{v:.0f} bits",
        axis_fmt=lambda x, _p: f"{x:.0f}",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline: in March 2021 Coldcard firmware started making seeds with a weak software random number generator; on July 29, 2026 thieves began rebuilding keys offline and draining wallets; on July 31, 2026 Coinkite shipped fixed firmware; on Nov. 23, 2026 Coinkite published its postmortem", COLD_TL_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Coinkite postmortem, Nov. 23, 2026")},
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Bar chart of Coinkite's estimate of real randomness in Coldcard seeds: about 40 bits on affected Mk2 and Mk3 devices, about 72 bits on affected Mk4, Mk5 and Q devices, versus the intended 128 bits", COLD_CHART_ALTS),
         "caption": tr_map(CAPTION_CHART, src="Coinkite postmortem, Nov. 23, 2026")},
    ]


COLD_TL_ALTS = {
 "es": "Cronología: en marzo de 2021 el firmware de Coldcard empezó a crear semillas con un generador de números aleatorios por software débil; el 29 de julio de 2026 los ladrones empezaron a reconstruir claves sin conexión y a vaciar billeteras; el 31 de julio de 2026 Coinkite publicó un firmware corregido; el 23 de noviembre de 2026 Coinkite publicó su análisis posterior",
 "pt": "Linha do tempo: em março de 2021 o firmware da Coldcard passou a gerar sementes com um gerador de números aleatórios por software fraco; em 29 de julho de 2026 ladrões começaram a reconstruir chaves offline e esvaziar carteiras; em 31 de julho de 2026 a Coinkite lançou o firmware corrigido; em 23 de novembro de 2026 a Coinkite publicou seu relatório pós-incidente",
 "fr": "Chronologie : en mars 2021, le firmware Coldcard commence à créer des graines avec un générateur logiciel de nombres aléatoires trop faible ; le 29 juillet 2026, des voleurs reconstruisent des clés hors ligne et vident des portefeuilles ; le 31 juillet 2026, Coinkite publie un firmware corrigé ; le 23 novembre 2026, Coinkite publie son rapport d'incident",
 "de": "Zeitleiste: Im März 2021 begann die Coldcard-Firmware, Seeds mit einem schwachen Software-Zufallszahlengenerator zu erzeugen; am 29. Juli 2026 begannen Diebe, Schlüssel offline nachzubauen und Wallets zu leeren; am 31. Juli 2026 lieferte Coinkite eine korrigierte Firmware; am 23. November 2026 veröffentlichte Coinkite seinen Untersuchungsbericht",
 "ru": "Хронология: в марте 2021 года прошивка Coldcard начала создавать сид-фразы слабым программным генератором случайных чисел; 29 июля 2026 года воры начали восстанавливать ключи офлайн и опустошать кошельки; 31 июля 2026 года Coinkite выпустила исправленную прошивку; 23 ноября 2026 года Coinkite опубликовала разбор инцидента",
 "tr": "Zaman çizelgesi: Mart 2021'de Coldcard yazılımı tohumları zayıf bir yazılım rastgele sayı üreteciyle oluşturmaya başladı; 29 Temmuz 2026'da hırsızlar anahtarları çevrimdışı yeniden üretip cüzdanları boşaltmaya başladı; 31 Temmuz 2026'da Coinkite düzeltilmiş yazılımı yayımladı; 23 Kasım 2026'da Coinkite olay sonrası raporunu yayımladı",
 "id": "Linimasa: pada Maret 2021 firmware Coldcard mulai membuat seed dengan generator angka acak perangkat lunak yang lemah; pada 29 Juli 2026 pencuri mulai membangun ulang kunci secara offline dan menguras dompet; pada 31 Juli 2026 Coinkite merilis firmware perbaikan; pada 23 November 2026 Coinkite menerbitkan laporan pascainsiden",
 "ja": "年表: 2021年3月、Coldcardのファームウェアが弱いソフトウェア乱数生成器でシードを作り始める。2026年7月29日、窃盗犯がオフラインで鍵を再現しウォレットから資金を抜き始める。2026年7月31日、Coinkiteが修正版ファームウェアを公開。2026年11月23日、Coinkiteが事後調査報告書を公表",
 "ko": "타임라인: 2021년 3월 Coldcard 펌웨어가 약한 소프트웨어 난수 생성기로 시드를 만들기 시작했다. 2026년 7월 29일 도둑들이 오프라인에서 키를 재구성해 지갑을 털기 시작했다. 2026년 7월 31일 Coinkite가 수정 펌웨어를 배포했다. 2026년 11월 23일 Coinkite가 사후 분석 보고서를 공개했다",
}
COLD_CHART_ALTS = {
 "es": "Gráfico de barras con la estimación de Coinkite sobre la aleatoriedad real de las semillas de Coldcard: unos 40 bits en los Mk2 y Mk3 afectados, unos 72 bits en los Mk4, Mk5 y Q afectados, frente a los 128 bits previstos",
 "pt": "Gráfico de barras com a estimativa da Coinkite para a aleatoriedade real das sementes da Coldcard: cerca de 40 bits nos Mk2 e Mk3 afetados, cerca de 72 bits nos Mk4, Mk5 e Q afetados, contra os 128 bits previstos",
 "fr": "Graphique en barres de l'estimation de Coinkite sur le hasard réel des graines Coldcard : environ 40 bits sur les Mk2 et Mk3 touchés, environ 72 bits sur les Mk4, Mk5 et Q touchés, contre 128 bits prévus",
 "de": "Balkendiagramm mit Coinkites Schätzung der echten Zufälligkeit von Coldcard-Seeds: etwa 40 Bit bei betroffenen Mk2 und Mk3, etwa 72 Bit bei betroffenen Mk4, Mk5 und Q, statt der vorgesehenen 128 Bit",
 "ru": "Столбчатая диаграмма с оценкой Coinkite реальной случайности сид-фраз Coldcard: около 40 бит у затронутых Mk2 и Mk3, около 72 бит у затронутых Mk4, Mk5 и Q против задуманных 128 бит",
 "tr": "Coinkite'ın Coldcard tohumlarındaki gerçek rastgelelik tahminini gösteren çubuk grafik: etkilenen Mk2 ve Mk3'te yaklaşık 40 bit, etkilenen Mk4, Mk5 ve Q'da yaklaşık 72 bit, hedeflenen 128 bite karşı",
 "id": "Grafik batang perkiraan Coinkite tentang keacakan nyata seed Coldcard: sekitar 40 bit pada Mk2 dan Mk3 yang terdampak, sekitar 72 bit pada Mk4, Mk5, dan Q yang terdampak, dibandingkan target 128 bit",
 "ja": "Coldcardのシードに含まれる実際のランダム性についてのCoinkiteの推定を示す棒グラフ。影響を受けたMk2とMk3は約40ビット、Mk4、Mk5、Qは約72ビットで、本来の目標は128ビット",
 "ko": "Coldcard 시드의 실제 무작위성에 대한 Coinkite 추정치 막대 그래프: 영향을 받은 Mk2와 Mk3는 약 40비트, Mk4, Mk5, Q는 약 72비트로, 원래 목표는 128비트",
}

# --- Nov 25, 2026 morning run: bitcoin $58,000 after PCE, Bullpen account takeover --------------
PCE_SLUG = "bitcoin-58000-pce-inflation-3-8-percent-eighth-weekly-loss-nov-2026"
BULL_SLUG = "bullpen-hack-ansem-wallet-2-57-million-imported-keys-nov-2026"


def build_btc_58k_pce():
    d = OUT / PCE_SLUG
    data = json.loads((I18N / PCE_SLUG / "chart-data.json").read_text(encoding="utf-8"))
    xs = np.array([r[0] for r in data["daily"]], dtype=float)
    ys = np.array([r[1] for r in data["daily"]])
    assert round(ys[0]) == 77437 and round(ys[-1]) == 58003, (ys[0], ys[-1])
    chart = make_line_chart(
        d / "chart-btc-daily-closes-november-2026",
        xs, ys,
        title="Bitcoin in November 2026: Kraken daily closes (Nov. 25: price at 8 a.m. CT)",
        hline=77437.0,
        hlabel="Oct. 31 close: $77,437",
    )
    fact = make_fact_card(
        d / "fact-pce-inflation-october-3-8-percent",
        "U.S. PCE price index · October 2026",
        "3.8% (core 3.3%)",
        "Prices rose 3.8% from a year earlier, up from 3.6% in September. Core PCE, without food and energy, was 3.3%, above the 3.2% forecast",
        footer="Source: Commerce Department via CNBC, Nov. 25, 2026",
    )
    return [
        {"id": "chart", "file": chart.name, "w": 1200, "h": 675, "kind": "chart",
         "alt": alts("Line chart of bitcoin's daily closing price on Kraken from Oct. 31 to Nov. 25, 2026: it starts at $77,437, holds near $74,000 to $80,000 in early November, drops sharply from Nov. 12, and reaches about $58,000 on the morning of Nov. 25, about 25% lower", PCE_CHART_ALTS),
         "caption": tr_map(CAPTION_CHART, src="Kraken BTC/USD daily closes, Oct. 31 to Nov. 25, 2026")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: the U.S. PCE price index rose 3.8% in the year to October 2026, up from 3.6% in September; core PCE was 3.3%, above the 3.2% forecast", PCE_FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="U.S. Commerce Department via CNBC, Nov. 25, 2026")},
    ]


PCE_CHART_ALTS = {
 "es": "Gráfico de líneas del precio de cierre diario de bitcoin en Kraken del 31 de octubre al 25 de noviembre de 2026: empieza en 77.437 dólares, se mantiene entre 74.000 y 80.000 a principios de noviembre, cae con fuerza desde el 12 de noviembre y llega a unos 58.000 dólares la mañana del 25 de noviembre, alrededor de un 25% menos",
 "pt": "Gráfico de linha do preço de fechamento diário do bitcoin na Kraken de 31 de outubro a 25 de novembro de 2026: começa em US$ 77.437, fica entre US$ 74.000 e US$ 80.000 no início de novembro, cai forte a partir de 12 de novembro e chega a cerca de US$ 58.000 na manhã de 25 de novembro, cerca de 25% abaixo",
 "fr": "Graphique linéaire du cours de clôture quotidien du bitcoin sur Kraken du 31 octobre au 25 novembre 2026 : il part de 77 437 dollars, reste entre 74 000 et 80 000 dollars début novembre, chute nettement à partir du 12 novembre et atteint environ 58 000 dollars le matin du 25 novembre, soit environ 25 % de moins",
 "de": "Liniendiagramm der täglichen Bitcoin-Schlusskurse auf Kraken vom 31. Oktober bis 25. November 2026: Start bei 77.437 $, Anfang November zwischen 74.000 und 80.000 $, ab dem 12. November ein starker Rückgang und am Morgen des 25. November rund 58.000 $, etwa 25 % weniger",
 "ru": "Линейный график дневных цен закрытия биткоина на Kraken с 31 октября по 25 ноября 2026 года: старт на $77 437, в начале ноября цена держится между $74 000 и $80 000, с 12 ноября резко падает и утром 25 ноября достигает около $58 000, примерно на 25% ниже",
 "tr": "Bitcoin'in 31 Ekim - 25 Kasım 2026 arasında Kraken'deki günlük kapanış fiyatını gösteren çizgi grafik: 77.437 dolardan başlıyor, kasım başında 74.000-80.000 dolar arasında kalıyor, 12 Kasım'dan itibaren sert düşüyor ve 25 Kasım sabahı yaklaşık 58.000 dolara, yani yaklaşık %25 aşağıya iniyor",
 "id": "Grafik garis harga penutupan harian bitcoin di Kraken dari 31 Oktober hingga 25 November 2026: dimulai di US$77.437, bertahan di kisaran US$74.000 hingga US$80.000 pada awal November, turun tajam sejak 12 November, dan mencapai sekitar US$58.000 pada pagi 25 November, sekitar 25% lebih rendah",
 "ja": "2026年10月31日から11月25日までのクラーケンにおけるビットコインの日次終値の折れ線グラフ。77,437ドルから始まり、11月上旬は74,000〜80,000ドルで推移、11月12日から急落し、11月25日朝には約58,000ドルと約25%下落",
 "ko": "2026년 10월 31일부터 11월 25일까지 크라켄 비트코인 일일 종가 선 그래프. 77,437달러에서 시작해 11월 초 74,000~80,000달러에 머물다 11월 12일부터 급락해 11월 25일 아침 약 58,000달러로 약 25% 하락",
}
PCE_FACT_ALTS = {
 "es": "Tarjeta: el índice de precios PCE de EE. UU. subió un 3,8% en el año hasta octubre de 2026, frente al 3,6% de septiembre; el PCE subyacente fue del 3,3%, por encima del 3,2% previsto",
 "pt": "Cartão: o índice de preços PCE dos EUA subiu 3,8% nos 12 meses até outubro de 2026, ante 3,6% em setembro; o PCE núcleo foi de 3,3%, acima dos 3,2% previstos",
 "fr": "Fiche : l'indice des prix PCE américain a augmenté de 3,8 % sur un an en octobre 2026, contre 3,6 % en septembre ; le PCE sous-jacent était de 3,3 %, au-dessus des 3,2 % attendus",
 "de": "Faktenkarte: Der US-Preisindex PCE stieg im Jahr bis Oktober 2026 um 3,8 %, nach 3,6 % im September; der Kern-PCE lag bei 3,3 %, über der Prognose von 3,2 %",
 "ru": "Карточка: индекс цен PCE в США вырос на 3,8% за год по октябрь 2026 года после 3,6% в сентябре; базовый PCE составил 3,3% при прогнозе 3,2%",
 "tr": "Bilgi kartı: ABD PCE fiyat endeksi Ekim 2026'ya kadar olan bir yılda %3,8 arttı, eylülde bu oran %3,6'ydı; çekirdek PCE %3,2 beklentinin üzerinde %3,3 oldu",
 "id": "Kartu fakta: indeks harga PCE AS naik 3,8% dalam setahun hingga Oktober 2026, dari 3,6% pada September; PCE inti 3,3%, di atas perkiraan 3,2%",
 "ja": "ファクトカード：米PCE物価指数は2026年10月までの1年間で3.8%上昇（9月は3.6%）。コアPCEは3.3%で予想の3.2%を上回った",
 "ko": "팩트 카드: 미국 PCE 물가지수는 2026년 10월까지 1년간 3.8% 올라 9월의 3.6%보다 높아졌다. 근원 PCE는 3.3%로 예상치 3.2%를 웃돌았다",
}


def build_bullpen_takeover():
    d = OUT / BULL_SLUG
    tl = make_timeline_card(
        d / "timeline-bullpen-account-takeover-nov-24-25",
        "Bullpen account takeover · Central time",
        [
            ("2:34 a.m.", "Nov. 24: a wallet labeled as Ansem's starts selling memecoins", RED),
            ("10:35 a.m.", "Nov. 24: Bullpen confirms unauthorized transfers in 18 to 19 beta accounts", ORANGE),
            ("1:44 p.m.", "Nov. 24: Bullpen says accounts were taken over, imported wallets exposed", (96, 165, 250)),
            ("7:40 a.m.", "Nov. 25: old system shut down; outside security review planned", GREEN),
        ],
        footer="Sources: Bullpen posts on X, CoinDesk",
        margin=170, wrap_w=250,
    )
    fact = make_fact_card(
        d / "fact-bullpen-2-57-million-19-accounts",
        "Bullpen beta accounts · Nov. 24, 2026",
        "$2.57 million",
        "Moved to an Arbitrum address after 19 old beta accounts were taken over. Bullpen says 99.8% of the funds came from one account",
        footer="Sources: Lookonchain via The Block; Bullpen on X",
    )
    return [
        {"id": "timeline", "file": tl.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Timeline in U.S. Central time: at 2:34 a.m. on Nov. 24, 2026 a wallet labeled as Ansem's starts selling memecoins; at 10:35 a.m. Bullpen confirms unauthorized transfers in 18 to 19 beta accounts; at 1:44 p.m. Bullpen says the accounts were taken over and imported wallets were exposed; at 7:40 a.m. on Nov. 25 Bullpen says the old system is shut down and an outside security review is planned", BULL_TL_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Bullpen posts on X, CoinDesk, Nov. 24-25, 2026")},
        {"id": "fact", "file": fact.name, "w": 1200, "h": 630, "kind": "fact",
         "alt": alts("Fact card: $2.57 million moved to an Arbitrum address after 19 old Bullpen beta accounts were taken over; Bullpen says 99.8% of the funds came from one account", BULL_FACT_ALTS),
         "caption": tr_map(CAPTION_SOURCE, src="Lookonchain via The Block; Bullpen on X, Nov. 24, 2026")},
    ]


BULL_TL_ALTS = {
 "es": "Cronología en hora del centro de EE. UU.: a las 2:34 del 24 de noviembre de 2026 una billetera atribuida a Ansem empieza a vender memecoins; a las 10:35 Bullpen confirma transferencias no autorizadas en 18 a 19 cuentas beta; a las 13:44 Bullpen dice que las cuentas fueron tomadas y las billeteras importadas quedaron expuestas; a las 7:40 del 25 de noviembre Bullpen dice que cerró el sistema antiguo y que habrá una revisión de seguridad externa",
 "pt": "Linha do tempo no horário central dos EUA: às 2h34 de 24 de novembro de 2026 uma carteira atribuída a Ansem começa a vender memecoins; às 10h35 a Bullpen confirma transferências não autorizadas em 18 a 19 contas beta; às 13h44 a Bullpen diz que as contas foram invadidas e as carteiras importadas ficaram expostas; às 7h40 de 25 de novembro a Bullpen diz que desligou o sistema antigo e que haverá uma auditoria de segurança externa",
 "fr": "Chronologie à l'heure du centre des États-Unis : à 2 h 34 le 24 novembre 2026, un portefeuille attribué à Ansem commence à vendre des memecoins ; à 10 h 35, Bullpen confirme des transferts non autorisés sur 18 à 19 comptes bêta ; à 13 h 44, Bullpen indique que les comptes ont été piratés et que les portefeuilles importés étaient exposés ; à 7 h 40 le 25 novembre, Bullpen annonce l'arrêt de l'ancien système et un audit de sécurité externe",
 "de": "Zeitleiste in US-Zentralzeit: Um 2:34 Uhr am 24. November 2026 beginnt eine Ansem zugeordnete Wallet, Memecoins zu verkaufen; um 10:35 Uhr bestätigt Bullpen unbefugte Überweisungen bei 18 bis 19 Beta-Konten; um 13:44 Uhr erklärt Bullpen, die Konten seien übernommen und importierte Wallets offengelegt worden; um 7:40 Uhr am 25. November meldet Bullpen, das alte System sei abgeschaltet und eine externe Sicherheitsprüfung geplant",
 "ru": "Хронология по центральному времени США: в 2:34 24 ноября 2026 года кошелек, приписываемый Ansem, начинает продавать мемкоины; в 10:35 Bullpen подтверждает несанкционированные переводы с 18–19 бета-аккаунтов; в 13:44 Bullpen сообщает, что аккаунты были захвачены, а импортированные кошельки оказались под угрозой; в 7:40 25 ноября Bullpen сообщает, что старая система отключена и запланирован внешний аудит безопасности",
 "tr": "ABD Merkez saatiyle zaman çizelgesi: 24 Kasım 2026 saat 2.34'te Ansem'e ait olduğu belirtilen bir cüzdan memecoin satmaya başlıyor; 10.35'te Bullpen 18-19 beta hesabında yetkisiz transferleri doğruluyor; 13.44'te Bullpen hesapların ele geçirildiğini ve içe aktarılan cüzdanların açığa çıktığını söylüyor; 25 Kasım 7.40'ta Bullpen eski sistemin kapatıldığını ve dış güvenlik incelemesi yapılacağını açıklıyor",
 "id": "Linimasa dalam waktu Central AS: pukul 2.34 pada 24 November 2026 dompet yang dikaitkan dengan Ansem mulai menjual memecoin; pukul 10.35 Bullpen mengonfirmasi transfer tanpa izin di 18 hingga 19 akun beta; pukul 13.44 Bullpen menyatakan akun-akun itu diambil alih dan dompet yang diimpor ikut terekspos; pukul 7.40 pada 25 November Bullpen menyatakan sistem lama dimatikan dan audit keamanan eksternal direncanakan",
 "ja": "米中部時間のタイムライン：2026年11月24日午前2時34分、Ansemのものとされるウォレットがミームコインの売却を開始。午前10時35分、Bullpenが18〜19のベータアカウントでの不正送金を確認。午後1時44分、Bullpenはアカウントが乗っ取られ、インポートされたウォレットも危険にさらされたと説明。11月25日午前7時40分、旧システムの停止と外部セキュリティ監査の実施を発表",
 "ko": "미국 중부 시간 타임라인: 2026년 11월 24일 오전 2시 34분 Ansem의 것으로 알려진 지갑이 밈코인 매도를 시작한다. 오전 10시 35분 Bullpen이 베타 계정 18~19개의 무단 이체를 확인한다. 오후 1시 44분 Bullpen은 계정이 탈취돼 가져온 지갑도 노출됐다고 밝힌다. 11월 25일 오전 7시 40분 Bullpen은 구형 시스템을 종료하고 외부 보안 점검을 받겠다고 발표한다",
}
BULL_FACT_ALTS = {
 "es": "Tarjeta: 2,57 millones de dólares se movieron a una dirección de Arbitrum después de que se tomaran 19 cuentas beta antiguas de Bullpen; Bullpen dice que el 99,8% de los fondos salió de una sola cuenta",
 "pt": "Cartão: US$ 2,57 milhões foram movidos para um endereço na Arbitrum depois que 19 contas beta antigas da Bullpen foram invadidas; a Bullpen diz que 99,8% dos fundos saíram de uma única conta",
 "fr": "Fiche : 2,57 millions de dollars ont été transférés vers une adresse Arbitrum après le piratage de 19 anciens comptes bêta de Bullpen ; selon Bullpen, 99,8 % des fonds venaient d'un seul compte",
 "de": "Faktenkarte: 2,57 Millionen $ wurden auf eine Arbitrum-Adresse verschoben, nachdem 19 alte Bullpen-Beta-Konten übernommen wurden; laut Bullpen stammten 99,8 % der Gelder von einem einzigen Konto",
 "ru": "Карточка: $2,57 млн были переведены на адрес в сети Arbitrum после захвата 19 старых бета-аккаунтов Bullpen; по данным Bullpen, 99,8% средств пришлись на один аккаунт",
 "tr": "Bilgi kartı: 19 eski Bullpen beta hesabı ele geçirildikten sonra 2,57 milyon dolar bir Arbitrum adresine aktarıldı; Bullpen'e göre fonların %99,8'i tek bir hesaptan geldi",
 "id": "Kartu fakta: US$2,57 juta dipindahkan ke sebuah alamat Arbitrum setelah 19 akun beta lama Bullpen diambil alih; Bullpen menyebut 99,8% dana berasal dari satu akun",
 "ja": "ファクトカード：Bullpenの旧ベータアカウント19件が乗っ取られた後、257万ドルがArbitrum上のアドレスに移された。Bullpenによると資金の99.8%は1つのアカウントからだった",
 "ko": "팩트 카드: Bullpen의 구형 베타 계정 19개가 탈취된 뒤 257만 달러가 아비트럼 주소로 옮겨졌다. Bullpen은 자금의 99.8%가 한 계정에서 나왔다고 밝혔다",
}


BUILDERS = {
    "bitcoin-58000-pce-inflation-3-8-percent-eighth-weekly-loss-nov-2026": "btc58pce",
    "bullpen-hack-ansem-wallet-2-57-million-imported-keys-nov-2026": "bullpen",
    "fidelity-crypto-adds-aave-link-uni-nov-2026": "fiddefi",
    "coldcard-postmortem-weak-seeds-bitcoin-thefts-nov-2026": "coldcard",
    "kraken-krak-credit-cards-4-percent-bitcoin-cashback-usdc-secured-nov-2026": "krakcc",
    "bitcoin-etfs-record-4-71-billion-november-outflows-nov-2026": "etfnov471",
    "south-korea-crypto-bill-bank-led-stablecoins-ico-20-percent-exchange-cap-nov-2026": "krbill",
    "bitcoin-spikes-to-64500-on-huang-return-then-fades-nov-2026": "huangfade",
    "cftc-staff-bitcoin-ether-stablecoins-count-toward-exchange-reserves-nov-2026": "cftcres",
    "binance-hires-mandiant-slowmist-verichains-security-review-nov-2026": "bnbreview",
    "ark-invest-withdraws-coindesk-20-crypto-etfs-nov-2026": "arkcd20",
    "bitcoin-etfs-1-79-billion-weekly-outflow-fourth-week-nov-2026": "etf179",
    "strategy-buys-457-bitcoin-212-million-strc-buyback-nov-2026": "mstr457",
    "fusionist-ace-bridge-exploit-10-quintillion-tokens-nov-2026": "fusionist",
    "trump-memecoin-second-dinner-token-down-99-percent-nov-2026": "trumpdinner",
    "bitcoin-61500-abraxas-capital-1-billion-btc-off-exchanges-nov-2026": "abraxas",
    "chainflip-loss-12-million-bitcoin-10-percent-bounty-nov-2026": "cfbounty",
    "bitcoin-core-node-stall-bug-ai-found-fix-nov-2026": "corestall",
    "kraken-bitcoin-cad-flash-crash-24250-trades-stand-nov-2026": "krakencad",
    "bitcoin-crashes-to-55100-rebounds-above-60000-nov-2026": "btc55k",
    "bitcoin-new-2026-low-57661-strategy-shares-sink-nov-2026": "btcnewlow",
    "bitcoin-below-59000-near-2026-low-liquidations-nov-2026": "btc59k2026",
    "senate-passes-death-bets-act-prediction-markets-nov-2026": "deathbets",
    "blackrock-ibit-record-541-million-outflow-nov-2026": "ibitrec",
    "sec-fake-crypto-platforms-37-million-whatsapp-nov-2026": "secfake",
    "bitcoin-below-62000-lowest-since-july-etf-outflows-nov-2026": "btc62kjul",
    "coinbase-crypto-options-non-us-users-deribit-nov-2026": "cboptions",
    "threat-disruption-center-crypto-scams-trm-labs-nov-2026": "tdc",
    "sky-stablecoin-psm-north-korea-518-million-inca-nov-2026": "skypsm",
    "ledger-tampered-wallets-berlin-dubai-nov-2026": "ledgerbd",
    "senators-genius-act-state-stablecoin-safe-harbor-nov-2026": "geniusstate",
    "fed-minutes-more-rate-hikes-bitcoin-below-63000-nov-2026": "fedmin63k",
    "binance-abu-dhabi-court-order-frozen-hack-funds-nov-2026": "bnbadgm",
    "russia-retail-investors-bitcoin-ether-usdt-300000-ruble-cap-nov-2026": "rusretail",
    "mev-brothers-acquitted-25-million-ethereum-bots-nov-2026": "mevacq",
    "cftc-approves-backpack-blockchain-derivatives-exchange-nov-2026": "cftcbp",
    "goldman-wells-fargo-double-bitcoin-etf-holdings-13f-nov-2026": "banks13f",
    "trezor-skladon-shipping-breach-27000-orders-nov-2026": "trezor",
    "coinbase-borrow-new-york-all-50-states-nov-2026": "cbny",
    "optimizely-hack-crypto-address-swap-178-sites-nov-2026": "optimizely",
    "solana-foundation-coingecko-majority-stake-nov-2026": "cgsol",
    "supreme-court-rejects-custodia-fed-master-account-nov-2026": "custodia",
    "solana-drops-mainnet-beta-solana-1-0-nov-2026": "sol10",
    "lighter-dex-10-4-million-leaked-api-key-nov-2026": "lighter",
    "chainflip-vault-drained-4-86-million-flip-falls-nov-2026": "chainflip",
    "strategy-buys-485-bitcoin-strive-251-nov-2026": "mstr485",
    "crypto-fear-greed-index-10-extreme-fear-nov-2026": "fng10",
    "bitcoin-loses-50-week-moving-average-nov-2026": "50w",
    "bitcoin-volatility-liquidations-nov-2026": "vol",
    "us-midterms-crypto-regulation-etf-outflows": "mid",
    "fincen-fed-withdraw-250-travel-rule-nov-2026": "fin",
    "pnc-coinbase-usdc-payments-pilot-nov-2026": "pnc",
    "coinbase-occ-national-trust-charter-nov-2026": "occ",
    "how-to-buy-first-bitcoin-coinbase": "howto",
    "is-coinbase-safe-for-beginners": "safe",
    "how-much-bitcoin-should-a-beginner-buy-dca": "dca",
    "what-is-a-crypto-wallet-custodial-vs-self-custody": "wallet",
    "coinbase-fees-explained": "fees",
    "how-to-cash-out-bitcoin-coinbase-to-bank": "cashout",
    "bitcoin-etf-vs-buying-bitcoin": "etf",
    "binance-hack-north-korea-memecoin-laundering-nov-2026": "bnbhack",
    "bitcoin-hot-cpi-etf-outflows-nov-2026": "hotcpi",
    "binance-blocks-mexc-fincen-order-nov-2026": "mexc",
    "banks-270-million-stablecoin-project-faro-nov-2026": "faro",
    "bitcoin-below-73000-lowest-since-august-nov-2026": "btc73k",
    "binance-warns-iphone-ios-flaw-wallet-keys-nov-2026": "iosflaw",
    "across-protocol-domain-hijack-phishing-nov-2026": "across",
    "okxice-tokenized-stocks-launch-nov-23-2026": "okxice",
    "stablecoin-supply-shrinks-usdt-tether-nov-2026": "usdt",
    "sec-backs-cftc-stock-perps-crypto-etf-options-nov-2026": "secperps",
    "msci-drops-strategy-bitcoin-falls-nvidia-nov-2026": "msci",
    "doj-seizes-1-2-billion-binance-hack-north-korea-nov-2026": "dojseize",
    "bitcoin-below-70000-200-week-average-nov-2026": "btc70k",
    "trump-nominates-sec-cftc-commissioners-peirce-nov-2026": "secnom",
    "illinois-crypto-tax-doj-defi-challenge-nov-2026": "iltax",
    "dtcc-tokenized-stocks-solana-2027-nov-2026": "dtccsol",
    "kraken-payward-q3-2026-results-nov-2026": "payward",
    "crypto-treasury-firms-loans-nakamoto-btcs-nov-2026": "treasuryloans",
    "bitcoin-below-67000-sixth-weekly-loss-nov-2026": "btc67k",
    "unocoin-hack-bitgo-backup-keys-nov-2026": "unocoin",
    "ether-solana-xrp-lead-selloff-bitcoin-65000-nov-2026": "altselloff",
    "binance-reopens-withdrawals-87-networks-nov-2026": "bnbreopen",
    "bitcoin-falls-below-64000-three-month-low-nov-2026": "btc64k",
    "kava-lend-hack-3-8-million-kava-falls-nov-2026": "kavahack",
    "bitcoin-four-month-low-62000-liquidations-nov-2026": "btc62k",
    "coinone-data-breach-support-contractor-passwords-nov-2026": "coinone",
    "stusdt-wind-down-redeem-by-may-2027-nov-2026": "stusdt",
    "luxor-commander-hack-bitcoin-miners-hashrate-ocean-nov-2026": "luxor",
    "germany-customs-crypto-seizure-100000-euros-bundestag-nov-2026": "dezoll",
}


def build_slug(slug: str, btc=None):
    if btc is None and slug in (
        "bitcoin-loses-50-week-moving-average-nov-2026",
        "bitcoin-volatility-liquidations-nov-2026",
        "how-to-buy-first-bitcoin-coinbase",
    ):
        btc = fetch_btc_prices(90)
    key = BUILDERS[slug]
    if key == "btc58pce":
        figs = build_btc_58k_pce()
    elif key == "bullpen":
        figs = build_bullpen_takeover()
    elif key == "fiddefi":
        figs = build_fidelity_defi_tokens()
    elif key == "coldcard":
        figs = build_coldcard_postmortem()
    elif key == "krakcc":
        figs = build_krak_credit_cards()
    elif key == "etfnov471":
        figs = build_etf_nov_record_471()
    elif key == "krbill":
        figs = build_korea_digital_asset_bill()
    elif key == "huangfade":
        figs = build_huang_btc_fade()
    elif key == "cftcres":
        figs = build_cftc_crypto_reserves()
    elif key == "bnbreview":
        figs = build_binance_security_review()
    elif key == "arkcd20":
        figs = build_ark_withdraws_cd20()
    elif key == "etf179":
        figs = build_etf_weekly_179()
    elif key == "mstr457":
        figs = build_strategy_457()
    elif key == "fusionist":
        figs = build_fusionist_ace()
    elif key == "trumpdinner":
        figs = build_trump_dinner()
    elif key == "abraxas":
        figs = build_abraxas_withdrawals()
    elif key == "cfbounty":
        figs = build_chainflip_bounty()
    elif key == "corestall":
        figs = build_core_node_stall()
    elif key == "krakencad":
        figs = build_kraken_cad_crash()
    elif key == "btc55k":
        figs = build_btc_55100_rebound()
    elif key == "btcnewlow":
        figs = build_btc_new_2026_low()
    elif key == "btc59k2026":
        figs = build_btc_below_59k_2026_low()
    elif key == "deathbets":
        figs = build_death_bets_act()
    elif key == "ibitrec":
        figs = build_ibit_record_outflow()
    elif key == "secfake":
        figs = build_sec_fake_platforms()
    elif key == "btc62kjul":
        figs = build_btc_below_62k_july()
    elif key == "cboptions":
        figs = build_coinbase_options_intl()
    elif key == "50w":
        figs = build_bitcoin_50w(*btc)
    elif key == "vol":
        figs = build_volatility(*btc)
    elif key == "mid":
        figs = build_midterms()
    elif key == "fin":
        figs = build_fincen()
    elif key == "pnc":
        figs = build_pnc()
    elif key == "occ":
        figs = build_occ()
    elif key == "howto":
        figs = build_howto(*btc)
    elif key == "safe":
        figs = build_safe()
    elif key == "dca":
        figs = build_dca()
    elif key == "wallet":
        figs = build_wallet()
    elif key == "fees":
        figs = build_fees()
    elif key == "cashout":
        figs = build_cashout()
    elif key == "etf":
        figs = build_etf()
    elif key == "bnbhack":
        figs = build_binance_hack()
    elif key == "hotcpi":
        figs = build_hot_cpi()
    elif key == "mexc":
        figs = build_mexc()
    elif key == "faro":
        figs = build_faro()
    elif key == "btc73k":
        figs = build_btc_below_73k()
    elif key == "iosflaw":
        figs = build_ios_flaw()
    elif key == "across":
        figs = build_across()
    elif key == "okxice":
        figs = build_okxice()
    elif key == "usdt":
        figs = build_stablecoin_shrink()
    elif key == "secperps":
        figs = build_sec_perps_options()
    elif key == "msci":
        figs = build_msci_strategy()
    elif key == "dojseize":
        figs = build_doj_binance_seizure()
    elif key == "btc70k":
        figs = build_btc_below_70k()
    elif key == "secnom":
        figs = build_sec_cftc_nominees()
    elif key == "iltax":
        figs = build_illinois_tax()
    elif key == "dtccsol":
        figs = build_dtcc_solana()
    elif key == "payward":
        figs = build_payward_q3()
    elif key == "treasuryloans":
        figs = build_treasury_loans()
    elif key == "btc67k":
        figs = build_btc_below_67k()
    elif key == "unocoin":
        figs = build_unocoin_hack()
    elif key == "altselloff":
        figs = build_alt_selloff()
    elif key == "bnbreopen":
        figs = build_binance_reopen()
    elif key == "btc64k":
        figs = build_btc_below_64k()
    elif key == "kavahack":
        figs = build_kava_hack()
    elif key == "btc62k":
        figs = build_btc_62k_liquidations()
    elif key == "coinone":
        figs = build_coinone_breach()
    elif key == "stusdt":
        figs = build_stusdt_wind_down()
    elif key == "luxor":
        figs = build_luxor_hashrate_hijack()
    elif key == "dezoll":
        figs = build_germany_customs_crypto()
    elif key == "mstr485":
        figs = build_strategy_485_btc()
    elif key == "fng10":
        figs = build_fear_greed_10()
    elif key == "cftcbp":
        figs = build_cftc_backpack()
    elif key == "rusretail":
        figs = build_russia_retail_crypto()
    elif key == "tdc":
        figs = build_threat_disruption_center()
    elif key == "skypsm":
        figs = build_sky_psm_illicit()
    elif key == "ledgerbd":
        figs = build_ledger_berlin_dubai()
    elif key == "geniusstate":
        figs = build_genius_state_safe_harbor()
    elif key == "fedmin63k":
        figs = build_fed_minutes_btc_63k()
    elif key == "bnbadgm":
        figs = build_binance_adgm_order()
    elif key == "mevacq":
        figs = build_mev_acquittal()
    elif key == "banks13f":
        figs = build_banks_btc_etf_13f()
    elif key == "trezor":
        figs = build_trezor_skladon()
    elif key == "cbny":
        figs = build_coinbase_borrow_ny()
    elif key == "optimizely":
        figs = build_optimizely_clipper()
    elif key == "cgsol":
        figs = build_coingecko_solana()
    elif key == "chainflip":
        figs = build_chainflip_drain()
    elif key == "lighter":
        figs = build_lighter_api_key()
    elif key == "custodia":
        figs = build_custodia_scotus()
    elif key == "sol10":
        figs = build_solana_1_0()
    else:
        raise ValueError(slug)
    meta_path = I18N / slug / "figures.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(figs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in figs:
        p = OUT / slug / f["file"]
        print(f"  {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
    print(f"  wrote {meta_path.relative_to(ROOT)}")
    return figs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not args.all and not args.slug:
        ap.print_help()
        return 2
    slugs = list(BUILDERS) if args.all else [args.slug]
    btc = None
    need_btc = any(
        s in (
            "bitcoin-loses-50-week-moving-average-nov-2026",
            "bitcoin-volatility-liquidations-nov-2026",
            "how-to-buy-first-bitcoin-coinbase",
        )
        for s in slugs
    )
    if need_btc:
        print("Fetching BTC prices from CoinGecko…")
        btc = fetch_btc_prices(90)
        print(f"  {len(btc[0])} points, last=${btc[1][-1]:,.0f}")
    for slug in slugs:
        if slug not in BUILDERS:
            print(f"unknown slug {slug}", file=sys.stderr)
            return 1
        print(f"== {slug}")
        build_slug(slug, btc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
