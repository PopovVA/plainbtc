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
                    ylabel="USD", w=1200, h=675) -> Path:
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
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}")
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
                   colors=None, w=1200, h=675, value_fmt=None) -> Path:
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
    ax.yaxis.set_major_formatter(lambda x, _p: f"${x:,.0f}M")
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
    for x in range(0, w, 48):
        draw.line([(x, 0), (x, h)], fill=(255, 255, 255, 0))
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
