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


BUILDERS = {
    "trezor-skladon-shipping-breach-27000-orders-nov-2026": "trezor",
    "coinbase-borrow-new-york-all-50-states-nov-2026": "cbny",
    "optimizely-hack-crypto-address-swap-178-sites-nov-2026": "optimizely",
    "solana-foundation-coingecko-majority-stake-nov-2026": "cgsol",
    "supreme-court-rejects-custodia-fed-master-account-nov-2026": "custodia",
    "solana-drops-mainnet-beta-solana-1-0-nov-2026": "sol10",
    "lighter-dex-10-4-million-leaked-api-key-nov-2026": "lighter",
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
    elif key == "trezor":
        figs = build_trezor_skladon()
    elif key == "cbny":
        figs = build_coinbase_borrow_ny()
    elif key == "optimizely":
        figs = build_optimizely_clipper()
    elif key == "cgsol":
        figs = build_coingecko_solana()
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
