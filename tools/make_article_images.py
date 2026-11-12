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
        d / "chart-advanced-intro",
        ["Maker\n(Intro)", "Taker\n(Intro)"],
        [0.50, 0.90],
        title="Coinbase Advanced spot — Intro tier (U.S.)",
        ylabel="Fee %",
        value_fmt=lambda v: f"{v:.2f}%",
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
    chart = make_bar_chart(
        d / "chart-ach-days",
        ["ACH\nbank out", "Instant\n(eligible)"],
        [4, 0.5],
        title="Typical U.S. cash-out timing (illustrative)",
        ylabel="Business days (approx.)",
        value_fmt=lambda v: f"~{v:g}d",
    )
    tax = make_fact_card(
        d / "fact-irs-property",
        label="U.S. taxes",
        big="Property",
        sub="The IRS treats digital assets as property — selling bitcoin for USD is generally a taxable disposal",
        footer="Source: IRS · Digital assets",
    )
    return [
        _fig("timing", chart.name, "chart", 1200, 630, _lang_dict(
            "Bar chart comparing typical ACH cash-out timing of several business days versus faster instant cashouts",
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


BUILDERS = {
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
}


def build_slug(slug: str, btc=None):
    if btc is None and slug in (
        "bitcoin-loses-50-week-moving-average-nov-2026",
        "bitcoin-volatility-liquidations-nov-2026",
        "how-to-buy-first-bitcoin-coinbase",
    ):
        btc = fetch_btc_prices(90)
    key = BUILDERS[slug]
    if key == "50w":
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
